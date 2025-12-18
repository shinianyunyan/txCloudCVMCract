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
import atexit
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QIcon
from utils.utils import setup_logger
from core.preload import preload_reference_data, stop_go_server

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
    # 注册退出时清理 Go 预加载服务的钩子
    atexit.register(stop_go_server)
    
    # 创建 Qt 应用实例
    app = QApplication(sys.argv)
    app.setApplicationName("腾讯云CVM管理工具")
    # 设置应用级图标（影响任务栏图标）
    icon_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "logo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 显示加载窗口
    from PyQt5.QtWidgets import QSplashScreen, QLabel, QWidget, QVBoxLayout
    from PyQt5.QtCore import Qt, QTimer
    
    # 创建简单的加载提示窗口
    splash_widget = QWidget()
    splash_widget.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.SplashScreen | Qt.FramelessWindowHint)
    splash_widget.setStyleSheet("background-color: white;")
    splash_widget.setFixedSize(400, 150)
    
    layout = QVBoxLayout()
    layout.setContentsMargins(20, 20, 20, 20)
    splash_label = QLabel("正在初始化，请稍候...", splash_widget)
    splash_label.setAlignment(Qt.AlignCenter)
    splash_label.setStyleSheet("""
        QLabel {
            font-size: 16px;
            color: #333;
        }
    """)
    layout.addWidget(splash_label)
    splash_widget.setLayout(layout)
    
    # 居中显示
    screen = QApplication.primaryScreen()
    screen_geometry = screen.geometry()
    splash_widget.move(
        (screen_geometry.width() - splash_widget.width()) // 2,
        (screen_geometry.height() - splash_widget.height()) // 2
    )
    splash_widget.show()
    app.processEvents()  # 强制刷新显示
    
    # 在显示主窗口前完成预加载
    logger = setup_logger()
    logger.info("启动时预加载配置数据...")
    
    # 更新加载提示
    def update_splash_text(text):
        splash_label.setText(text)
        app.processEvents()
    
    try:
        update_splash_text("正在连接 Go 服务...")
        preload_reference_data()
        update_splash_text("预加载完成")
        logger.info("预加载完成")
    except Exception as e:
        update_splash_text("预加载失败，将使用缓存数据")
        logger.warning(f"预加载失败，将使用缓存数据: {e}")
    
    # 短暂延迟后关闭加载窗口，让用户看到完成提示
    QTimer.singleShot(500, splash_widget.close)
    app.processEvents()
    
    # 显示主窗口
    window = CVMApp()
    window.show()
    
    sys.exit(app.exec_())

