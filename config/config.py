"""
配置文件
用于存储腾讯云 API 凭证和默认配置

配置方式：
    1. 通过环境变量配置（推荐）
       设置环境变量：TENCENT_SECRET_ID 和 TENCENT_SECRET_KEY
    2. 通过UI界面配置（热更新，无需重启）
       在程序运行时，点击"设置"按钮进行配置
    3. 通过配置文件（config.json，热更新，无需重启）

注意：配置会从 config.json 文件优先读取，支持热更新
"""
import os

try:
    from config.config_manager import get_api_config
    api_config = get_api_config()
    SECRET_ID = api_config.get("secret_id") or os.getenv("TENCENT_SECRET_ID", None)
    SECRET_KEY = api_config.get("secret_key") or os.getenv("TENCENT_SECRET_KEY", None)
    DEFAULT_REGION = api_config.get("default_region") or os.getenv("TENCENT_DEFAULT_REGION", "ap-beijing")
except ImportError:
    SECRET_ID = os.getenv("TENCENT_SECRET_ID", None)
    SECRET_KEY = os.getenv("TENCENT_SECRET_KEY", None)
    DEFAULT_REGION = os.getenv("TENCENT_DEFAULT_REGION", "ap-beijing")

API_ENDPOINT = "cvm.tencentcloudapi.com"
DEFAULT_CPU = 2
DEFAULT_MEMORY = 4
LOG_LEVEL = "INFO"
LOG_FILE = "cvm_manager.log"


