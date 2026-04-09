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
    
    # 创建 Qt 应用实例
    app = QApplication(sys.argv)
    app.setApplicationName("腾讯云CVM管理工具")
    # 设置应用级图标（影响任务栏图标）
    from utils.utils import get_resource_dir
    icon_path = os.path.join(get_resource_dir(), "ui", "assets", "logo.ico")
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
    
    # 点动画定时器
    splash_dots = [0]  # 用列表以便在闭包中修改
    splash_base_text = ["正在初始化，请稍候"]
    
    def _update_splash_dots():
        splash_dots[0] = (splash_dots[0] % 3) + 1
        splash_label.setText(splash_base_text[0] + "." * splash_dots[0])
    
    splash_timer = QTimer()
    splash_timer.setInterval(350)
    splash_timer.timeout.connect(_update_splash_dots)
    splash_timer.start()
    
    # 在显示主窗口前完成预加载（使用后台线程，保持动画流畅）
    logger = setup_logger()
    logger.info("启动时预加载配置数据...")
    
    # 更新加载提示（同时更新动画基础文本）
    def update_splash_text(text):
        splash_base_text[0] = text
        splash_dots[0] = 0
        splash_label.setText(text + ".")
        app.processEvents()
    
    import threading
    preload_done = threading.Event()
    preload_error = [None]
    
    def _run_preload():
        try:
            preload_reference_data()
        except Exception as e:
            preload_error[0] = e
        finally:
            preload_done.set()
    
    update_splash_text("正在同步云端数据")
    preload_thread = threading.Thread(target=_run_preload, daemon=True)
    preload_thread.start()
    
    # 等待预加载完成，同时保持事件循环运转（动画不卡）
    while not preload_done.is_set():
        app.processEvents()
        preload_done.wait(0.05)  # 50ms 间隔，兼顾响应速度和 CPU
    
    if preload_error[0]:
        update_splash_text("预加载失败，将使用缓存数据")
        logger.warning(f"预加载失败，将使用缓存数据: {preload_error[0]}")
    else:
        update_splash_text("预加载完成")
        logger.info("预加载完成")
    
    # 停止动画，短暂延迟后关闭加载窗口
    splash_timer.stop()
    QTimer.singleShot(500, splash_widget.close)
    app.processEvents()
    
    # 显示主窗口
    window = CVMApp()
    window.show()
    
    sys.exit(app.exec_())

