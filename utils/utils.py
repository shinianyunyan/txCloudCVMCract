"""
工具函数模块
提供通用的工具函数

包含功能：
    - 日志配置
    - 密码验证
    - 数据格式化
    - 区域和状态名称转换
"""
import logging
import os
from typing import List, Dict, Any, Tuple
from datetime import datetime


def setup_logger(name: str = "CVM_Manager", log_file: str = "cvm_manager.log", level: str = "INFO") -> logging.Logger:
    """
    设置日志记录器
    
    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别
    
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 格式化
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
    验证密码是否符合腾讯云要求
    
    Args:
        password: 待验证的密码
    
    Returns:
        tuple[bool, str]: (是否有效, 错误信息)
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
    格式化实例信息，便于显示
    
    Args:
        instance: 原始实例信息
    
    Returns:
        Dict[str, Any]: 格式化后的实例信息
    """
    # 这里可以根据实际API返回的数据结构进行格式化
    return instance


def get_region_name(region: str) -> str:
    """
    获取区域的中文名称
    
    Args:
        region: 区域代码
    
    Returns:
        str: 区域中文名称
    """
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
    """
    获取实例状态的中文名称
    
    Args:
        status: 状态代码
    
    Returns:
        str: 状态中文名称
    """
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

