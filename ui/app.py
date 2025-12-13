"""
应用主窗口模块。

主要职责：
    - 提供 `CVMApp`，承载主界面、菜单栏和状态栏。
    - 初始化窗口尺寸、样式与主业务组件。
    - 管理加载状态展示与退出确认对话框。
"""
import os
import logging
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QMessageBox, QMenuBar, QMenu, QAction, QApplication, QDialog, QLabel, QPushButton, QHBoxLayout, QStatusBar
from PyQt5.QtCore import Qt, QTimer, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QIcon
from ui.main_window import MainWindow
from ui.styles import get_style_sheet

class Worker(QObject):
    """
    通用后台任务执行器。

    将耗时函数放入独立线程，避免阻塞主界面。
    """
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        import logging
        logger = logging.getLogger("CVM_Manager")
        func_name = getattr(self.func, '__name__', str(self.func))
        
        # 根据函数名推断任务类型
        task_desc = func_name
        if 'create' in func_name.lower() or 'create_task' in func_name:
            task_desc = "创建实例"
        elif 'terminate' in func_name.lower():
            task_desc = "销毁实例"
        elif 'start' in func_name.lower():
            task_desc = "启动实例"
        elif 'stop' in func_name.lower():
            task_desc = "停止实例"
        elif 'reset' in func_name.lower():
            task_desc = "重置密码"
        
        logger.info(f"[Worker.run 被调用] 任务: {task_desc}, 函数名: {func_name}")
        try:
            logger.info(f"开始执行: {task_desc}")
            result = self.func(*self.args, **self.kwargs)
            logger.info(f"执行完成: {task_desc}")
            self.finished.emit(result)
        except Exception as e:
            logger.error(f"执行失败: {task_desc}, 错误: {str(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            self.error.emit(str(e))


class CVMApp(QMainWindow):
    """
    CVM 管理应用主窗口。
    
    继承 QMainWindow，负责：
        - 初始化主界面和尺寸。
        - 创建菜单栏、状态栏。
        - 承载业务主界面 MainWindow。
    """
    
    def __init__(self):
        super().__init__()
        self.loading_timer = QTimer()
        self.loading_timer.setSingleShot(True)  # 单次定时，回调内自行续约
        self.loading_dots = 1
        self.is_loading = False
        self._bg_threads = []  # 保存后台线程引用，防止被GC
        self.init_ui()
    
    def init_ui(self):
        """
        初始化界面元素：
            - 依据屏幕尺寸设置窗口大小和最小尺寸。
            - 应用统一样式。
            - 嵌入主业务窗口并创建菜单与状态栏。
        """
        self.setWindowTitle("腾讯云 CVM 实例管理工具")
        # 依据屏幕尺寸计算窗口大小与位置，保证在大屏下保持足够宽度
        screen = QApplication.primaryScreen()
        screen_geometry = screen.geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()
        
        # 默认使用屏幕宽度 95%、高度 90%，兼顾视野与可用空间
        window_width = int(screen_width * 0.95)
        window_height = int(screen_height * 0.9)
        
        # 确保主界面控件不拥挤：宽度至少 1400 像素，高度不低于屏幕 60%
        min_window_width = max(1400, int(screen_width * 0.7))
        if window_width < min_window_width:
            window_width = min_window_width
        
        # 居中显示
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        self.setGeometry(x, y, window_width, window_height)
        
        min_width = max(1400, int(screen_width * 0.7))
        min_height = int(screen_height * 0.6)
        self.setMinimumSize(min_width, min_height)
        
        # 设置窗口图标，兼容旧路径
        icon_path = os.path.join(os.path.dirname(__file__), "ui", "assets", "logo.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "ui", "logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 应用自定义样式（内部已考虑 DPI 缩放）
        self.setStyleSheet(get_style_sheet())
        
        # 嵌入主业务窗口
        self.main_window = MainWindow(self)
        self.setCentralWidget(self.main_window)
        
        # 初始化菜单栏（依赖 main_window 方法）
        self.create_menu_bar()
        
        # 配置状态栏初始文案
        self.status_label = QLabel('<span style="font-weight: bold; color: #2e7d32;">就绪</span> | 欢迎使用腾讯云 CVM 实例管理工具')
        self.status_label.setTextFormat(Qt.RichText)
        self.statusBar().addPermanentWidget(self.status_label)
        
        # 初始化加载动画定时器
        self.loading_timer.timeout.connect(self._update_loading_status)
        self.loading_timer.setSingleShot(False)
    
    def create_menu_bar(self):
        """
        创建菜单栏：
            - 文件：刷新、设置、实例配置、退出。
            - 实例：创建实例、批量开关机、批量重置密码。
            - 帮助：关于。
        """
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")
        
        # 刷新（F5）
        refresh_action = QAction("刷新(&R)", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.main_window.refresh_instances)
        file_menu.addAction(refresh_action)
        
        file_menu.addSeparator()
        
        # 设置（Ctrl+,）
        settings_action = QAction("设置(&S)", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.main_window.show_settings)
        file_menu.addAction(settings_action)
        
        instance_config_action = QAction("实例配置(&C)", self)
        instance_config_action.triggered.connect(self.main_window.show_instance_config)
        file_menu.addAction(instance_config_action)
        
        file_menu.addSeparator()
        
        # 退出（Ctrl+Q）
        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 实例菜单
        instance_menu = menubar.addMenu("实例(&I)")
        
        # 创建实例（Ctrl+N）
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
        
        # 帮助菜单
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
        
        dialog_width = 300
        dialog_height = 150
        button_width = 80
        button_height = 25
        
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
            # 等待所有后台线程完成
            import logging
            logger = logging.getLogger("CVM_Manager")
            if self._bg_threads:
                logger.info(f"等待 {len(self._bg_threads)} 个后台线程完成...")
                # 请求所有线程退出
                for thread in self._bg_threads[:]:  # 使用切片复制，避免迭代时修改列表
                    if thread.isRunning():
                        thread.quit()
                        thread.wait(3000)  # 等待最多3秒
                        if thread.isRunning():
                            logger.warning(f"线程 {thread} 未在3秒内完成，强制终止")
                            thread.terminate()
                            thread.wait(1000)  # 再等待1秒
                self._bg_threads.clear()
                logger.info("所有后台线程已清理")
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
        # 循环 1~3 个点，定时器每次触发都会刷新
        self.loading_dots = (self.loading_dots % 3) + 1
        dots = "." * self.loading_dots
        self.status_label.setText(f'<span style="font-weight: bold; color: #f57c00;">加载中{dots}</span> | 欢迎使用腾讯云 CVM 实例管理工具')
        # 若仍处于加载状态，则续约下一次动画更新
        if self.is_loading:
            self.loading_timer.start(300)

    def run_in_background(self, func, callback=None, auto_stop=True, err_callback=None, use_loading=True, *args, **kwargs):
        """
        在独立线程运行耗时任务，避免阻塞 UI。

        Args:
            func: 耗时函数
            callback: 完成后的回调（在主线程执行），入参为 func 返回值
            auto_stop: 是否在完成后自动停止加载动画
            err_callback: 异常回调（在主线程执行），入参为错误信息
            use_loading: 是否显示加载动画
        """
        import logging
        logger = logging.getLogger("CVM_Manager")
        
        func_name = getattr(func, '__name__', str(func))
        task_desc = func_name
        if 'create' in func_name.lower() or 'create_task' in func_name:
            task_desc = "创建实例"
        elif 'terminate' in func_name.lower():
            task_desc = "销毁实例"
        elif 'start' in func_name.lower():
            task_desc = "启动实例"
        elif 'stop' in func_name.lower():
            task_desc = "停止实例"
        elif 'reset' in func_name.lower():
            task_desc = "重置密码"
        
        logger.info(f"启动线程执行: {task_desc}")
        
        if use_loading:
            self.start_loading_status()

        thread = QThread()
        worker = Worker(func, *args, **kwargs)
        worker.moveToThread(thread)

        def handle_finished(result):
            logger.info(f"线程执行完成: {task_desc}")
            if auto_stop and use_loading:
                self.stop_loading_status()
            if callback:
                callback(result)
            self._bg_threads = [t for t in self._bg_threads if t is not thread]

        def handle_error(msg):
            logger.error(f"线程执行失败: {task_desc}, 错误: {msg}")
            if auto_stop and use_loading:
                self.stop_loading_status()
            if err_callback:
                err_callback(msg)
            else:
                QMessageBox.critical(self, "错误", msg)
            self._bg_threads = [t for t in self._bg_threads if t is not thread]

        # 连接信号
        worker.finished.connect(handle_finished)
        worker.error.connect(handle_error)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        
        # 使用 DirectConnection 确保 run 立即执行，避免事件循环问题
        def start_worker():
            logger.info(f"[线程事件循环启动] 任务: {task_desc}")
            worker.run()
        
        thread.started.connect(start_worker)

        self._bg_threads.append(thread)
        logger.info(f"[启动线程] 任务: {task_desc}")
        thread.start()


