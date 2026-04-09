"""
预加载辅助模块。

职责：
    - 提供 `preload_reference_data`，在应用启动或用户手动触发时，
      通过 Go DLL（ctypes 调用）高并发拉取区域、可用区、公共镜像与实例列表，
      并写入本地 SQLite 数据库。
"""

import ctypes
import os
import sys
import time

from utils.utils import setup_logger
from utils.db_manager import get_db

try:
    from config.config_manager import get_api_config
except ImportError:
    get_api_config = None

# Go DLL 单例
_go_dll = None
_go_initialized = False


def _get_dll_path():
    """获取 go_preload.dll 的路径，兼容开发环境和 PyInstaller 打包。"""
    from utils.utils import get_resource_dir
    return os.path.join(get_resource_dir(), "go_preload", "go_preload.dll")


def _load_go_dll():
    """加载 Go DLL 并初始化（仅调用一次）。"""
    global _go_dll, _go_initialized
    if _go_initialized:
        return _go_dll

    dll_path = _get_dll_path()
    if not os.path.exists(dll_path):
        raise RuntimeError(f"Go DLL 不存在: {dll_path}")

    logger = setup_logger()
    logger.info(f"加载 Go DLL: {dll_path}")
    _go_dll = ctypes.CDLL(dll_path)

    # 设置函数签名
    _go_dll.GoPreloadInit.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _go_dll.GoPreloadInit.restype = ctypes.c_int

    _go_dll.GoPreloadAll.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
    _go_dll.GoPreloadAll.restype = ctypes.c_void_p

    _go_dll.GoFreeString.argtypes = [ctypes.c_void_p]
    _go_dll.GoFreeString.restype = None

    # 初始化：传入数据库路径和日志路径
    db = get_db()
    db_path = db.db_path.encode("utf-8")
    from utils.utils import get_app_dir
    log_path = os.path.join(get_app_dir(), "cvm_manager.log").encode("utf-8")

    ret = _go_dll.GoPreloadInit(db_path, log_path)
    if ret != 0:
        raise RuntimeError(f"Go DLL 初始化失败 (code={ret})")

    _go_initialized = True
    logger.info("Go DLL 已加载并初始化")
    return _go_dll


def stop_go_server():
    """兼容旧接口 — DLL 模式下无需额外清理。"""
    pass


def _preload_via_go():
    """通过 ctypes 调用 Go DLL 执行全量数据同步。"""
    logger = setup_logger()
    if not get_api_config:
        raise RuntimeError("无法获取 API 配置")
    api_config = get_api_config() or {}
    secret_id = api_config.get("secret_id") or ""
    secret_key = api_config.get("secret_key") or ""
    default_region = api_config.get("default_region", "ap-beijing")

    if not secret_id or not secret_key:
        raise RuntimeError("未配置 API 凭证")

    dll = _load_go_dll()

    logger.info(f"调用 Go DLL 同步 (region={default_region})...")
    start_time = time.time()

    result_ptr = dll.GoPreloadAll(
        secret_id.encode("utf-8"),
        secret_key.encode("utf-8"),
        default_region.encode("utf-8"),
    )

    # 读取返回值（result_ptr 是 c_void_p 整数，保留原始 Go 指针）
    result = ctypes.cast(result_ptr, ctypes.c_char_p).value.decode("utf-8")
    # 用原始指针释放 Go 分配的内存
    dll.GoFreeString(result_ptr)

    duration = time.time() - start_time
    logger.info(f"Go DLL 响应时间: {duration:.2f}秒, 结果: {result}")

    if result.startswith("ERROR:"):
        raise RuntimeError(f"Go 同步失败: {result[6:]}")


def preload_reference_data():
    """
    同步拉取实例配置所需的基础数据，并落库到 SQLite。

    所有高负载任务（API 调用、数据库写入）均由 Go DLL 处理。
    Python 仅负责触发调用，不执行任何重负载操作。
    """
    logger = setup_logger()

    try:
        _preload_via_go()
        logger.info("预加载完成：Go DLL 已处理所有数据同步")
        return
    except Exception as e:
        logger.error(f"Go 预加载失败: {e}")
        logger.warning("跳过预加载：Go DLL 不可用，将使用缓存数据")
        raise


