"""
通用工具函数集合。

包含：
    - 日志记录器初始化。
    - 密码合规校验。
    - 区域/状态名称映射。
    - 预留的实例信息格式化入口。
"""
import logging
import os
import sys
from typing import List, Dict, Any, Tuple
from datetime import datetime


def get_app_dir() -> str:
    """获取应用程序的「可写数据」根目录（数据库、日志等持久性文件）。
    
    - 源码运行时：项目根目录
    - PyInstaller 打包后：exe 所在目录
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_resource_dir() -> str:
    """获取应用程序的「只读资源」根目录（DLL、图标、SVG 等打包资源）。
    
    - 源码运行时：项目根目录
    - PyInstaller --onefile 打包后：_MEIPASS 临时解压目录
    """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def setup_logger(name: str = "CVM_Manager", log_file: str = "cvm_manager.log", level: str = "INFO") -> logging.Logger:
    """
    创建（或复用）带文件与控制台输出的日志记录器。
    
    Args:
        name: 记录器名称。
        log_file: 日志文件路径。
        level: 日志级别（INFO/DEBUG/...）。
    
    Returns:
        logging.Logger: 已配置好的记录器。
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # 文件处理器，完整持久化日志（写入 exe 所在目录）
    if not os.path.isabs(log_file):
        log_file = os.path.join(get_app_dir(), log_file)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台处理器，输出到终端
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 统一格式：时间-名称-级别-内容
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def generate_password(length: int = 16) -> str:
    """
    生成符合腾讯云要求的随机复杂密码。
    保证包含大写、小写、数字、特殊字符各至少 1 个。
    """
    import secrets
    import string
    
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    special = "!@#$%^&*_+-="
    
    # 保证每类至少 1 个
    pwd = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    # 剩余用全字符集随机填充
    all_chars = upper + lower + digits + special
    pwd += [secrets.choice(all_chars) for _ in range(length - 4)]
    
    # 打乱顺序
    result = list(pwd)
    secrets.SystemRandom().shuffle(result)
    return "".join(result)


def validate_password(password: str) -> Tuple[bool, str]:
    """
    校验密码是否符合腾讯云要求。

    规则：
        - 长度 8~30。
        - 至少包含大写、小写、数字、特殊字符中的 3 类。
    返回 (是否合规, 错误信息)。
    """
    if not password:
        return False, "密码不能为空"
    
    if len(password) < 8:
        return False, "密码长度至少8位"
    
    if len(password) > 30:
        return False, "密码长度不能超过30位"
    
    # 检查是否包含大小写字母、数字和特殊字符中的至少三种
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    types_count = sum([has_upper, has_lower, has_digit, has_special])
    
    if types_count < 3:
        return False, "密码必须包含大小写字母、数字和特殊字符中的至少三种"
    
    return True, ""


def format_instance_info(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    预留实例信息格式化入口，便于后续扩展。

    当前直接返回原数据，可按需要在此整理字段。
    """
    # 如需新增展示字段或转换格式，可在此扩展
    return instance


def get_region_name(region: str) -> str:
    """根据区域代码返回对应中文名，未知则回退原值。"""
    region_map = {
        "ap-beijing": "北京",
        "ap-shanghai": "上海",
        "ap-guangzhou": "广州",
        "ap-chengdu": "成都",
        "ap-chongqing": "重庆",
        "ap-nanjing": "南京",
        "ap-shenzhen-fsi": "深圳金融",
        "ap-shanghai-fsi": "上海金融",
        "ap-beijing-fsi": "北京金融",
        "ap-hongkong": "香港",
        "ap-singapore": "新加坡",
        "ap-mumbai": "孟买",
        "ap-seoul": "首尔",
        "ap-bangkok": "曼谷",
        "ap-tokyo": "东京",
        "na-siliconvalley": "硅谷",
        "na-ashburn": "弗吉尼亚",
        "na-toronto": "多伦多",
        "sa-saopaulo": "圣保罗",
        "eu-frankfurt": "法兰克福",
        "eu-moscow": "莫斯科",
    }
    return region_map.get(region, region)


def get_instance_status_name(status: str) -> str:
    """根据实例状态码返回中文名，未知则回退原值。"""
    status_map = {
        "PENDING": "创建中",
        "LAUNCH_FAILED": "创建失败",
        "RUNNING": "运行中",
        "STOPPED": "已关机",
        "STARTING": "开机中",
        "STOPPING": "关机中",
        "REBOOTING": "重启中",
        "SHUTDOWN": "已销毁",
        "TERMINATING": "销毁中",
    }
    return status_map.get(status, status)

