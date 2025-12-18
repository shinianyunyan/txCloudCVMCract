"""
预加载辅助模块。

职责：
    - 提供 `preload_reference_data`，在应用启动或用户手动触发时，
      统一拉取区域、可用区、公共镜像与实例列表，并写入本地数据库。
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
import subprocess
import time

import requests

from utils.utils import setup_logger
from utils.db_manager import get_db

try:
    from config.config_manager import get_api_config
except ImportError:
    get_api_config = None

try:
    from core.cvm_manager import CVMManager
except Exception:  # 依赖缺失时，保持模块可导入
    CVMManager = None


GO_PRELOAD_URL = "http://127.0.0.1:8088/preload_all"

# 由当前 Python 进程启动的 Go 预加载子进程句柄（仅用于退出时清理）
_GO_PROC = None


def _ensure_go_server_running(logger):
    """
    确保 Go 预加载服务已经运行。
    注意：此函数在后台线程中执行，所有阻塞操作都在后台线程中。
    """
    # 1. 快速检查服务是否可用（最多尝试2次）
    for _ in range(2):
        try:
            requests.get(GO_PRELOAD_URL.replace("/preload_all", "/health"), timeout=0.5)
            return  # 服务已运行
        except Exception:
            pass  # 服务不可用，继续启动流程
    
    # 2. 检查可执行文件
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    exe_path = os.path.join(base_dir, "go_preload", "go_preload_server.exe")
    
    if not os.path.exists(exe_path):
        raise RuntimeError(f"Go 服务文件不存在: {exe_path}")

    # 3. 启动进程（非阻塞）
    logger.info(f"正在后台启动 Go 服务: {exe_path}")
    try:
        # 使用绝对路径和独立的工作目录，解决 WinError 193
        subprocess.Popen(
            [exe_path],
            cwd=os.path.dirname(exe_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        raise RuntimeError(f"启动 Go 服务进程失败: {e}")

    # 4. 等待服务就绪（最多等 5 秒，但使用更短的检查间隔）
    # 注意：time.sleep() 在后台线程中执行，不会阻塞UI线程
    start_time = time.time()
    check_count = 0
    while time.time() - start_time < 5:
        try:
            requests.get(GO_PRELOAD_URL.replace("/preload_all", "/health"), timeout=0.5)
            logger.info("Go 预加载服务已就绪")
            return
        except Exception:
            check_count += 1
            # 使用较短的等待时间，减少阻塞感
            time.sleep(0.3 if check_count < 5 else 0.5)
    
    raise RuntimeError("Go 预加载服务启动超时（5秒）")


def stop_go_server():
    """
    在程序退出时调用，停止由当前 Python 进程启动的 Go 预加载服务。
    仅在 _ensure_go_server_running 中成功启动后才会生效，不会影响手动启动的服务。
    """
    global _GO_PROC
    proc = _GO_PROC
    _GO_PROC = None
    if not proc:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
    except Exception:
        pass


def _preload_via_go():
    """
    使用 Go 预加载服务。
    Go 负责：高并发 API 调用 + 数据库写入。
    Python 负责：仅触发请求。
    
    注意：此函数在后台线程中执行，但 requests.post() 是同步阻塞调用。
    虽然网络I/O会释放GIL，但为了确保UI流畅，我们使用较短的超时和重试机制。
    """
    logger = setup_logger()
    if not get_api_config:
        raise RuntimeError("无法获取 API 配置")
    api_config = get_api_config() or {}
    secret_id = api_config.get("secret_id") or ""
    secret_key = api_config.get("secret_key") or ""
    default_region = api_config.get("default_region", "ap-beijing")

    if not secret_id or not secret_key:
        raise RuntimeError("未配置 API 凭证")

    payload = {
        "secret_id": secret_id,
        "secret_key": secret_key,
        "default_region": default_region,
    }

    logger.info(f"调用 Go 全能同步接口: {GO_PRELOAD_URL}")
    
    # 确保 Go 服务正在运行（在后台线程中执行，不会阻塞UI）
    try:
        # 先快速检查服务是否可用（超时1秒）
        requests.get(GO_PRELOAD_URL.replace("/preload_all", "/health"), timeout=1)
        logger.info("Go 服务已运行，直接发送请求")
    except Exception:
        # 服务不可用，尝试启动（这个过程在后台线程中，不会阻塞UI）
        logger.info("Go 服务未运行，正在启动...")
        _ensure_go_server_running(logger)
    
    # 发送预加载请求，使用较长的超时（Go服务需要时间处理）
    # 重要：这个调用在后台线程中执行，requests.post() 在网络I/O时会释放GIL，
    # 理论上不会阻塞UI线程。但如果仍然卡顿，可能是DNS解析或其他系统调用导致的。
    logger.info("正在发送预加载请求到 Go 服务（后台线程，不应阻塞UI）...")
    request_start_time = time.time()
    try:
        resp = requests.post(GO_PRELOAD_URL, json=payload, timeout=120)
        request_duration = time.time() - request_start_time
        logger.info(f"Go 服务响应时间: {request_duration:.2f}秒")
    except requests.exceptions.Timeout:
        raise RuntimeError("Go 同步服务响应超时（120秒）")
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"无法连接到 Go 服务: {e}")
    except Exception as e:
        raise RuntimeError(f"调用 Go 服务失败: {e}")

    if resp.status_code != 200:
        raise RuntimeError(f"Go 同步服务异常: {resp.status_code}")

    res_json = resp.json()
    if not res_json.get("success"):
        msg = res_json.get("message", "unknown error")
        raise RuntimeError(f"Go 同步失败: {msg}")

    total_duration = time.time() - request_start_time
    logger.info(f"Go 侧已完成全量数据抓取与写库操作（总耗时: {total_duration:.2f}秒）")


def preload_reference_data():
    """
    同步拉取实例配置所需的基础数据，并落库到 SQLite。

    所有高负载任务（API 调用、数据库写入）均由 Go 服务处理。
    Python 仅负责触发 HTTP 请求，不执行任何重负载操作。
    """
    logger = setup_logger()

    # 仅通过 Go 服务触发预加载任务（所有高负载逻辑在 Go 中执行）
    try:
        _preload_via_go()
        logger.info("预加载完成：Go 服务已处理所有数据同步")
        return
    except Exception as e:
        # Go 服务不可用时，记录错误但不执行 Python 回退逻辑
        # 因为 Python 回退逻辑包含大量数据库写入操作，会导致 UI 卡顿
        logger.error(f"Go 预加载服务不可用或调用失败: {e}")
        logger.warning("跳过预加载：所有高负载任务已迁移至 Go 服务，Python 不再执行回退逻辑")
        raise  # 重新抛出异常，让调用方知道预加载失败


