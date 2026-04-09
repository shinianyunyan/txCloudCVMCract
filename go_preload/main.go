package main

/*
   Go 预加载模块 — 编译为 c-shared DLL，由 Python ctypes 直接调用。
   编译命令：go build -buildmode=c-shared -o go_preload.dll main.go
*/

/*
#include <stdlib.h>
*/
import "C"
import (
	"database/sql"
	"fmt"
	"io"
	"log"
	"os"
	"runtime/debug"
	"sync"
	"unsafe"

	_ "github.com/mattn/go-sqlite3"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common"
	"github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/common/profile"
	cvm "github.com/tencentcloud/tencentcloud-sdk-go/tencentcloud/cvm/v20170312"
)

// 模块级变量：数据库路径（由 Python 侧传入）
var gDBPath string

//export GoPreloadInit
func GoPreloadInit(dbPath *C.char, logPath *C.char) C.int {
	gDBPath = C.GoString(dbPath)

	lp := C.GoString(logPath)
	if lp != "" {
		f, err := os.OpenFile(lp, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if err == nil {
			log.SetOutput(io.MultiWriter(os.Stdout, f))
		}
	}
	log.SetFlags(log.LstdFlags)
	log.SetPrefix("[GO] ")
	log.Printf("Go DLL 已初始化, db=%s", gDBPath)
	return 0
}

//export GoPreloadAll
func GoPreloadAll(secretID *C.char, secretKey *C.char, defaultRegion *C.char) *C.char {
	defer func() {
		if err := recover(); err != nil {
			log.Printf("CRITICAL PANIC: %v\n%s", err, debug.Stack())
		}
	}()

	sid := C.GoString(secretID)
	skey := C.GoString(secretKey)
	region := C.GoString(defaultRegion)
	if region == "" {
		region = "ap-beijing"
	}

	log.Printf("收到同步请求 (Region: %s)，正在执行...", region)

	if err := runFullPreload(sid, skey, region); err != nil {
		log.Printf("同步失败: %v", err)
		errMsg := fmt.Sprintf("ERROR:%s", err.Error())
		return C.CString(errMsg)
	}

	log.Printf("同步成功完成")
	return C.CString("OK")
}

//export GoFreeString
func GoFreeString(p *C.char) {
	C.free(unsafe.Pointer(p))
}

func main() {
	// c-shared 模式要求 main 函数存在但不执行
}

func runFullPreload(secretID, secretKey, defaultRegion string) error {
	if gDBPath == "" {
		return fmt.Errorf("数据库路径未初始化，请先调用 GoPreloadInit")
	}

	db, err := sql.Open("sqlite3", gDBPath+"?_journal=WAL&_busy_timeout=5000")
	if err != nil {
		return fmt.Errorf("open db failed: %w", err)
	}
	defer db.Close()

	client, err := newCvmClient(secretID, secretKey, defaultRegion)
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

			rClient, err := newCvmClient(secretID, secretKey, rid)
			if err != nil {
				return
			}

			// 可用区
			if zResp, err := rClient.DescribeZones(cvm.NewDescribeZonesRequest()); err == nil {
				_ = syncZonesToDB(db, rid, zResp.Response.ZoneSet)
			}

			// 镜像（分页拉取所有公共镜像）
			var allImages []*cvm.Image
			var imgOffset uint64 = 0
			const imgLimit uint64 = 100
			for {
				iReq := cvm.NewDescribeImagesRequest()
				iReq.Offset = common.Uint64Ptr(imgOffset)
				iReq.Limit = common.Uint64Ptr(imgLimit)
				iReq.Filters = []*cvm.Filter{{Name: common.StringPtr("image-type"), Values: []*string{common.StringPtr("PUBLIC_IMAGE")}}}
				iResp, err := rClient.DescribeImages(iReq)
				if err != nil {
					break
				}
				allImages = append(allImages, iResp.Response.ImageSet...)
				if uint64(len(iResp.Response.ImageSet)) < imgLimit {
					break
				}
				imgOffset += imgLimit
			}
			if len(allImages) > 0 {
				_ = syncImagesToDB(db, rid, allImages)
			}
		}(regionID)
	}
	wg.Wait()

	// 3. 同步实例
	return syncInstances(db, client, defaultRegion)
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
	// 收集 API 返回的所有实例 ID，用于后续标记缺失实例
	var validIDs []string
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
			validIDs = append(validIDs, str(inst.InstanceId))
		}
		_ = tx.Commit()
		if len(resp.Response.InstanceSet) < int(limit) {
			break
		}
		offset += limit
	}

	// API 拉取完成后，将不在返回列表中的实例标记为 -1（已销毁/不存在）
	if len(validIDs) > 0 {
		placeholders := ""
		args := make([]interface{}, len(validIDs))
		for i, id := range validIDs {
			if i > 0 {
				placeholders += ","
			}
			placeholders += "?"
			args[i] = id
		}
		_, _ = db.Exec(
			"UPDATE instances SET status='-1', updated_at=strftime('%s','now') WHERE status != '-1' AND instance_id NOT IN ("+placeholders+")",
			args...,
		)
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
