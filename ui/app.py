"""
UI 应用主文件
定义主窗口类，负责窗口的创建、菜单栏、状态栏等

重要提示：
    - 窗口宽高设置在 init_ui() 方法中（第19-42行）
    - 可以通过修改窗口大小比例来调整窗口尺寸
"""
import os
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QMessageBox, QMenuBar, QMenu, QAction, QApplication, QDialog, QLabel, QPushButton, QHBoxLayout, QStatusBar
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from ui.main_window import MainWindow
from ui.styles import get_style_sheet


class CVMApp(QMainWindow):
    """
    CVM 管理应用主窗口类
    
    继承自 QMainWindow，提供主窗口框架
    包含菜单栏、状态栏和中央组件区域
    """
    
    def __init__(self):
        super().__init__()
        self.loading_timer = QTimer()
        self.loading_timer.setSingleShot(False)
        self.loading_dots = 1
        self.is_loading = False
        self.init_ui()
    
    def init_ui(self):
        """
        初始化UI界面
        
        注意：窗口宽高设置在此方法中
        """
        self.setWindowTitle("腾讯云 CVM 实例管理工具")
        
        # ========== 窗口宽高设置区域 ==========
        # 获取屏幕尺寸并自适应窗口大小
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        
        # 计算窗口大小（占屏幕的95%）
        # 修改这里的 0.95 可以调整窗口大小比例（0.5 = 50%, 0.95 = 95%）
        window_width = int(screen_width * 0.95)
        window_height = int(screen_height * 0.9)
        
        # 确保最小宽度足够显示所有按钮（至少1400像素）
        min_window_width = max(1400, int(screen_width * 0.7))
        if window_width < min_window_width:
            window_width = min_window_width
        
        # 计算窗口位置（居中）
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        # 设置窗口位置和大小
        # 参数：x坐标, y坐标, 宽度, 高度
        # 如果想固定窗口大小，可以直接写：self.setGeometry(100, 100, 1400, 900)
        self.setGeometry(x, y, window_width, window_height)
        
        # 设置最小窗口大小（确保按钮能完全显示）
        # 最小宽度至少1400像素，最小高度为屏幕的60%
        min_width = max(1400, int(screen_width * 0.7))
        min_height = int(screen_height * 0.6)
        self.setMinimumSize(min_width, min_height)
        # ========== 窗口宽高设置区域结束 ==========
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "logo.ico")
        if not os.path.exists(icon_path):
            # 兼容旧路径
            icon_path = os.path.join(os.path.dirname(__file__), "ui", "logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 应用样式（根据DPI自动调整）
        self.setStyleSheet(get_style_sheet())
        
        # 创建主窗口组件
        self.main_window = MainWindow(self)
        self.setCentralWidget(self.main_window)
        
        # 创建菜单栏（需要在main_window创建之后）
        self.create_menu_bar()
        
        # 设置状态栏
        self.status_label = QLabel('<span style="font-weight: bold; color: #2e7d32;">就绪</span> | 欢迎使用腾讯云 CVM 实例管理工具')
        self.status_label.setTextFormat(Qt.RichText)
        self.statusBar().addPermanentWidget(self.status_label)
        
        # 初始化加载动画定时器
        self.loading_timer.timeout.connect(self._update_loading_status)
        self.loading_timer.setSingleShot(False)
    
    def create_menu_bar(self):
        """
        创建菜单栏
        
        包含三个主菜单：
            - 文件菜单：刷新、设置、退出
            - 实例菜单：创建实例、批量操作
            - 帮助菜单：关于信息
        """
        menubar = self.menuBar()
        
        # ========== 文件菜单 ==========
        file_menu = menubar.addMenu("文件(&F)")
        
        # 刷新功能（快捷键：F5）
        refresh_action = QAction("刷新(&R)", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.main_window.refresh_instances)
        file_menu.addAction(refresh_action)
        
        file_menu.addSeparator()
        
        # 设置功能（快捷键：Ctrl+,）
        settings_action = QAction("设置(&S)", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.main_window.show_settings)
        file_menu.addAction(settings_action)
        
        instance_config_action = QAction("实例配置(&C)", self)
        instance_config_action.triggered.connect(self.main_window.show_instance_config)
        file_menu.addAction(instance_config_action)
        
        file_menu.addSeparator()
        
        # 退出功能（快捷键：Ctrl+Q）
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # ========== 实例菜单 ==========
        instance_menu = menubar.addMenu("实例(&I)")
        
        # 创建实例（快捷键：Ctrl+N）
        create_action = QAction("创建实例(&N)", self)
        create_action.setShortcut("Ctrl+N")
        create_action.triggered.connect(self.main_window.create_instances)
        instance_menu.addAction(create_action)
        
        instance_menu.addSeparator()
        
        # 批量操作
        start_action = QAction("批量开机(&S)", self)
        start_action.triggered.connect(self.main_window.batch_start)
        instance_menu.addAction(start_action)
        
        stop_action = QAction("批量关机(&T)", self)
        stop_action.triggered.connect(self.main_window.batch_stop)
        instance_menu.addAction(stop_action)
        
        reset_pwd_action = QAction("批量重置密码(&P)", self)
        reset_pwd_action.triggered.connect(self.main_window.batch_reset_password)
        instance_menu.addAction(reset_pwd_action)
        
        # ========== 帮助菜单 ==========
        help_menu = menubar.addMenu("帮助(&H)")
        
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def show_about(self):
        """
        显示关于对话框
        
        显示应用程序的版本信息和说明
        """
        QMessageBox.about(
            self,
            "关于",
            "<h2>腾讯云 CVM 实例管理工具</h2>"
            "<p>版本: 1.0.0</p>"
            "<p>基于腾讯云 API 的云服务器管理工具</p>"
            "<p>支持实例创建、批量操作、镜像管理等功能</p>"
            "<p><a href='https://cloud.tencent.com'>腾讯云官网</a></p>"
        )
    
    def closeEvent(self, event):
        """窗口关闭事件处理"""
        dialog = QDialog(self)
        dialog.setWindowTitle("确认退出")
        dialog.setModal(True)
        
        dialog_width = 400
        dialog_height = 150
        button_width = 100
        button_height = 35
        
        dialog.setFixedSize(dialog_width, dialog_height)
        
        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        label = QLabel("确定要退出吗？")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        button_layout.addStretch()
        
        yes_btn = QPushButton("是")
        yes_btn.setFixedSize(button_width, button_height)
        yes_btn.clicked.connect(dialog.accept)
        
        no_btn = QPushButton("否")
        no_btn.setFixedSize(button_width, button_height)
        no_btn.clicked.connect(dialog.reject)
        no_btn.setDefault(True)
        
        button_layout.addWidget(yes_btn)
        button_layout.addWidget(no_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        dialog.setStyleSheet(f"""
            QDialog {{
                background-color: white;
            }}
            QLabel {{
                font-size: 14px;
            }}
            QPushButton {{
                font-size: 14px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: #f0f0f0;
            }}
            QPushButton:hover {{
                background-color: #e0e0e0;
            }}
            QPushButton:pressed {{
                background-color: #d0d0d0;
            }}
        """)
        
        if dialog.exec_() == QDialog.Accepted:
            event.accept()
        else:
            event.ignore()
    
    def start_loading_status(self):
        """开始显示加载状态"""
        self.is_loading = True
        self.loading_dots = 0
        if self.loading_timer.isActive():
            self.loading_timer.stop()
        self._update_loading_status()
        self.loading_timer.start(300)
    
    def stop_loading_status(self):
        """停止加载状态，恢复就绪"""
        self.is_loading = False
        if self.loading_timer.isActive():
            self.loading_timer.stop()
        if hasattr(self, 'status_label'):
            self.status_label.setText('<span style="font-weight: bold; color: #2e7d32;">就绪</span> | 欢迎使用腾讯云 CVM 实例管理工具')
    
    def _update_loading_status(self):
        """更新加载状态动画"""
        if not self.is_loading:
            return
        if not hasattr(self, 'status_label'):
            return
        self.loading_dots += 1
        if self.loading_dots > 3:
            self.loading_dots = 1
        dots = "." * self.loading_dots
        self.status_label.setText(f'<span style="font-weight: bold; color: #f57c00;">加载中{dots}</span> | 欢迎使用腾讯云 CVM 实例管理工具')


