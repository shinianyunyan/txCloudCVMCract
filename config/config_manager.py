"""
配置管理模块（结构化存储，落库，不使用本地文件）。
"""
import os
from utils.db_manager import get_db

# API 端点常量
API_ENDPOINT = "cvm.tencentcloudapi.com"


def get_default_config():
    """获取默认配置"""
    return {
        "api": {
            "secret_id": None,
            "secret_key": None,
            "default_region": "ap-beijing"
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
            "default_bandwidth_charge": "TRAFFIC_POSTPAID_BY_HOUR"
        }
    }


def ensure_config_file():
    """兼容旧调用：确保数据库中存在配置。"""
    db = get_db()
    existing = db.get_config_struct()
    if not existing:
        default_config = get_default_config()
        db.set_config_struct(default_config)
        return True
    return False


def load_config():
    """从数据库加载配置，不存在则写入默认后再返回。"""
    db = get_db()
    default_config = get_default_config()
    cfg = db.get_config_struct(default_config)
    if not cfg:
        db.set_config_struct(default_config)
        return default_config
    merged = default_config.copy()
    merged.update(cfg)
    if "api" in cfg:
        merged["api"].update(cfg["api"])
    if "instance" in cfg:
        merged["instance"].update(cfg["instance"])
    return merged


def save_config(config):
    """保存配置到数据库"""
    try:
        db = get_db()
        db.set_config_struct(config)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False


def get_api_config():
    """获取API配置"""
    config = load_config()
    return config.get("api", {})


def save_api_config(secret_id, secret_key, default_region):
    """保存API配置（落库）"""
    config = load_config()
    config["api"] = {"secret_id": secret_id, "secret_key": secret_key, "default_region": default_region}
    os.environ["TENCENT_SECRET_ID"] = secret_id
    os.environ["TENCENT_SECRET_KEY"] = secret_key
    os.environ["TENCENT_DEFAULT_REGION"] = default_region
    return save_config(config)


def get_instance_config():
    """获取实例默认配置"""
    config = load_config()
    return config.get("instance", {})


def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):
    """保存实例默认配置（落库）"""
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
        "default_bandwidth_charge": default_bandwidth_charge
    }
    return save_config(config)



def get_instance_config():

    """获取实例默认配置"""

    config = load_config()

    return config.get("instance", {})





def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):

    """保存实例默认配置（落库）"""
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

        "default_bandwidth_charge": default_bandwidth_charge

    }

    return save_config(config)





def get_instance_config():

    """获取实例默认配置"""

    config = load_config()

    return config.get("instance", {})





def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):

    """保存实例默认配置（落库）"""
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

        "default_bandwidth_charge": default_bandwidth_charge

    }

    return save_config(config)





def get_instance_config():

    """获取实例默认配置"""

    config = load_config()

    return config.get("instance", {})





def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):

    """保存实例默认配置（落库）"""
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

        "default_bandwidth_charge": default_bandwidth_charge

    }

    return save_config(config)





def get_instance_config():

    """获取实例默认配置"""

    config = load_config()

    return config.get("instance", {})





def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):

    """保存实例默认配置（落库）"""
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

        "default_bandwidth_charge": default_bandwidth_charge

    }

    return save_config(config)





def get_instance_config():

    """获取实例默认配置"""

    config = load_config()

    return config.get("instance", {})





def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):

    """保存实例默认配置（落库）"""
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

        "default_bandwidth_charge": default_bandwidth_charge

    }

    return save_config(config)





def get_instance_config():

    """获取实例默认配置"""

    config = load_config()

    return config.get("instance", {})





def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):

    """保存实例默认配置（落库）"""
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

        "default_bandwidth_charge": default_bandwidth_charge

    }

    return save_config(config)





def get_instance_config():

    """获取实例默认配置"""

    config = load_config()

    return config.get("instance", {})





def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):

    """保存实例默认配置（落库）"""
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

        "default_bandwidth_charge": default_bandwidth_charge

    }

    return save_config(config)


