"""
配置管理模块（结构化存储，基于 SQLite，不使用独立本地配置文件）。

职责：
    - 定义配置的默认结构（API 与实例默认参数）。
    - 通过 utils.db_manager 提供的结构化存储接口进行读写。
    - 为其它模块提供简洁的 get_* / save_* 调用入口。
"""

import os
from typing import Dict, Any

from utils.db_manager import get_db

# API 端点常量（给 SDK 使用）
API_ENDPOINT = "cvm.tencentcloudapi.com"


def get_default_config() -> Dict[str, Any]:
    """获取默认配置结构。"""
    return {
        "api": {
            "secret_id": None,
            "secret_key": None,
            "default_region": "ap-beijing",
        },
        "instance": {
            "default_cpu": 2,
            "default_memory": 4,
            "default_region": "ap-beijing",
            "default_zone": None,
            "default_image_id": None,
            "default_password": None,
            "default_disk_type": "CLOUD_PREMIUM",
            "default_disk_size": 50,
            "default_bandwidth": 10,
            "default_bandwidth_charge": "TRAFFIC_POSTPAID_BY_HOUR",
        },
    }


def ensure_config_file() -> bool:
    """
    兼容旧调用：确保数据库中存在配置记录。

    Returns:
        bool: 如果是首次初始化（写入了默认配置）返回 True，否则 False。
    """
    db = get_db()
    existing = db.get_config_struct()
    if not existing:
        default_config = get_default_config()
        db.set_config_struct(default_config)
        return True
    return False


def load_config() -> Dict[str, Any]:
    """
    从数据库加载完整配置；如不存在则写入默认后再返回。
    """
    db = get_db()
    default_config = get_default_config()
    cfg = db.get_config_struct(default_config)
    if not cfg:
        db.set_config_struct(default_config)
        return default_config

    # 浅复制 + 分段合并，保证新增字段有默认值
    merged = default_config.copy()
    merged.update(cfg)
    if "api" in cfg:
        merged["api"].update(cfg["api"])
    if "instance" in cfg:
        merged["instance"].update(cfg["instance"])
    return merged


def save_config(config: Dict[str, Any]) -> bool:
    """保存完整配置到数据库。"""
    try:
        db = get_db()
        db.set_config_struct(config)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False


def get_api_config() -> Dict[str, Any]:
    """获取 API 配置子树。"""
    config = load_config()
    return config.get("api", {})


def save_api_config(secret_id: str, secret_key: str, default_region: str) -> bool:
    """
    保存 API 配置到数据库，并同步到进程环境变量。
    """
    config = load_config()
    config["api"] = {
        "secret_id": secret_id,
        "secret_key": secret_key,
        "default_region": default_region,
    }

    # 同步到环境变量，便于 SDK 或其它脚本直接复用
    os.environ["TENCENT_SECRET_ID"] = secret_id
    os.environ["TENCENT_SECRET_KEY"] = secret_key
    os.environ["TENCENT_DEFAULT_REGION"] = default_region

    return save_config(config)


def get_instance_config() -> Dict[str, Any]:
    """获取实例默认配置子树。"""
    config = load_config()
    return config.get("instance", {})


def save_instance_config(
    default_cpu: int,
    default_memory: int,
    default_region: str,
    default_zone: str,
    default_image_id: str,
    default_password: str,
    default_disk_type: str = "CLOUD_PREMIUM",
    default_disk_size: int = 50,
    default_bandwidth: int = 10,
    default_bandwidth_charge: str = "TRAFFIC_POSTPAID_BY_HOUR",
) -> bool:
    """保存实例默认配置到数据库。"""
    config = load_config()
    config["instance"] = {
        "default_cpu": default_cpu,
        "default_memory": default_memory,
        "default_region": default_region,
        "default_zone": default_zone,
        "default_image_id": default_image_id,
        "default_password": default_password,
        "default_disk_type": default_disk_type,
        "default_disk_size": default_disk_size,
        "default_bandwidth": default_bandwidth,
        "default_bandwidth_charge": default_bandwidth_charge,
    }
    return save_config(config)


