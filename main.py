"""
主程序入口。

职责：
    - 设置高 DPI 相关环境变量和 Qt 属性，确保高分屏显示清晰。
    - 初始化 PyQt5 应用对象并设置应用基础信息（名称、组织、图标）。
    - 创建并显示主窗口 `CVMApp`。

运行方式：
    python main.py
"""
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QIcon
from utils.utils import setup_logger
from utils.db_manager import get_db
try:
    from config.config_manager import get_api_config
except ImportError:
    get_api_config = None

# 启用高 DPI 支持，让界面在高分屏上保持清晰
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
# 必须在 QApplication 创建前设置
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from ui.app import CVMApp
from config.config_manager import ensure_config_file


def preload_reference_data():
    """
    启动阶段同步拉取实例配置所需的基础数据，并落库到 SQLite。

    包含：区域、可用区、公共镜像（按区域），避免进入实例配置界面时再等待远程查询。
    使用多线程并发处理各区域，加快预加载速度。
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    logger = setup_logger()
    try:
        from core.cvm_manager import CVMManager
    except Exception as exc:  # 依赖缺失时直接跳过预加载，保持应用可启动
        logger.warning(f"跳过预加载：无法导入依赖（{exc}）")
        return

    api_config = get_api_config() if get_api_config else {}
    secret_id = api_config.get("secret_id")
    secret_key = api_config.get("secret_key")
    default_region = api_config.get("default_region", "ap-beijing")
    
    if not secret_id or not secret_key:
        logger.warning("跳过预加载：未配置腾讯云 API 凭证")
        return

    try:
        cvm_manager = CVMManager(secret_id, secret_key, default_region)
    except Exception as exc:
        logger.error(f"预加载失败：无法初始化 CVM 管理器（{exc}）")
        return

    db = get_db()
    try:
        regions = cvm_manager.get_regions()
        db.replace_regions(regions)
    except Exception as exc:
        logger.error(f"预加载失败：拉取区域列表异常（{exc}）")
        return

    def load_region_data(region_info):
        """单个线程处理一个区域：查询可用区和镜像"""
        region_id = region_info.get("Region") or region_info.get("region")
        if not region_id:
            return None
        
        # 每个线程使用独立的 CVMManager 实例（客户端非线程安全）
        try:
            thread_manager = CVMManager(secret_id, secret_key, region_id)
        except Exception as exc:
            logger.error(f"预加载警告：区域 {region_id} 初始化失败（{exc}）")
            return region_id
        
        result = {"region": region_id, "zones": None, "images": None, "error": None}
        
        # 查询可用区
        try:
            zones = thread_manager.get_zones(region_id)
            db.replace_zones(region_id, zones)
            result["zones"] = len(zones) if zones else 0
        except Exception as exc:
            logger.error(f"预加载警告：区域 {region_id} 可用区同步失败（{exc}）")
            result["error"] = f"可用区失败: {str(exc)}"
        
        # 查询镜像
        try:
            images = thread_manager.get_images("PUBLIC_IMAGE", limit=100)
            db.replace_images(region_id, "PUBLIC_IMAGE", images)
            result["images"] = len(images) if images else 0
        except Exception as exc:
            logger.error(f"预加载警告：区域 {region_id} 公共镜像同步失败（{exc}）")
            if result["error"]:
                result["error"] += f"; 镜像失败: {str(exc)}"
            else:
                result["error"] = f"镜像失败: {str(exc)}"
        
        return result

    # 使用线程池并发处理各区域（最多10个线程）
    logger.info(f"开始并发预加载 {len(regions)} 个区域的数据...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(load_region_data, region): region for region in regions or []}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                result = future.result()
                if result:
                    logger.info(f"区域 {result['region']} 预加载完成 (可用区: {result.get('zones', 0)}, 镜像: {result.get('images', 0)}) [{completed}/{len(regions)}]")
            except Exception as exc:
                region_info = futures[future]
                region_id = region_info.get("Region") or region_info.get("region")
                logger.error(f"预加载异常：区域 {region_id} 处理失败（{exc}）")
    
    # 按照官方接口要求，DescribeInstances 需指定 Region，这里只同步默认区域实例
    # 若配置文件中有自定义默认区域，则优先使用
    try:
        from config.config_manager import get_instance_config
        cfg = get_instance_config()
        default_region = cfg.get("default_region", default_region)
    except Exception:
        pass
    
    # 预加载实例列表：先标记所有实例为-1，然后查询API，存在的实例会更新status
    try:
        db = get_db()
        logger.info("预加载：标记所有现有实例为删除状态")
        db.mark_all_instances_as_deleted()
        
        cvm_manager._init_client(default_region)
        cvm_manager.get_instances(default_region)
        logger.info(f"默认区域 {default_region} 实例列表已同步到本地数据库")
    except Exception as exc:
        logger.error(f"预加载警告：默认区域 {default_region} 实例同步失败（{exc}）")
    
    logger.info("所有区域预加载完成")


if __name__ == "__main__":
    ensure_config_file()
    # 同步预拉取实例配置所需数据，确保实例配置界面直接读库
    preload_reference_data()
    # 创建 Qt 应用实例并开启高 DPI 相关属性
    app = QApplication(sys.argv)
    app.setApplicationName("腾讯云CVM管理工具")
    app.setOrganizationName("CVMManager")
    icon_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "logo.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(os.path.dirname(__file__), "ui", "logo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    window = CVMApp()
    window.show()
    sys.exit(app.exec_())

