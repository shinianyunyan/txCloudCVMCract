"""
主窗口组件
定义主窗口的内容区域，包含工具栏、实例列表等

功能：
    - 显示实例统计信息
    - 提供操作按钮（刷新、创建、批量操作等）
    - 显示实例列表表格
    - 处理实例的增删改查操作
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QLineEdit, QGroupBox, QGridLayout, QFrame, QMainWindow, QSpinBox, QDialog
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont
from ui.components.instance_list import InstanceList
from ui.components.message_bar import MessageBar
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.instance_config_dialog import InstanceConfigDialog
from config.config import SECRET_ID, SECRET_KEY

# 延迟导入，避免在未安装依赖时失败
# 如果未安装 tencentcloud-sdk-python，程序仍可启动，只是功能不可用
try:
    from core.cvm_manager import CVMManager
    CVM_MANAGER_AVAILABLE = True
except ImportError:
    CVM_MANAGER_AVAILABLE = False
    CVMManager = None


class MainWindow(QWidget):
    """
    主窗口内容组件
    
    这是主窗口的中央区域，包含所有功能组件
    注意：窗口本身的宽高设置在 ui/app.py 的 CVMApp.init_ui() 方法中
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cvm_manager = None
        self.message_bar = None
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(lambda: self.refresh_instances(silent=True))
        self.init_ui()
        self.auto_refresh_on_start()
    
    def init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # 消息提示条（浮动窗口，显示在主界面顶部居中）
        # 注意：MessageBar 现在是浮动窗口，不需要添加到布局中
        # 获取主窗口（CVMApp）作为父窗口
        parent_window = self.parent()
        while parent_window and not isinstance(parent_window, QMainWindow):
            parent_window = parent_window.parent()
        self.message_bar = MessageBar(parent_window if parent_window else self)
        
        # 统计信息面板
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 12px;
            }
        """)
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)
        
        self.stats_label = QLabel("实例统计: 总计 0 | 运行中 0 | 已停止 0 | 其他 0")
        self.stats_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                color: #666666;
                padding: 4px;
            }
        """)
        stats_layout.addWidget(self.stats_label)
        stats_layout.addStretch()
        
        stats_frame.setLayout(stats_layout)
        main_layout.addWidget(stats_frame)
        
        # 工具栏和搜索框
        toolbar_frame = QFrame()
        toolbar_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(8)
        
        # 左侧操作按钮组
        btn_group1 = QHBoxLayout()
        btn_group1.setSpacing(8)
        
        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setProperty("class", "")
        self.btn_refresh.clicked.connect(self.refresh_instances)
        self.btn_refresh.setToolTip("刷新实例列表 (F5)")
        
        self.count_spin = QSpinBox()
        self.count_spin.setMinimum(1)
        self.count_spin.setMaximum(100)
        self.count_spin.setValue(1)
        self.count_spin.setMaximumWidth(60)
        self.count_spin.setToolTip("创建实例数量")
        
        self.btn_create = QPushButton("➕ 创建实例")
        self.btn_create.setProperty("class", "primary")
        self.btn_create.clicked.connect(self.create_instances)
        self.btn_create.setToolTip("使用配置的参数创建实例 (Ctrl+N)")
        
        self.btn_instance_config = QPushButton("⚙ 实例配置")
        self.btn_instance_config.setProperty("class", "")
        self.btn_instance_config.clicked.connect(self.show_instance_config)
        self.btn_instance_config.setToolTip("配置创建实例的默认参数")
        
        btn_group1.addWidget(self.btn_refresh)
        btn_group1.addWidget(QLabel("数量:"))
        btn_group1.addWidget(self.count_spin)
        btn_group1.addWidget(self.btn_create)
        btn_group1.addWidget(self.btn_instance_config)
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        search_label.setStyleSheet("color: #666666; font-size: 13px;")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入实例ID或名称进行搜索...")
        self.search_input.setMinimumWidth(300)
        self.search_input.textChanged.connect(self.on_search_changed)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        
        # 右侧设置按钮
        self.btn_settings = QPushButton("⚙ 设置")
        self.btn_settings.setProperty("class", "")
        self.btn_settings.clicked.connect(self.show_settings)
        self.btn_settings.setToolTip("打开设置 (Ctrl+,)")
        
        toolbar_layout.addLayout(btn_group1)
        toolbar_layout.addStretch()
        toolbar_layout.addLayout(search_layout)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.btn_settings)
        
        toolbar_frame.setLayout(toolbar_layout)
        main_layout.addWidget(toolbar_frame)
        
        # 批量操作按钮组（放在工具栏下方，实例列表上方）
        batch_btn_frame = QFrame()
        batch_btn_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        batch_btn_layout = QHBoxLayout()
        batch_btn_layout.setSpacing(6)
        batch_btn_layout.setContentsMargins(8, 4, 8, 4)
        
        self.btn_start = QPushButton("▶ 批量开机")
        self.btn_start.setProperty("class", "success")
        self.btn_start.clicked.connect(self.batch_start)
        self.btn_start.setFixedHeight(32)
        self.btn_start.setStyleSheet("font-size: 12px; padding: 4px 12px;")
        
        self.btn_stop = QPushButton("⏸ 批量关机")
        self.btn_stop.setProperty("class", "")
        self.btn_stop.clicked.connect(self.batch_stop)
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setStyleSheet("font-size: 12px; padding: 4px 12px;")
        
        self.btn_terminate = QPushButton("🗑 销毁实例")
        self.btn_terminate.setProperty("class", "")
        self.btn_terminate.clicked.connect(self.batch_terminate)
        self.btn_terminate.setFixedHeight(32)
        self.btn_terminate.setStyleSheet("font-size: 12px; padding: 4px 12px;")
        
        self.btn_reset_pwd = QPushButton("🔑 重置密码")
        self.btn_reset_pwd.setProperty("class", "")
        self.btn_reset_pwd.clicked.connect(self.batch_reset_password)
        self.btn_reset_pwd.setFixedHeight(32)
        self.btn_reset_pwd.setStyleSheet("font-size: 12px; padding: 4px 12px;")
        
        batch_btn_layout.addWidget(self.btn_start)
        batch_btn_layout.addWidget(self.btn_stop)
        batch_btn_layout.addWidget(self.btn_terminate)
        batch_btn_layout.addWidget(self.btn_reset_pwd)
        batch_btn_layout.addStretch()
        
        batch_btn_frame.setLayout(batch_btn_layout)
        main_layout.addWidget(batch_btn_frame)
        
        # 实例列表
        list_group = QGroupBox("实例列表")
        list_group.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                font-size: 14px;
                color: #333333;
            }
        """)
        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(8, 20, 8, 8)
        
        self.instance_list = InstanceList()
        list_layout.addWidget(self.instance_list)
        
        list_group.setLayout(list_layout)
        main_layout.addWidget(list_group)
        
        main_layout.setStretchFactor(list_group, 1)
        
        self.setLayout(main_layout)
    
    def on_search_changed(self, text):
        """搜索文本变化时的处理"""
        # 这里可以实现搜索过滤功能
        # 暂时先不实现，后续可以添加
        pass
    
    def update_stats(self, instances=None):
        """更新统计信息"""
        if instances is None:
            instances = []
        
        total = len(instances)
        running = sum(1 for inst in instances if inst.get("InstanceState") == "RUNNING")
        stopped = sum(1 for inst in instances if inst.get("InstanceState") == "STOPPED")
        other = total - running - stopped
        
        self.stats_label.setText(
            f"实例统计: 总计 {total} | 运行中 {running} | 已停止 {stopped} | 其他 {other}"
        )
    
    def show_message(self, message, message_type, duration):
        """
        显示消息提示（在主界面顶部居中显示）
        
        Args:
            message: 消息内容
            message_type: 消息类型（error, warning, success, info）
            duration: 显示时长（毫秒）
        """
        from utils.utils import setup_logger
        logger = setup_logger()
        
        log_message = " ".join(message.splitlines())
        if message_type == "error":
            logger.error(f"UI消息: {log_message}")
        elif message_type == "warning":
            logger.warning(f"UI消息: {log_message}")
        elif message_type == "success":
            logger.info(f"UI消息: {log_message}")
        else:
            logger.info(f"UI消息: {log_message}")
        
        if self.message_bar:
            self.message_bar.show_message(message, message_type, duration)
    
    def auto_refresh_on_start(self):
        """启动时自动刷新实例列表"""
        if SECRET_ID and SECRET_KEY:
            self.refresh_instances(silent=True)
            self.refresh_timer.start(60000)
    
    def refresh_instances(self, silent=False):
        """刷新实例列表"""
        if not CVM_MANAGER_AVAILABLE:
            if self.refresh_timer.isActive():
                self.refresh_timer.stop()
            if not silent:
                self.show_message("请先安装依赖：pip install -r requirements.txt", "error", 5000)
            return
        
        if not self.cvm_manager:
            if not SECRET_ID or not SECRET_KEY:
                if self.refresh_timer.isActive():
                    self.refresh_timer.stop()
                if not silent:
                    self.show_message("请先配置API凭证", "warning", 5000)
                return
            try:
                self.cvm_manager = CVMManager(SECRET_ID, SECRET_KEY, None)
            except Exception as e:
                if self.refresh_timer.isActive():
                    self.refresh_timer.stop()
                if not silent:
                    self.show_message(f"无法初始化CVM管理器: {str(e)}", "error", 5000)
                return
        
        try:
            instances = self.cvm_manager.get_instances(None)
            self.instance_list.update_instances(instances)
            self.update_stats(instances)
            if self.parent():
                self.parent().statusBar().showMessage(f"已加载 {len(instances)} 个实例", 3000)
            if not silent:
                self.show_message(f"成功刷新，共{len(instances)}个实例", "success", 2000)
            if not self.refresh_timer.isActive():
                self.refresh_timer.start(60000)
        except Exception as e:
            if not silent:
                self.show_message(f"无法获取实例列表: {str(e)}", "error", 5000)
    
    def create_instances(self):
        """使用配置的参数创建实例"""
        if not CVM_MANAGER_AVAILABLE:
            self.show_message("请先安装依赖：pip install -r requirements.txt", "error", 5000)
            return
        
        if not SECRET_ID or not SECRET_KEY:
            self.show_message("请先配置API凭证（SecretId和SecretKey）", "warning", 5000)
            self.show_settings()
            return
        
        if not self.cvm_manager:
            try:
                self.cvm_manager = CVMManager(SECRET_ID, SECRET_KEY, None)
            except Exception as e:
                self.show_message(f"无法初始化CVM管理器: {str(e)}", "error", 5000)
                return
        
        from config.config_manager import get_instance_config
        
        config = get_instance_config()
        count = self.count_spin.value()
        
        if not config.get("default_region"):
            self.show_message("请先在实例配置中设置区域", "warning", 5000)
            self.show_instance_config()
            return
        
        if not config.get("default_password"):
            self.show_message("请先在实例配置中设置密码", "warning", 5000)
            self.show_instance_config()
            return
        
        try:
            result = self.cvm_manager.create(config.get("default_cpu", 2), config.get("default_memory", 4), config["default_region"], config["default_password"], config.get("default_image_id"), None, config.get("default_zone"), count)
            
            if count == 1:
                instance_id = result.get('InstanceId') or (result.get('InstanceIds', [None])[0] if result.get('InstanceIds') else None)
                self.show_message(f"实例创建成功！实例ID: {instance_id}", "success", 5000)
            else:
                instance_ids = result.get('InstanceIds', [])
                created_count = len(instance_ids)
                if created_count <= 10:
                    ids_text = "\n".join(instance_ids)
                else:
                    ids_text = "\n".join(instance_ids[:10]) + f"\n... 还有 {created_count - 10} 个"
                self.show_message(f"成功创建{created_count}个实例！\n实例ID列表:\n{ids_text}", "success", 5000)
            
            self.refresh_instances()
        except Exception as e:
            error_msg = str(e)
            self.show_message(f"无法创建实例: {error_msg}", "error", 5000)
    
    def batch_start(self):
        """批量开机"""
        if not self.cvm_manager:
            self.show_message("请先配置并刷新实例列表", "warning", 5000)
            return
        
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要操作的实例", "warning", 5000)
            return
        
        reply = QMessageBox.question(
            self,
            "确认操作",
            f"确定要启动 {len(selected_ids)} 个实例吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.cvm_manager.start(selected_ids)
                self.show_message(f"批量开机操作已提交，共{len(selected_ids)}个实例", "success", 5000)
                self.refresh_instances()
            except Exception as e:
                self.show_message(f"批量开机失败: {str(e)}", "error", 5000)
    
    def batch_stop(self):
        """批量关机"""
        if not self.cvm_manager:
            self.show_message("请先配置并刷新实例列表", "warning", 5000)
            return
        
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要操作的实例", "warning", 5000)
            return
        
        reply = QMessageBox.question(
            self,
            "确认操作",
            f"确定要停止 {len(selected_ids)} 个实例吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.cvm_manager.stop(selected_ids, False)
                self.show_message(f"批量关机操作已提交，共{len(selected_ids)}个实例", "success", 5000)
                self.refresh_instances()
            except Exception as e:
                self.show_message(f"批量关机失败: {str(e)}", "error", 5000)
    
    def batch_terminate(self):
        """批量销毁实例"""
        if not self.cvm_manager:
            self.show_message("请先配置并刷新实例列表", "warning", 5000)
            return
        
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要操作的实例", "warning", 5000)
            return
        
        reply = QMessageBox.question(
            self,
            "确认销毁",
            f"确定要销毁 {len(selected_ids)} 个实例吗？该操作不可恢复。",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.cvm_manager.terminate(selected_ids)
                self.show_message(f"销毁操作已提交，共{len(selected_ids)}个实例", "success", 5000)
                self.refresh_instances()
            except Exception as e:
                self.show_message(f"销毁实例失败: {str(e)}", "error", 5000)
    
    def batch_reset_password(self):
        """批量重置密码"""
        if not self.cvm_manager:
            self.show_message("请先配置并刷新实例列表", "warning", 5000)
            return
        
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要操作的实例", "warning", 5000)
            return
        
        is_windows = False
        try:
            instances = self.cvm_manager.get_instances(None)
            for instance in instances:
                if instance.get("InstanceId") in selected_ids:
                    platform = instance.get("Platform", "").upper()
                    if "WINDOWS" in platform:
                        is_windows = True
                        break
        except:
            pass
        
        from ui.dialogs.password_dialog import PasswordDialog
        dialog = PasswordDialog(self, is_windows)
        if dialog.exec_():
            password = dialog.get_password()
            try:
                # 检查有多少运行中的实例
                running_count = 0
                try:
                    instances = self.cvm_manager.get_instances(None)
                    for instance in instances:
                        if instance.get("InstanceId") in selected_ids and instance.get("InstanceState") == "RUNNING":
                            running_count += 1
                except:
                    pass
                
                self.cvm_manager.reset_pwd(selected_ids, password)
                from config.config_manager import get_instance_config, save_instance_config
                config = get_instance_config()
                save_instance_config(config.get("default_cpu", 2), config.get("default_memory", 4), config.get("default_region"), config.get("default_zone"), config.get("default_image_id"), password)
                
                # 更新提示信息
                if running_count > 0:
                    self.show_message(f"已重置{len(selected_ids)}个实例的密码，并自动开机{running_count}个原本运行中的实例", "success", 5000)
                else:
                    self.show_message(f"已重置{len(selected_ids)}个实例的密码", "success", 5000)
                self.refresh_instances()
            except Exception as e:
                self.show_message(f"批量重置密码失败: {str(e)}", "error", 5000)
    
    def show_settings(self):
        """显示设置对话框（API凭证设置）"""
        dialog = SettingsDialog(self)
        if dialog.exec_():
            # 重新初始化管理器（热更新，无需重启）
            if CVM_MANAGER_AVAILABLE:
                try:
                    self.cvm_manager = CVMManager(SECRET_ID, SECRET_KEY, None)
                    self.show_message("API凭证已更新", "success", 2000)
                    # 可选：自动刷新实例列表
                    # self.refresh_instances()
                except Exception as e:
                    self.show_message(f"无法初始化CVM管理器: {str(e)}", "error", 5000)
    
    def show_instance_config(self):
        """显示实例配置对话框"""
        self.btn_instance_config.setEnabled(False)
        main_app = self.parent()
        while main_app and not isinstance(main_app, QMainWindow):
            main_app = main_app.parent()
        
        if main_app and hasattr(main_app, 'start_loading_status'):
            main_app.start_loading_status()
        
        try:
            if not CVM_MANAGER_AVAILABLE:
                if main_app and hasattr(main_app, 'stop_loading_status'):
                    main_app.stop_loading_status()
                self.show_message("请先安装依赖：pip install -r requirements.txt", "error", 5000)
                self.btn_instance_config.setEnabled(True)
                return
            
            if not self.cvm_manager:
                if not SECRET_ID or not SECRET_KEY:
                    if main_app and hasattr(main_app, 'stop_loading_status'):
                        main_app.stop_loading_status()
                    self.show_message("请先配置API凭证", "warning", 5000)
                    self.show_settings()
                    self.btn_instance_config.setEnabled(True)
                    return
                try:
                    from config.config_manager import get_instance_config
                    config = get_instance_config()
                    default_region = config.get("default_region")
                    self.cvm_manager = CVMManager(SECRET_ID, SECRET_KEY, default_region)
                except Exception as e:
                    if main_app and hasattr(main_app, 'stop_loading_status'):
                        main_app.stop_loading_status()
                    self.show_message(f"无法初始化CVM管理器: {str(e)}", "error", 5000)
                    self.btn_instance_config.setEnabled(True)
                    return
            
            dialog = InstanceConfigDialog(self.cvm_manager, self)
            
            def on_config_loaded():
                if main_app and hasattr(main_app, 'stop_loading_status'):
                    main_app.stop_loading_status()
                dialog.exec_()
                if dialog.result() == QDialog.Accepted:
                    self.show_message("实例配置已保存", "success", 2000)
                self.btn_instance_config.setEnabled(True)
            
            def on_dialog_finished(result):
                if main_app and hasattr(main_app, 'stop_loading_status'):
                    main_app.stop_loading_status()
                self.btn_instance_config.setEnabled(True)
            
            dialog.finished.connect(on_dialog_finished)
            
            if hasattr(dialog, 'load_thread'):
                dialog.load_thread.finished.connect(on_config_loaded)
            else:
                if main_app and hasattr(main_app, 'stop_loading_status'):
                    main_app.stop_loading_status()
                dialog.exec_()
                if dialog.result() == QDialog.Accepted:
                    self.show_message("实例配置已保存", "success", 2000)
                self.btn_instance_config.setEnabled(True)
        except Exception as e:
            if main_app and hasattr(main_app, 'stop_loading_status'):
                main_app.stop_loading_status()
            self.show_message(f"打开配置对话框失败: {str(e)}", "error", 5000)
            self.btn_instance_config.setEnabled(True)
    
    def _on_dialog_finished(self, main_app):
        """对话框关闭回调"""
        self.btn_instance_config.setEnabled(True)
        if main_app and hasattr(main_app, 'stop_loading_status'):
            main_app.stop_loading_status()


