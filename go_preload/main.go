package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"runtime/debug"
	"sync"

	_ "github.com/mattn/go-sqlite3"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
	cvm "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/cvm/v20170312"
)

type PreloadRequest struct {
	SecretID      string `json:"secret_id"`
	SecretKey     string `json:"secret_key"`
	DefaultRegion string `json:"default_region"`
}

type PreloadResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

func main() {
	initLogger()
	http.HandleFunc("/preload_all", handlePreloadAll)
	http.HandleFunc("/health", handleHealth)

	addr := ":8088"
	log.Printf("Go Preload Server (Safe Mode) listening on %s\n", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("failed to start server: %v", err)
	}
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok", "mode": "cgo-full"})
}

func initLogger() {
	wd, _ := os.Getwd()
	root := filepath.Clean(filepath.Join(wd, ".."))
	logPath := filepath.Join(root, "cvm_manager.log")
	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err == nil {
		log.SetOutput(io.MultiWriter(os.Stdout, f))
	}
	log.SetFlags(log.LstdFlags)
	log.SetPrefix("[GO] ")
}

func handlePreloadAll(w http.ResponseWriter, r *http.Request) {
	// 增加 Panic 恢复，防止进程崩溃
	defer func() {
		if err := recover(); err != nil {
			log.Printf("CRITICAL PANIC: %v\n%s", err, debug.Stack())
			http.Error(w, "internal server error", http.StatusInternalServerError)
		}
	}()

	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req PreloadRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		log.Printf("Decode error: %v", err)
		http.Error(w, "invalid json", http.StatusBadRequest)
		return
	}

	if req.DefaultRegion == "" {
		req.DefaultRegion = "ap-beijing"
	}

	log.Printf("收到同步请求 (Region: %s)，正在执行...", req.DefaultRegion)

	if err := runFullPreload(req); err != nil {
		log.Printf("同步失败: %v", err)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(PreloadResponse{Success: false, Message: err.Error()})
		return
	}

	log.Printf("同步成功完成")
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(PreloadResponse{Success: true, Message: "success"})
}

func runFullPreload(req PreloadRequest) error {
	dbPath, err := resolveDBPath()
	if err != nil {
		return err
	}

	// 增加写等待，防止数据库忙
	db, err := sql.Open("sqlite3", dbPath+"?_journal=WAL&_busy_timeout=5000")
	if err != nil {
		return fmt.Errorf("open db failed: %w", err)
	}
	defer db.Close()

	client, err := newCvmClient(req.SecretID, req.SecretKey, req.DefaultRegion)
	if err != nil {
		return fmt.Errorf("init client failed: %w", err)
	}

	// 1. 同步区域
	regions, err := fetchRegions(client)
	if err != nil {
		return fmt.Errorf("fetch regions failed: %w", err)
	}
	_ = syncRegionsToDB(db, regions)

	// 2. 并发同步
	var wg sync.WaitGroup
	sem := make(chan struct{}, 10)
	for _, r := range regions {
		regionID := str(r.Region)
		if regionID == "" {
			continue
		}
		wg.Add(1)
		go func(rid string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()

			rClient, err := newCvmClient(req.SecretID, req.SecretKey, rid)
			if err != nil {
				return
			}

			// 可用区
			if zResp, err := rClient.DescribeZones(cvm.NewDescribeZonesRequest()); err == nil {
				_ = syncZonesToDB(db, rid, zResp.Response.ZoneSet)
			}

			// 镜像
			iReq := cvm.NewDescribeImagesRequest()
			iReq.Limit = common.Uint64Ptr(60)
			iReq.Filters = []*cvm.Filter{{Name: common.StringPtr("image-type"), Values: []*string{common.StringPtr("PUBLIC_IMAGE")}}}
			if iResp, err := rClient.DescribeImages(iReq); err == nil {
				_ = syncImagesToDB(db, rid, iResp.Response.ImageSet)
			}
		}(regionID)
	}
	wg.Wait()

	// 3. 同步实例
	return syncInstances(db, client, req.DefaultRegion)
}

func syncRegionsToDB(db *sql.DB, regions []*cvm.RegionInfo) error {
	tx, _ := db.Begin()
	defer tx.Rollback()
	_, _ = tx.Exec("DELETE FROM regions")
	stmt, _ := tx.Prepare("INSERT INTO regions (region, region_name, region_state, updated_at) VALUES (?, ?, ?, strftime('%s','now'))")
	for _, r := range regions {
		_, _ = stmt.Exec(str(r.Region), str(r.RegionName), str(r.RegionState))
	}
	return tx.Commit()
}

func syncZonesToDB(db *sql.DB, regionID string, zones []*cvm.ZoneInfo) error {
	tx, _ := db.Begin()
	defer tx.Rollback()
	_, _ = tx.Exec("DELETE FROM zones WHERE region = ?", regionID)
	stmt, _ := tx.Prepare("INSERT INTO zones (zone, region, zone_name, zone_state, updated_at) VALUES (?, ?, ?, ?, strftime('%s','now'))")
	for _, z := range zones {
		_, _ = stmt.Exec(str(z.Zone), regionID, str(z.ZoneName), str(z.ZoneState))
	}
	return tx.Commit()
}

func syncImagesToDB(db *sql.DB, regionID string, images []*cvm.Image) error {
	tx, _ := db.Begin()
	defer tx.Rollback()
	_, _ = tx.Exec("DELETE FROM images WHERE region = ? AND image_type = 'PUBLIC_IMAGE'", regionID)
	stmt, _ := tx.Prepare("INSERT INTO images (image_id, image_name, image_type, platform, region, created_time, updated_at) VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'))")
	for _, img := range images {
		_, _ = stmt.Exec(str(img.ImageId), str(img.ImageName), "PUBLIC_IMAGE", str(img.Platform), regionID, str(img.CreatedTime))
	}
	return tx.Commit()
}

func syncInstances(db *sql.DB, client *cvm.Client, defaultRegion string) error {
	_, _ = db.Exec("UPDATE instances SET status='-1', updated_at=strftime('%s','now') WHERE status != '-1'")
	var offset uint64 = 0
	const limit uint64 = 100
	for {
		req := cvm.NewDescribeInstancesRequest()
		req.Offset = common.Int64Ptr(int64(offset))
		req.Limit = common.Int64Ptr(int64(limit))
		resp, err := client.DescribeInstances(req)
		if err != nil {
			return err
		}
		if len(resp.Response.InstanceSet) == 0 {
			break
		}

		tx, _ := db.Begin()
		stmt, _ := tx.Prepare(`INSERT INTO instances (instance_id, instance_name, status, region, zone, instance_type, image_id, cpu, memory, private_ip, public_ip, created_time, updated_at) 
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
			ON CONFLICT(instance_id) DO UPDATE SET status=excluded.status, updated_at=strftime('%s','now')`)

		for _, inst := range resp.Response.InstanceSet {
			priv := ""
			if len(inst.PrivateIpAddresses) > 0 {
				priv = str(inst.PrivateIpAddresses[0])
			}
			pub := ""
			if len(inst.PublicIpAddresses) > 0 {
				pub = str(inst.PublicIpAddresses[0])
			}
			zone := ""
			if inst.Placement != nil {
				zone = str(inst.Placement.Zone)
			}

			_, _ = stmt.Exec(str(inst.InstanceId), str(inst.InstanceName), str(inst.InstanceState), defaultRegion, zone, str(inst.InstanceType), str(inst.ImageId), i64(inst.CPU), i64(inst.Memory), priv, pub, str(inst.CreatedTime))
		}
		_ = tx.Commit()
		if len(resp.Response.InstanceSet) < int(limit) {
			break
		}
		offset += limit
	}
	return nil
}

func str(p *string) string {
	if p == nil {
		return ""
	}
	return *p
}
func i64(p *int64) int64 {
	if p == nil {
		return 0
	}
	return *p
}

func resolveDBPath() (string, error) {
	wd, _ := os.Getwd()
	return filepath.Join(filepath.Dir(wd), "data", "cvm_cache.db"), nil
}

func newCvmClient(secretID, secretKey, region string) (*cvm.Client, error) {
	cred := common.NewCredential(secretID, secretKey)
	cpf := profile.NewClientProfile()
	return cvm.NewClient(cred, region, cpf)
}

func fetchRegions(client *cvm.Client) ([]*cvm.RegionInfo, error) {
	req := cvm.NewDescribeRegionsRequest()
	resp, err := client.DescribeRegions(req)
	if err != nil {
		return nil, err
	}
	return resp.Response.RegionSet, nil
}
