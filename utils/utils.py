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
from typing import List, Dict, Any, Tuple
from datetime import datetime


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
    
    # 文件处理器，完整持久化日志
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

