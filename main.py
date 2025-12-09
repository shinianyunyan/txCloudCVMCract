"""
主程序入口文件
启动图形用户界面

运行方式：
    python main.py

功能：
    - 初始化 PyQt5 应用程序
    - 启用高DPI支持（适配高分辨率屏幕）
    - 创建并显示主窗口
"""
import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon

# 启用高DPI支持（适配高分辨率屏幕）
# 这可以让程序在高分辨率屏幕上显示更清晰
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

from ui.app import CVMApp
from config.config_manager import ensure_config_file

if __name__ == "__main__":
    ensure_config_file()
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
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


