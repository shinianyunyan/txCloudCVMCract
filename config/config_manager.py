"""
配置管理模块
"""
import os
import json


CONFIG_FILE = "config.json"


def get_config_path():
    """获取配置文件路径"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    return os.path.join(project_root, CONFIG_FILE)


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
    """确保配置文件存在，不存在则创建默认配置文件"""
    config_path = get_config_path()
    if not os.path.exists(config_path):
        default_config = get_default_config()
        save_config(default_config)
        return True
    return False


def load_config():
    """加载配置文件，如果不存在则创建默认配置文件"""
    config_path = get_config_path()
    default_config = get_default_config()
    
    if not os.path.exists(config_path):
        save_config(default_config)
        return default_config
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        merged_config = default_config.copy()
        merged_config.update(config)
        if "api" in config:
            merged_config["api"].update(config["api"])
        if "instance" in config:
            merged_config["instance"].update(config["instance"])
        return merged_config
    except json.JSONDecodeError:
        print(f"配置文件格式错误，将使用默认配置并重新创建")
        save_config(default_config)
        return default_config
    except Exception as e:
        print(f"加载配置文件失败: {e}，将使用默认配置")
        return default_config


def save_config(config):
    """保存配置文件"""
    try:
        config_path = get_config_path()
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"保存配置文件失败: {e}")
        return False


def get_api_config():
    """获取API配置"""
    config = load_config()
    return config.get("api", {})


def save_api_config(secret_id, secret_key, default_region):
    """保存API配置"""
    config = load_config()
    config["api"] = {"secret_id": secret_id, "secret_key": secret_key, "default_region": default_region}
    os.environ["TENCENT_SECRET_ID"] = secret_id
    os.environ["TENCENT_SECRET_KEY"] = secret_key
    os.environ["TENCENT_DEFAULT_REGION"] = default_region
    try:
        import sys
        if 'config.config' in sys.modules:
            m = sys.modules['config.config']
            m.SECRET_ID = secret_id
            m.SECRET_KEY = secret_key
            m.DEFAULT_REGION = default_region
    except:
        pass
    return save_config(config)


def get_instance_config():
    """获取实例默认配置"""
    config = load_config()
    return config.get("instance", {})


def save_instance_config(default_cpu, default_memory, default_region, default_zone, default_image_id, default_password, default_disk_type="CLOUD_PREMIUM", default_disk_size=50, default_bandwidth=10, default_bandwidth_charge="TRAFFIC_POSTPAID_BY_HOUR"):
    """保存实例默认配置"""
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
