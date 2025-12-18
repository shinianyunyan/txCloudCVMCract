"""
本地 SQLite 缓存管理。

职责：
- 维护实例列表的本地持久化，供 UI 轮询读取。
- 缓存区域、镜像、实例配置等数据，减少重复 API 调用。
- 提供线程安全的基本增删改查接口。
"""
import os
import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional

_db_singleton = None
_lock = threading.Lock()


class DBManager:
    """SQLite 管理器，封装实例与配置缓存的读写。"""

    def __init__(self, db_path: Optional[str] = None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
        os.makedirs(base_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(base_dir, "cvm_cache.db")
        self._init_tables()

    def _connect(self):
        # 启用 WAL 模式，提高并发读写性能，减少锁竞争
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # 设置 WAL 模式和 busy_timeout，减少与 Go 服务的锁竞争
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")  # 5秒超时
        return conn

    def _init_tables(self):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS instances (
                    instance_id TEXT PRIMARY KEY,
                    instance_name TEXT,
                    status TEXT,
                    region TEXT,
                    zone TEXT,
                    instance_type TEXT,
                    image_id TEXT,
                    image_name TEXT,
                    platform TEXT,
                    cpu INTEGER,
                    memory INTEGER,
                    private_ip TEXT,
                    public_ip TEXT,
                    expired_time TEXT,
                    created_time TEXT,
                    updated_at INTEGER
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    secret_id TEXT,
                    secret_key TEXT,
                    default_region TEXT,
                    default_cpu INTEGER,
                    default_memory INTEGER,
                    default_zone TEXT,
                    default_image_id TEXT,
                    default_password TEXT,
                    default_disk_type TEXT,
                    default_disk_size INTEGER,
                    default_bandwidth INTEGER,
                    default_bandwidth_charge TEXT,
                    updated_at INTEGER
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS regions (
                    region TEXT PRIMARY KEY,
                    region_name TEXT,
                    region_state TEXT,
                    updated_at INTEGER
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS zones (
                    zone TEXT PRIMARY KEY,
                    region TEXT,
                    zone_name TEXT,
                    zone_state TEXT,
                    updated_at INTEGER
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    image_id TEXT,
                    image_name TEXT,
                    image_type TEXT,
                    platform TEXT,
                    region TEXT,
                    created_time TEXT,
                    updated_at INTEGER,
                    PRIMARY KEY (image_id, region)
                )
                """
            )
            # 兼容旧库，补充缺失列
            cur.execute("PRAGMA table_info(instances)")
            cols = [r[1] for r in cur.fetchall()]
            if "cpu" not in cols:
                cur.execute("ALTER TABLE instances ADD COLUMN cpu INTEGER")
            if "memory" not in cols:
                cur.execute("ALTER TABLE instances ADD COLUMN memory INTEGER")
            if "image_name" not in cols:
                cur.execute("ALTER TABLE instances ADD COLUMN image_name TEXT")
            if "platform" not in cols:
                cur.execute("ALTER TABLE instances ADD COLUMN platform TEXT")
            if "expired_time" not in cols:
                cur.execute("ALTER TABLE instances ADD COLUMN expired_time TEXT")
            # 配置表迁移：如存在旧 config_cache 记录则迁移至 config 表
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
            has_config_table = cur.fetchone() is not None
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_cache'")
            has_config_cache = cur.fetchone() is not None
            if has_config_table and has_config_cache:
                self._migrate_config_cache_to_config(cur)
            conn.commit()

    # ---------------- 实例缓存 ----------------
    def upsert_instances(self, instances: List[Dict[str, Any]]):
        """批量写入/更新实例信息。"""
        with _lock, self._connect() as conn:
            cur = conn.cursor()
            for inst in instances or []:
                cur.execute(
                    """
                    INSERT INTO instances (instance_id, instance_name, status, region, zone, instance_type, image_id, image_name, platform, cpu, memory, private_ip, public_ip, expired_time, created_time, updated_at)
                    VALUES (:instance_id, :instance_name, :status, :region, :zone, :instance_type, :image_id, :image_name, :platform, :cpu, :memory, :private_ip, :public_ip, :expired_time, :created_time, strftime('%s','now'))
                    ON CONFLICT(instance_id) DO UPDATE SET
                        instance_name=excluded.instance_name,
                        status=excluded.status,
                        region=excluded.region,
                        zone=excluded.zone,
                        instance_type=excluded.instance_type,
                        image_id=excluded.image_id,
                        image_name=excluded.image_name,
                        platform=excluded.platform,
                        cpu=excluded.cpu,
                        memory=excluded.memory,
                        private_ip=excluded.private_ip,
                        public_ip=excluded.public_ip,
                        expired_time=COALESCE(excluded.expired_time, instances.expired_time),
                        created_time=COALESCE(instances.created_time, excluded.created_time),
                        updated_at=strftime('%s','now')
                    """,
                    {
                        "instance_id": inst.get("InstanceId") or inst.get("instance_id"),
                        "instance_name": inst.get("InstanceName") or inst.get("instance_name"),
                        "status": inst.get("InstanceState") or inst.get("status"),
                        "region": inst.get("Region") or inst.get("region"),
                        "zone": inst.get("Zone") or inst.get("zone"),
                        "instance_type": inst.get("InstanceType") or inst.get("instance_type"),
                        "image_id": inst.get("ImageId") or inst.get("image_id"),
                        "image_name": inst.get("ImageName") or inst.get("image_name"),
                        "platform": inst.get("Platform") or inst.get("platform"),
                        "cpu": inst.get("CPU") or inst.get("cpu"),
                        "memory": inst.get("Memory") or inst.get("memory"),
                        "private_ip": self._first_ip(inst.get("PrivateIpAddresses") or inst.get("private_ip")),
                        "public_ip": self._first_ip(inst.get("PublicIpAddresses") or inst.get("public_ip")),
                        "expired_time": inst.get("ExpiredTime") or inst.get("expired_time"),
                        "created_time": inst.get("CreatedTime") or inst.get("created_time"),
                    },
                )
            conn.commit()

    def mark_all_instances_as_deleted(self):
        """标记所有实例为删除状态（status = '-1'），用于预加载前的清理。"""
        with _lock, self._connect() as conn:
            conn.execute("UPDATE instances SET status='-1', updated_at=strftime('%s','now') WHERE status != '-1'")
            conn.commit()

    def update_instance_status(self, instance_id: str, status: str, public_ip: Optional[str] = None, private_ip: Optional[str] = None):
        """更新实例状态及可选 IP。"""
        with _lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE instances
                SET status = ?, public_ip = COALESCE(?, public_ip), private_ip = COALESCE(?, private_ip), updated_at = strftime('%s','now')
                WHERE instance_id = ?
                """,
                (status, public_ip, private_ip, instance_id),
            )
            conn.commit()

    def soft_delete_missing(self, valid_ids: List[str]):
        """将不在有效列表中的实例标记为删除（status = '-1'），避免直接删除记录。"""
        if valid_ids is None:
            return
        if len(valid_ids) == 0:
            return
        with _lock, self._connect() as conn:
            placeholders = ",".join("?" for _ in valid_ids)
            conn.execute(
                f"UPDATE instances SET status='-1', updated_at=strftime('%s','now') WHERE status != '-1' AND instance_id NOT IN ({placeholders})",
                valid_ids,
            )
            conn.commit()

    def list_instances(self) -> List[Dict[str, Any]]:
        """返回未标记删除的实例列表（过滤 status = '-1'）。"""
        # [优化]：UI 线程频繁调用此方法。如果此时后台正在写库（加了锁），
        # UI 线程不应该等待，而是直接返回空或报错，避免卡死界面。
        locked = _lock.acquire(blocking=False)
        if not locked:
            # 如果拿不到锁，说明后台正在大规模写入，UI 线程直接跳过本次刷新
            return [] 
        
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT instance_id, instance_name, status, region, zone, instance_type, image_id, image_name, platform, cpu, memory, private_ip, public_ip, created_time, expired_time FROM instances WHERE status != '-1' OR status IS NULL ORDER BY updated_at DESC"
                )
                rows = cur.fetchall()
                return [dict(row) for row in rows]
        finally:
            _lock.release()

    def get_instances(self, instance_ids: List[str]) -> List[Dict[str, Any]]:
        """按 ID 查询实例记录。"""
        if not instance_ids:
            return []
            
        locked = _lock.acquire(blocking=False)
        if not locked:
            return []

        try:
            with self._connect() as conn:
                placeholders = ",".join("?" for _ in instance_ids)
                cur = conn.cursor()
                cur.execute(
                    f"SELECT instance_id, instance_name, status, region, zone, instance_type, image_id, image_name, platform, cpu, memory, private_ip, public_ip, created_time, expired_time FROM instances WHERE instance_id IN ({placeholders})",
                    instance_ids,
                )
                return [dict(row) for row in cur.fetchall()]
        finally:
            _lock.release()

    # ---------------- 配置结构化存储 ----------------
    def _migrate_config_cache_to_config(self, cur):
        """从旧 config_cache 迁移到 config 表（仅在表存在时调用）。"""
        try:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config_cache'")
            if not cur.fetchone():
                return
            cur.execute("SELECT value FROM config_cache WHERE key = 'config'")
            row = cur.fetchone()
            if not row:
                return
            cfg = json.loads(row["value"])
            api = (cfg or {}).get("api", {}) if isinstance(cfg, dict) else {}
            inst = (cfg or {}).get("instance", {}) if isinstance(cfg, dict) else {}
            cur.execute(
                """
                INSERT INTO config (id, secret_id, secret_key, default_region, default_cpu, default_memory,
                                    default_zone, default_image_id, default_password, default_disk_type,
                                    default_disk_size, default_bandwidth, default_bandwidth_charge, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(id) DO UPDATE SET
                    secret_id=excluded.secret_id,
                    secret_key=excluded.secret_key,
                    default_region=excluded.default_region,
                    default_cpu=excluded.default_cpu,
                    default_memory=excluded.default_memory,
                    default_zone=excluded.default_zone,
                    default_image_id=excluded.default_image_id,
                    default_password=excluded.default_password,
                    default_disk_type=excluded.default_disk_type,
                    default_disk_size=excluded.default_disk_size,
                    default_bandwidth=excluded.default_bandwidth,
                    default_bandwidth_charge=excluded.default_bandwidth_charge,
                    updated_at=excluded.updated_at
                """,
                (
                    api.get("secret_id"),
                    api.get("secret_key"),
                    api.get("default_region"),
                    inst.get("default_cpu"),
                    inst.get("default_memory"),
                    inst.get("default_zone"),
                    inst.get("default_image_id"),
                    inst.get("default_password"),
                    inst.get("default_disk_type"),
                    inst.get("default_disk_size"),
                    inst.get("default_bandwidth"),
                    inst.get("default_bandwidth_charge"),
                ),
            )
            # 迁移后可选清理旧记录
            cur.execute("DELETE FROM config_cache WHERE key = 'config'")
        except Exception:
            pass

    def get_config_struct(self, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """读取结构化配置，若不存在返回 default。"""
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT secret_id, secret_key, default_region, default_cpu, default_memory, default_zone,
                       default_image_id, default_password, default_disk_type, default_disk_size,
                       default_bandwidth, default_bandwidth_charge
                  FROM config
                 WHERE id = 1
                """
            )
            row = cur.fetchone()
            if not row:
                return default or {}
            d = dict(row)
            return {
                "api": {
                    "secret_id": d.get("secret_id"),
                    "secret_key": d.get("secret_key"),
                    "default_region": d.get("default_region"),
                },
                "instance": {
                    "default_cpu": d.get("default_cpu"),
                    "default_memory": d.get("default_memory"),
                    "default_region": d.get("default_region"),
                    "default_zone": d.get("default_zone"),
                    "default_image_id": d.get("default_image_id"),
                    "default_password": d.get("default_password"),
                    "default_disk_type": d.get("default_disk_type"),
                    "default_disk_size": d.get("default_disk_size"),
                    "default_bandwidth": d.get("default_bandwidth"),
                    "default_bandwidth_charge": d.get("default_bandwidth_charge"),
                },
            }

    def set_config_struct(self, config: Dict[str, Any]):
        """保存结构化配置到 config 表。"""
        api = (config or {}).get("api", {}) if isinstance(config, dict) else {}
        inst = (config or {}).get("instance", {}) if isinstance(config, dict) else {}
        with _lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO config (id, secret_id, secret_key, default_region, default_cpu, default_memory,
                                    default_zone, default_image_id, default_password, default_disk_type,
                                    default_disk_size, default_bandwidth, default_bandwidth_charge, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(id) DO UPDATE SET
                    secret_id=excluded.secret_id,
                    secret_key=excluded.secret_key,
                    default_region=excluded.default_region,
                    default_cpu=excluded.default_cpu,
                    default_memory=excluded.default_memory,
                    default_zone=excluded.default_zone,
                    default_image_id=excluded.default_image_id,
                    default_password=excluded.default_password,
                    default_disk_type=excluded.default_disk_type,
                    default_disk_size=excluded.default_disk_size,
                    default_bandwidth=excluded.default_bandwidth,
                    default_bandwidth_charge=excluded.default_bandwidth_charge,
                    updated_at=excluded.updated_at
                """,
                (
                    api.get("secret_id"),
                    api.get("secret_key"),
                    api.get("default_region"),
                    inst.get("default_cpu"),
                    inst.get("default_memory"),
                    inst.get("default_zone"),
                    inst.get("default_image_id"),
                    inst.get("default_password"),
                    inst.get("default_disk_type"),
                    inst.get("default_disk_size"),
                    inst.get("default_bandwidth"),
                    inst.get("default_bandwidth_charge"),
                ),
            )
            conn.commit()
    # ---------------- 区域/可用区/镜像 ----------------
    def replace_regions(self, regions: List[Dict[str, Any]]):
        """全量覆盖区域列表。"""
        with _lock, self._connect() as conn:
            conn.execute("DELETE FROM regions")
            for r in regions or []:
                conn.execute(
                    """
                    INSERT INTO regions (region, region_name, region_state, updated_at)
                    VALUES (?, ?, ?, strftime('%s','now'))
                    """,
                    (r.get("Region"), r.get("RegionName"), r.get("RegionState")),
                )
            conn.commit()

    def list_regions(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT region, region_name, region_state FROM regions ORDER BY region")
            return [dict(row) for row in cur.fetchall()]

    def replace_zones(self, region: str, zones: List[Dict[str, Any]]):
        """覆盖某区域的可用区列表。"""
        if not region:
            return
        with _lock, self._connect() as conn:
            conn.execute("DELETE FROM zones WHERE region = ?", (region,))
            for z in zones or []:
                conn.execute(
                    """
                    INSERT INTO zones (zone, region, zone_name, zone_state, updated_at)
                    VALUES (?, ?, ?, ?, strftime('%s','now'))
                    """,
                    (z.get("Zone"), region, z.get("ZoneName"), z.get("ZoneState")),
                )
            conn.commit()

    def list_zones(self, region: Optional[str]) -> List[Dict[str, Any]]:
        if not region:
            return []
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT zone, region, zone_name, zone_state FROM zones WHERE region = ? ORDER BY zone",
                (region,),
            )
            return [dict(row) for row in cur.fetchall()]

    def replace_images(self, region: str, image_type: str, images: List[Dict[str, Any]]):
        """覆盖某区域某类型的镜像列表。"""
        if not region or not image_type:
            return
        with _lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM images WHERE region = ? AND image_type = ?", (region, image_type))
            batch = []
            for img in images or []:
                batch.append(
                    (
                        img.get("ImageId"),
                        img.get("ImageName"),
                        img.get("ImageType") or image_type,
                        img.get("Platform"),
                        region,
                        img.get("CreatedTime"),
                    )
                )
            if batch:
                cur.executemany(
                    """
                    INSERT INTO images (image_id, image_name, image_type, platform, region, created_time, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'))
                    """,
                    batch,
                )
            conn.commit()

    def list_images(self, region: Optional[str], image_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """按区域（可选类型）查询镜像。"""
        if not region:
            return []
        with self._connect() as conn:
            cur = conn.cursor()
            if image_type:
                cur.execute(
                    "SELECT image_id, image_name, image_type, platform, region, created_time FROM images WHERE region = ? AND image_type = ? ORDER BY image_name",
                    (region, image_type),
                )
            else:
                cur.execute(
                    "SELECT image_id, image_name, image_type, platform, region, created_time FROM images WHERE region = ? ORDER BY image_name",
                    (region,),
                )
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                result.append(
                    {
                        "ImageId": d.get("image_id"),
                        "ImageName": d.get("image_name"),
                        "ImageType": d.get("image_type"),
                        "Platform": d.get("platform"),
                        "Region": d.get("region"),
                        "CreatedTime": d.get("created_time"),
                    }
                )
            return result

    def batch_sync_data(self, regions=None, zones_map=None, images_map=None, instances=None):
        """
        在一个事务中同步所有云端数据。
        这是减少磁盘 IO 和锁竞争的最优方案。
        """
        with _lock, self._connect() as conn:
            cur = conn.cursor()
            
            # 1. 同步区域
            if regions:
                cur.execute("DELETE FROM regions")
                for r in regions:
                    cur.execute(
                        "INSERT INTO regions (region, region_name, region_state, updated_at) VALUES (?, ?, ?, strftime('%s','now'))",
                        (r.get("Region") or r.get("region"), r.get("RegionName") or r.get("region_name"), r.get("RegionState") or r.get("region_state"))
                    )

            # 2. 同步可用区
            if zones_map:
                # zones_map: {region: [zone_info, ...]}
                for rid, zones in zones_map.items():
                    cur.execute("DELETE FROM zones WHERE region = ?", (rid,))
                    for z in zones or []:
                        cur.execute(
                            "INSERT INTO zones (zone, region, zone_name, zone_state, updated_at) VALUES (?, ?, ?, ?, strftime('%s','now'))",
                            (z.get("Zone") or z.get("zone"), rid, z.get("ZoneName") or z.get("zone_name"), z.get("ZoneState") or z.get("zone_state"))
                        )

            # 3. 同步镜像
            if images_map:
                # images_map: {region: [image_info, ...]}
                for rid, images in images_map.items():
                    cur.execute("DELETE FROM images WHERE region = ? AND image_type = ?", (rid, "PUBLIC_IMAGE"))
                    batch = []
                    for img in images or []:
                        batch.append((
                            img.get("ImageId") or img.get("image_id"),
                            img.get("ImageName") or img.get("image_name"),
                            img.get("ImageType") or "PUBLIC_IMAGE",
                            img.get("Platform") or img.get("platform"),
                            rid,
                            img.get("CreatedTime") or img.get("created_time")
                        ))
                    if batch:
                        cur.executemany(
                            "INSERT INTO images (image_id, image_name, image_type, platform, region, created_time, updated_at) VALUES (?, ?, ?, ?, ?, ?, strftime('%s','now'))",
                            batch
                        )

            # 4. 同步实例 (先统一标记删除，再写入/更新)
            if instances is not None:
                cur.execute("UPDATE instances SET status='-1', updated_at=strftime('%s','now') WHERE status != '-1'")
                batch = []
                for inst in instances:
                    # 获取 IP 逻辑复用
                    private_ip = self._first_ip(inst.get("PrivateIpAddresses") or inst.get("private_ip"))
                    public_ip = self._first_ip(inst.get("PublicIpAddresses") or inst.get("public_ip"))
                    
                    batch.append((
                        inst.get("InstanceId") or inst.get("instance_id"),
                        inst.get("InstanceName") or inst.get("instance_name"),
                        inst.get("InstanceState") or inst.get("status"),
                        inst.get("Region") or inst.get("region"),
                        inst.get("Zone") or (inst.get("Placement", {}).get("Zone") if isinstance(inst.get("Placement"), dict) else inst.get("zone")),
                        inst.get("InstanceType") or inst.get("instance_type"),
                        inst.get("ImageId") or inst.get("image_id"),
                        inst.get("ImageName") or inst.get("image_name"),
                        inst.get("Platform") or inst.get("platform"),
                        inst.get("CPU") or inst.get("cpu"),
                        inst.get("Memory") or inst.get("memory"),
                        private_ip,
                        public_ip,
                        inst.get("ExpiredTime") or inst.get("expired_time"),
                        inst.get("CreatedTime") or inst.get("created_time")
                    ))
                
                if batch:
                    cur.executemany(
                        """
                        INSERT INTO instances (instance_id, instance_name, status, region, zone, instance_type, image_id, image_name, platform, cpu, memory, private_ip, public_ip, expired_time, created_time, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                        ON CONFLICT(instance_id) DO UPDATE SET
                            instance_name=excluded.instance_name,
                            status=excluded.status,
                            region=excluded.region,
                            zone=excluded.zone,
                            instance_type=excluded.instance_type,
                            image_id=excluded.image_id,
                            image_name=excluded.image_name,
                            platform=excluded.platform,
                            cpu=excluded.cpu,
                            memory=excluded.memory,
                            private_ip=excluded.private_ip,
                            public_ip=excluded.public_ip,
                            expired_time=COALESCE(excluded.expired_time, instances.expired_time),
                            created_time=COALESCE(instances.created_time, excluded.created_time),
                            updated_at=strftime('%s','now')
                        """,
                        batch
                    )

            conn.commit()

    # ---------------- 工具 ----------------
    @staticmethod
    def _first_ip(value):
        if isinstance(value, list) and value:
            return value[0]
        if isinstance(value, str):
            return value
        return None


def get_db() -> DBManager:
    """获取全局单例 DBManager。"""
    global _db_singleton
    with _lock:
        if _db_singleton is None:
            _db_singleton = DBManager()
        return _db_singleton


