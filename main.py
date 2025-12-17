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
from core.preload import preload_reference_data

# 启用高 DPI 支持，让界面在高分屏上保持清晰
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
# 必须在 QApplication 创建前设置
QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from ui.app import CVMApp
from config.config_manager import ensure_config_file


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

