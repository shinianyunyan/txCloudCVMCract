"""
主窗口内容区域。

职责：
    - 提供实例列表、统计信息与批量操作入口。
    - 负责实例创建、启动、关机、销毁、密码重置等交互逻辑。
    - 统一触发顶部消息条，反馈成功或异常信息。
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox, QGroupBox, QFrame, QMainWindow, QSpinBox, QDialog, QComboBox
from PyQt5.QtCore import Qt, QTimer
from ui.components.instance_list import InstanceList
from ui.components.message_bar import MessageBar
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.instance_config_dialog import InstanceConfigDialog
from utils.db_manager import get_db
try:
    from config.config_manager import get_api_config
except ImportError:
    get_api_config = None

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
    主窗口内容组件。
    
    作为 `CVMApp` 的中央部件，组织工具栏、统计信息和实例表格，
    并承载所有与实例相关的操作入口。
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cvm_manager = None
        self.message_bar = None
        # 每分钟同步远端到本地库
        self.refresh_timer = QTimer()
        self.refresh_timer.setInterval(60_000)
        self.refresh_timer.timeout.connect(lambda: self.refresh_instances(silent=True, sync_only=True))
        # 每4秒轮询本地数据库展示
        self.db_poll_timer = QTimer()
        self.db_poll_timer.setInterval(4_000)
        self.db_poll_timer.timeout.connect(lambda: self.refresh_instances(silent=True, sync_only=False, skip_sync=True))
        # 创建后 pending 实例监控
        self.pending_instance_ids = set()
        # 开机中实例监控
        self.starting_instance_ids = set()
        # 关机中实例监控
        self.stopping_instance_ids = set()
        self.pending_poll_timer = QTimer()
        self.pending_poll_timer.setInterval(2_000)
        self.pending_poll_timer.timeout.connect(self._poll_pending_instances)
        self.custom_images = []  # 缓存自定义镜像列表
        self.init_ui()
        self.auto_refresh_on_start()
    
    def init_ui(self):
        """
        构建主界面布局：
            - 顶部统计信息。
            - 工具栏（刷新、创建、实例配置、设置）。
            - 批量操作区（开机/关机/销毁/重置密码）。
            - 实例表格。
        """
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # 创建浮动消息条（挂在顶层主窗口，统一展示提醒）
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

        # 镜像来源选择（公共/自定义）
        self.image_source_combo = QComboBox()
        self.image_source_combo.addItem("公共镜像", "PUBLIC")
        self.image_source_combo.addItem("自定义镜像", "PRIVATE")
        self.image_source_combo.currentIndexChanged.connect(self.on_image_source_changed)
        self.image_source_combo.setToolTip("选择镜像来源")

        # 自定义镜像列表（仅当选择自定义时可用）
        self.custom_image_combo = QComboBox()
        self.custom_image_combo.setMinimumWidth(220)
        self.custom_image_combo.setEnabled(False)
        self.custom_image_combo.setToolTip("选择自定义镜像")
        
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
        btn_group1.addWidget(QLabel("镜像来源:"))
        btn_group1.addWidget(self.image_source_combo)
        btn_group1.addWidget(self.custom_image_combo)
        btn_group1.addWidget(self.btn_create)
        btn_group1.addWidget(self.btn_instance_config)
        
        # 设置按钮放在实例配置按钮旁边
        self.btn_settings = QPushButton("⚙ 设置")
        self.btn_settings.setProperty("class", "")
        self.btn_settings.clicked.connect(self.show_settings)
        self.btn_settings.setToolTip("打开设置 (Ctrl+,)")
        btn_group1.addWidget(self.btn_settings)
        
        toolbar_layout.addLayout(btn_group1)
        toolbar_layout.addStretch()
        
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
        # 初始化镜像来源状态
        self.refresh_image_selection()
    
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
        api_config = get_api_config() if get_api_config else {}
        if api_config.get("secret_id") and api_config.get("secret_key"):
            # 先同步一次并展示
            self.refresh_instances(silent=True)
            # 开启定时：1分钟远端同步，4秒本地轮询
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()
            if not self.db_poll_timer.isActive():
                self.db_poll_timer.start()
    
    def refresh_instances(self, silent=False, sync_only=False, skip_sync=False):
        """
        刷新实例列表。
        sync_only: 只拉取远端到本地，不更新UI。
        skip_sync: 跳过远端调用，直接读本地。
        """
        if not CVM_MANAGER_AVAILABLE:
            if self.refresh_timer.isActive():
                self.refresh_timer.stop()
            if not silent:
                self.show_message("请先安装依赖：pip install -r requirements.txt", "error", 5000)
            return
        
        if not self.cvm_manager:
            api_config = get_api_config() if get_api_config else {}
            secret_id = api_config.get("secret_id")
            secret_key = api_config.get("secret_key")
            if not secret_id or not secret_key:
                if self.refresh_timer.isActive():
                    self.refresh_timer.stop()
                if not silent:
                    self.show_message("请先配置API凭证", "warning", 5000)
                return
            try:
                self.cvm_manager = CVMManager(secret_id, secret_key, None)
            except Exception as e:
                if self.refresh_timer.isActive():
                    self.refresh_timer.stop()
                if not silent:
                    self.show_message(f"无法初始化CVM管理器: {str(e)}", "error", 5000)
                return
            # 刷新自定义镜像列表（在首次成功初始化后）
            self.load_custom_images()
            self.refresh_image_selection()
    
        # 同步远端到本地库
        if not skip_sync:
            try:
                # 与预加载逻辑保持一致：先标记所有实例为-1，然后查询API
                # 存在的实例会通过upsert更新status，去掉-1标识
                # 不存在的实例会保持-1状态（通过soft_delete_missing处理）
                db = get_db()
                db.mark_all_instances_as_deleted()
                self.cvm_manager.get_instances(None)
            except Exception as e:
                if not silent:
                    self.show_message(f"无法同步实例列表: {str(e)}，将使用本地缓存", "warning", 5000)
        
        if sync_only:
            return
        
        # 从本地库读取展示
        db = get_db()
        raw_instances = db.list_instances()
        from config.config_manager import get_instance_config
        cfg = get_instance_config()
        pwd = cfg.get("default_password", "")
        instances = []
        for row in raw_instances or []:
            instances.append({
                "InstanceId": row.get("instance_id") or "",
                "InstanceName": row.get("instance_name") or "",
                "InstanceState": row.get("status") or "",
                "InstanceType": row.get("instance_type") or "",
                "CPU": row.get("cpu") or "",
                "Memory": row.get("memory") or "",
                "Zone": row.get("zone") or "",
                "Region": row.get("region") or "",
                "CreatedTime": row.get("created_time") or "",
                "ExpiredTime": row.get("expired_time") or "",
                "Platform": row.get("platform") or "",
                "IpAddress": row.get("public_ip") or row.get("private_ip") or "",
                "Password": pwd
            })
        
        self.instance_list.update_instances(instances)
        self.update_stats(instances)
        if self.parent():
            self.parent().statusBar().showMessage(f"已加载 {len(instances)} 个实例", 3000)
        if not silent:
            self.show_message(f"成功刷新，共{len(instances)}个实例", "success", 2000)
        # 定时器已在构造处设置间隔，保持运行
    
    def _poll_pending_instances(self):
        """轮询新创建实例状态/IP、开机中实例状态和关机中实例状态，每2s查询一次，达成条件即停止监控"""
        has_pending = bool(self.pending_instance_ids)
        has_starting = bool(self.starting_instance_ids)
        has_stopping = bool(self.stopping_instance_ids)
        
        if not has_pending and not has_starting and not has_stopping:
            if self.pending_poll_timer.isActive():
                self.pending_poll_timer.stop()
            return
        
        if not self.cvm_manager:
            return
        
        try:
            # 合并所有需要监控的实例ID
            all_ids = list(self.pending_instance_ids | self.starting_instance_ids | self.stopping_instance_ids)
            instances = self.cvm_manager.get_instances(None, all_ids)
            
            # 处理创建中的实例（等待 RUNNING 或 IP）
            if has_pending:
                pending_completed = set()
                for inst in instances or []:
                    instance_id = inst.get("InstanceId")
                    if instance_id in self.pending_instance_ids:
                        state = inst.get("InstanceState")
                        ip = inst.get("IpAddress") or ""
                        if state == "RUNNING" or ip:
                            pending_completed.add(instance_id)
                self.pending_instance_ids.difference_update(pending_completed)
            
            # 处理开机中的实例（等待 RUNNING）
            if has_starting:
                starting_completed = set()
                for inst in instances or []:
                    instance_id = inst.get("InstanceId")
                    if instance_id in self.starting_instance_ids:
                        state = inst.get("InstanceState")
                        if state == "RUNNING":
                            starting_completed.add(instance_id)
                self.starting_instance_ids.difference_update(starting_completed)
            
            # 处理关机中的实例（等待 STOPPED）
            if has_stopping:
                stopping_completed = set()
                for inst in instances or []:
                    instance_id = inst.get("InstanceId")
                    if instance_id in self.stopping_instance_ids:
                        state = inst.get("InstanceState")
                        if state == "STOPPED":
                            stopping_completed.add(instance_id)
                self.stopping_instance_ids.difference_update(stopping_completed)
            
            # 刷新本地展示（跳过同步，避免额外 API）
            self.refresh_instances(silent=True, skip_sync=True)
            
            # 如果所有监控都完成了，停止定时器
            if not self.pending_instance_ids and not self.starting_instance_ids and not self.stopping_instance_ids and self.pending_poll_timer.isActive():
                self.pending_poll_timer.stop()
        except Exception as e:
            self.show_message(f"轮询实例状态失败: {str(e)}", "warning", 3000)

    def _set_status_text(self, rich_text: str):
        """更新主窗口状态栏文本"""
        main_app = self.window()
        if main_app and hasattr(main_app, "status_label"):
            main_app.status_label.setText(rich_text)
    
    def create_instances(self):
        """使用配置的参数创建实例"""
        if not CVM_MANAGER_AVAILABLE:
            self.show_message("请先安装依赖：pip install -r requirements.txt", "error", 5000)
            return
        
        api_config = get_api_config() if get_api_config else {}
        secret_id = api_config.get("secret_id")
        secret_key = api_config.get("secret_key")
        if not secret_id or not secret_key:
            self.show_message("请先配置API凭证（SecretId和SecretKey）", "warning", 5000)
            self.show_settings()
            return
        
        if not self.cvm_manager:
            try:
                self.cvm_manager = CVMManager(secret_id, secret_key, None)
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
        
        # 根据选择的镜像来源确定镜像ID
        image_id = config.get("default_image_id")
        source = self.image_source_combo.currentData()
        if source == "PRIVATE":
            if not self.custom_images:
                self.show_message("没有可用的自定义镜像", "warning", 3000)
                return
            image_id = self.custom_image_combo.currentData()
            if not image_id:
                self.show_message("请选择自定义镜像", "warning", 3000)
                return
        else:
            if not image_id:
                self.show_message("未在实例配置中设置公共镜像，请先配置", "warning", 3000)
                return
        
        # 立即显示"正在创建"提示（前置反馈）
        if count == 1:
            self.show_message("已提交创建请求，正在创建实例...", "info", 5000)
        else:
            self.show_message(f"已提交创建请求，正在创建 {count} 个实例...", "info", 5000)
        
        # 更新主窗口状态栏为"创建中..."
        self._set_status_text('<span style="font-weight: bold; color: #f57c00;">创建中...</span> | 正在提交创建请求')
        
        # 后台线程执行创建，避免阻塞 UI
        main_app = self.window()
        from utils.utils import setup_logger
        logger = setup_logger()
        
        def create_task():
            logger.info(
                f"[创建任务开始] region={config.get('default_region')} zone={config.get('default_zone')} "
                f"image={image_id} cpu={config.get('default_cpu', 2)} mem={config.get('default_memory', 4)} "
                f"disk={config.get('default_disk_size', 50)}({config.get('default_disk_type', 'CLOUD_PREMIUM')}) "
                f"bandwidth={config.get('default_bandwidth', 10)} charge={config.get('default_bandwidth_charge', 'TRAFFIC_POSTPAID_BY_HOUR')} "
                f"count={count}"
            )
            return self.cvm_manager.create(
                config.get("default_cpu", 2),
                config.get("default_memory", 4),
                config["default_region"],
                config["default_password"],
                image_id,
                None,
                config.get("default_zone"),
                count,
                config.get("default_disk_type", "CLOUD_PREMIUM"),
                config.get("default_disk_size", 50),
                config.get("default_bandwidth", 10),
                config.get("default_bandwidth_charge", "TRAFFIC_POSTPAID_BY_HOUR")
            )
        
        def on_success(result):
            # 获取创建的实例ID列表
            if count == 1:
                instance_id = result.get('InstanceId') or (result.get('InstanceIds', [None])[0] if result.get('InstanceIds') else None)
                instance_ids = [instance_id] if instance_id else []
            else:
                instance_ids = result.get('InstanceIds', [])
            
            logger.info(f"[创建任务成功] 实例ID列表={instance_ids} warnings={result.get('Warnings')}")
            # 停止全局加载状态
            if hasattr(main_app, "stop_loading_status"):
                main_app.stop_loading_status()
            
            # 显示最终成功消息
            if count == 1:
                self.show_message(f"实例创建成功！实例ID: {instance_ids[0] if instance_ids else '未知'}", "success", 5000)
            else:
                created_count = len(instance_ids)
                if created_count <= 10:
                    ids_text = "\n".join(instance_ids)
                else:
                    ids_text = "\n".join(instance_ids[:10]) + f"\n... 还有 {created_count - 10} 个"
                self.show_message(f"成功创建{created_count}个实例！\n实例ID列表:\n{ids_text}", "success", 5000)
            
            # 展示创建过程中的警告（例如可用区不匹配、磁盘类型回退）
            warnings = result.get("Warnings") or []
            for warn in warnings:
                self.show_message(str(warn), "warning", 6000)
            
            # 将新实例加入 pending 监控（等待 RUNNING/IP）
            self.pending_instance_ids.update([iid for iid in instance_ids if iid])
            if self.pending_instance_ids and not self.pending_poll_timer.isActive():
                self.pending_poll_timer.start()
            
            # 立即刷新本地展示（数据库已写入）
            self.refresh_instances(silent=True, skip_sync=True)
            
            self._set_status_text('<span style="font-weight: bold; color: #2e7d32;">就绪</span> | 创建完成')
        
        def on_error(err_msg):
            logger.error(f"创建实例失败: {err_msg}")
            self.show_message(f"无法创建实例: {err_msg}", "error", 5000)
            if hasattr(main_app, "stop_loading_status"):
                main_app.stop_loading_status()
            self._set_status_text('<span style="font-weight: bold; color: #2e7d32;">就绪</span>')
        
        if hasattr(main_app, "run_in_background"):
            # 不使用全局 loading 动画，由状态栏“创建中...”提示
            main_app.run_in_background(create_task, on_success, auto_stop=True, err_callback=on_error, use_loading=False)
        else:
            # 回退：同步执行（一般不会走到这里）
            try:
                res = create_task()
                on_success(res)
            except Exception as e:
                on_error(str(e))
    
    def batch_start(self):
        """批量开机"""
        if not self.cvm_manager:
            self.show_message("请先配置并刷新实例列表", "warning", 5000)
            return
        
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要操作的实例", "warning", 5000)
            return
        
        # 检查实例状态，过滤掉已经是 RUNNING 的实例
        from utils.db_manager import get_db
        db = get_db()
        valid_ids = []
        skipped_ids = []
        try:
            original_instances = db.get_instances(selected_ids)
            for inst in original_instances:
                instance_id = inst.get("instance_id")
                status = inst.get("status", "")
                if status == "RUNNING":
                    skipped_ids.append(instance_id)
                else:
                    valid_ids.append(instance_id)
        except Exception as e:
            import logging
            logger = logging.getLogger("CVM_Manager")
            logger.warning(f"获取实例状态失败: {e}")
            # 如果获取状态失败，使用所有选中的实例
            valid_ids = selected_ids
        
        if not valid_ids:
            # 如果所有实例都已经是运行状态，直接返回错误
            if skipped_ids:
                self.show_message(f"所选实例均已运行，无法执行开机操作", "error", 5000)
            else:
                self.show_message("没有可开机的实例", "error", 5000)
            return
        
        if skipped_ids:
            self.show_message(f"已跳过 {len(skipped_ids)} 个已运行的实例，将处理 {len(valid_ids)} 个实例", "info", 4000)
        
        # 执行开机操作的函数
        def execute_start():
            import logging
            logger = logging.getLogger("CVM_Manager")
            
            # 保存原始状态用于回滚（只保存有效实例的状态）
            original_states = {}
            try:
                original_instances = db.get_instances(valid_ids)
                for inst in original_instances:
                    original_states[inst.get("instance_id")] = inst.get("status")
            except Exception as e:
                logger.warning(f"获取实例原始状态失败: {e}")
            
            # 1. 立即在数据库中标记为STARTING
            try:
                for iid in valid_ids:
                    db.update_instance_status(iid, "STARTING")
                logger.info(f"已在数据库中标记{len(valid_ids)}个实例为开机中状态")
            except Exception as e:
                logger.error(f"标记实例状态失败: {e}")
                self.show_message(f"标记实例状态失败: {str(e)}", "error", 5000)
                return
            
            # 2. 立即刷新UI，显示开机中状态
            self.refresh_instances(silent=True, skip_sync=True)
            
            # 3. 立即显示"成功发起开机"消息（用户确认后）
            self.show_message(f"成功发起开机，共{len(valid_ids)}个实例", "info", 5000)
            logger.info(f"UI消息: 成功发起开机，共{len(valid_ids)}个实例")
            
            # 4. 异步调用API开机
            def start_task():
                """后台任务：调用API开机"""
                logger.info(f"开始调用API开机{len(valid_ids)}个实例")
                return self.cvm_manager.start(valid_ids, skip_db_update=True)
            
            def on_success(result):
                """API调用成功"""
                logger.info(f"API开机成功: {result}")
                # 将实例加入开机监控（等待 RUNNING），每2秒轮询一次状态
                self.starting_instance_ids.update([iid for iid in valid_ids if iid])
                if self.starting_instance_ids and not self.pending_poll_timer.isActive():
                    self.pending_poll_timer.start()
                
                # 立即查询API获取最新状态并更新数据库
                try:
                    instances = self.cvm_manager.get_instances(self.cvm_manager.region, instance_ids=valid_ids)
                    if instances:
                        from utils.db_manager import get_db
                        db = get_db()
                        for inst in instances:
                            instance_id = inst.get("InstanceId")
                            api_status = inst.get("InstanceState", "")
                            if instance_id and api_status:
                                db.update_instance_status(instance_id, api_status)
                        logger.info(f"已更新{len(instances)}个实例的状态到数据库")
                except Exception as e:
                    logger.warning(f"查询最新状态失败: {e}，将使用轮询同步")
                
                self.show_message(f"开机成功，共{len(valid_ids)}个实例", "success", 5000)
                # 刷新UI，显示最新状态
                self.refresh_instances(silent=True, skip_sync=True)
                # 清除复选框选中状态
                self.instance_list.clear_selection()
            
            def on_error(err_msg):
                """API调用失败，回滚数据库状态"""
                logger.error(f"API开机失败: {err_msg}")
                # 回滚数据库状态
                try:
                    from utils.db_manager import get_db
                    db = get_db()
                    for iid in valid_ids:
                        original_status = original_states.get(iid)
                        if original_status:
                            db.update_instance_status(iid, original_status)
                        else:
                            # 如果没有原始状态，尝试从API获取最新状态
                            try:
                                instances = self.cvm_manager.get_instances(self.cvm_manager.region, instance_ids=[iid])
                                if instances:
                                    api_status = instances[0].get("InstanceState", "")
                                    if api_status:
                                        db.update_instance_status(iid, api_status)
                            except Exception:
                                pass
                    logger.info(f"已回滚{len(valid_ids)}个实例的状态")
                except Exception as rollback_err:
                    logger.error(f"回滚状态失败: {rollback_err}")
                
                # 刷新UI显示回滚后的状态
                self.refresh_instances(silent=True, skip_sync=True)
                self.show_message(f"开机失败: {err_msg}", "error", 5000)
                logger.info(f"UI消息: 开机失败: {err_msg}")
            
            # 获取主应用对象并调用后台任务
            main_app = self.window()
            if hasattr(main_app, "run_in_background"):
                main_app.run_in_background(
                    start_task,
                    callback=on_success,
                    err_callback=on_error,
                    use_loading=False  # 开机不需要显示加载动画
                )
            else:
                # 降级方案：直接调用
                try:
                    result = start_task()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
        
        # 显示确认对话框
        def show_dialog():
            if skipped_ids:
                message = f"已选择 {len(selected_ids)} 个实例，其中 {len(skipped_ids)} 个已运行将被跳过。\n确定要启动剩余的 {len(valid_ids)} 个实例吗？"
            else:
                message = f"确定要启动 {len(valid_ids)} 个实例吗？"
            
            reply = QMessageBox.question(
                self,
                "确认操作",
                message,
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                execute_start()
            else:
                self.show_message("已取消开机操作", "info", 3000)
        
        # 如果有跳过的实例，延迟显示确认对话框，让提示信息先显示
        if skipped_ids:
            QTimer.singleShot(300, show_dialog)
        else:
            show_dialog()
    
    def batch_stop(self):
        """批量关机"""
        if not self.cvm_manager:
            self.show_message("请先配置并刷新实例列表", "warning", 5000)
            return
        
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要操作的实例", "warning", 5000)
            return
        
        # 检查实例状态，过滤掉已经是 STOPPED 的实例
        from utils.db_manager import get_db
        db = get_db()
        valid_ids = []
        skipped_ids = []
        try:
            original_instances = db.get_instances(selected_ids)
            for inst in original_instances:
                instance_id = inst.get("instance_id")
                status = inst.get("status", "")
                if status == "STOPPED":
                    skipped_ids.append(instance_id)
                else:
                    valid_ids.append(instance_id)
        except Exception as e:
            import logging
            logger = logging.getLogger("CVM_Manager")
            logger.warning(f"获取实例状态失败: {e}")
            # 如果获取状态失败，使用所有选中的实例
            valid_ids = selected_ids
        
        if not valid_ids:
            # 如果所有实例都已经是关机状态，直接返回错误
            if skipped_ids:
                self.show_message(f"所选实例均已关机，无法执行关机操作", "error", 5000)
            else:
                self.show_message("没有可关机的实例", "error", 5000)
            return
        
        if skipped_ids:
            self.show_message(f"已跳过 {len(skipped_ids)} 个已关机的实例，将处理 {len(valid_ids)} 个实例", "info", 4000)
        
        # 执行关机操作的函数
        def execute_stop():
            import logging
            logger = logging.getLogger("CVM_Manager")
            
            # 保存原始状态用于回滚（只保存有效实例的状态）
            original_states = {}
            try:
                original_instances = db.get_instances(valid_ids)
                for inst in original_instances:
                    original_states[inst.get("instance_id")] = inst.get("status")
            except Exception as e:
                logger.warning(f"获取实例原始状态失败: {e}")
            
            # 1. 立即在数据库中标记为STOPPING
            try:
                for iid in valid_ids:
                    db.update_instance_status(iid, "STOPPING")
                logger.info(f"已在数据库中标记{len(valid_ids)}个实例为关机中状态")
            except Exception as e:
                logger.error(f"标记实例状态失败: {e}")
                self.show_message(f"标记实例状态失败: {str(e)}", "error", 5000)
                return
            
            # 2. 立即刷新UI，显示关机中状态
            self.refresh_instances(silent=True, skip_sync=True)
            
            # 3. 立即显示"成功发起关机"消息（用户确认后）
            self.show_message(f"成功发起关机，共{len(valid_ids)}个实例", "info", 5000)
            logger.info(f"UI消息: 成功发起关机，共{len(valid_ids)}个实例")
            
            # 4. 异步调用API关机
            def stop_task():
                """后台任务：调用API关机"""
                logger.info(f"开始调用API关机{len(valid_ids)}个实例")
                return self.cvm_manager.stop(valid_ids, False, skip_db_update=True)
            
            def on_success(result):
                """API调用成功"""
                logger.info(f"API关机成功: {result}")
                # 将实例加入关机监控（等待 STOPPED），每2秒轮询一次状态
                self.stopping_instance_ids.update([iid for iid in valid_ids if iid])
                if self.stopping_instance_ids and not self.pending_poll_timer.isActive():
                    self.pending_poll_timer.start()
                
                # 立即查询API获取最新状态并更新数据库
                try:
                    instances = self.cvm_manager.get_instances(self.cvm_manager.region, instance_ids=valid_ids)
                    if instances:
                        from utils.db_manager import get_db
                        db = get_db()
                        for inst in instances:
                            instance_id = inst.get("InstanceId")
                            api_status = inst.get("InstanceState", "")
                            if instance_id and api_status:
                                db.update_instance_status(instance_id, api_status)
                        logger.info(f"已更新{len(instances)}个实例的状态到数据库")
                except Exception as e:
                    logger.warning(f"查询最新状态失败: {e}，将使用轮询同步")
                
                self.show_message(f"关机成功，共{len(valid_ids)}个实例", "success", 5000)
                # 刷新UI，显示最新状态
                self.refresh_instances(silent=True, skip_sync=True)
                # 清除复选框选中状态
                self.instance_list.clear_selection()
            
            def on_error(err_msg):
                """API调用失败，回滚数据库状态"""
                logger.error(f"API关机失败: {err_msg}")
                # 回滚数据库状态
                try:
                    from utils.db_manager import get_db
                    db = get_db()
                    for iid in valid_ids:
                        original_status = original_states.get(iid)
                        if original_status:
                            db.update_instance_status(iid, original_status)
                        else:
                            # 如果没有原始状态，尝试从API获取最新状态
                            try:
                                instances = self.cvm_manager.get_instances(self.cvm_manager.region, instance_ids=[iid])
                                if instances:
                                    api_status = instances[0].get("InstanceState", "")
                                    if api_status:
                                        db.update_instance_status(iid, api_status)
                            except Exception:
                                pass
                    logger.info(f"已回滚{len(valid_ids)}个实例的状态")
                except Exception as rollback_err:
                    logger.error(f"回滚状态失败: {rollback_err}")
                
                # 刷新UI显示回滚后的状态
                self.refresh_instances(silent=True, skip_sync=True)
                self.show_message(f"关机失败: {err_msg}", "error", 5000)
                logger.info(f"UI消息: 关机失败: {err_msg}")
            
            # 获取主应用对象并调用后台任务
            main_app = self.window()
            if hasattr(main_app, "run_in_background"):
                main_app.run_in_background(
                    stop_task,
                    callback=on_success,
                    err_callback=on_error,
                    use_loading=False  # 关机不需要显示加载动画
                )
            else:
                # 降级方案：直接调用
                try:
                    result = stop_task()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
        
        # 显示确认对话框（开机操作）
        def show_dialog_start():
            if skipped_ids:
                message = f"已选择 {len(selected_ids)} 个实例，其中 {len(skipped_ids)} 个已运行将被跳过。\n确定要启动剩余的 {len(valid_ids)} 个实例吗？"
            else:
                message = f"确定要启动 {len(valid_ids)} 个实例吗？"
            
            reply = QMessageBox.question(
                self,
                "确认操作",
                message,
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                execute_start()
            else:
                self.show_message("已取消开机操作", "info", 3000)
        
        # 如果有跳过的实例，延迟显示确认对话框，让提示信息先显示
        if skipped_ids:
            QTimer.singleShot(300, show_dialog_start)
        else:
            show_dialog_start()
    
    def batch_stop(self):
        """批量关机"""
        if not self.cvm_manager:
            self.show_message("请先配置并刷新实例列表", "warning", 5000)
            return
        
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要操作的实例", "warning", 5000)
            return
        
        # 检查实例状态，过滤掉已经是 STOPPED 的实例
        from utils.db_manager import get_db
        db = get_db()
        valid_ids = []
        skipped_ids = []
        try:
            original_instances = db.get_instances(selected_ids)
            for inst in original_instances:
                instance_id = inst.get("instance_id")
                status = inst.get("status", "")
                if status == "STOPPED":
                    skipped_ids.append(instance_id)
                else:
                    valid_ids.append(instance_id)
        except Exception as e:
            import logging
            logger = logging.getLogger("CVM_Manager")
            logger.warning(f"获取实例状态失败: {e}")
            # 如果获取状态失败，使用所有选中的实例
            valid_ids = selected_ids
        
        if not valid_ids:
            # 如果所有实例都已经是关机状态，直接返回错误
            if skipped_ids:
                self.show_message(f"所选实例均已关机，无法执行关机操作", "error", 5000)
            else:
                self.show_message("没有可关机的实例", "error", 5000)
            return
        
        if skipped_ids:
            self.show_message(f"已跳过 {len(skipped_ids)} 个已关机的实例，将处理 {len(valid_ids)} 个实例", "info", 4000)
        
        # 执行关机操作的函数
        def execute_stop():
            import logging
            logger = logging.getLogger("CVM_Manager")
            
            # 保存原始状态用于回滚（只保存有效实例的状态）
            original_states = {}
            try:
                original_instances = db.get_instances(valid_ids)
                for inst in original_instances:
                    original_states[inst.get("instance_id")] = inst.get("status")
            except Exception as e:
                logger.warning(f"获取实例原始状态失败: {e}")
            
            # 1. 立即在数据库中标记为STOPPING
            try:
                for iid in valid_ids:
                    db.update_instance_status(iid, "STOPPING")
                logger.info(f"已在数据库中标记{len(valid_ids)}个实例为关机中状态")
            except Exception as e:
                logger.error(f"标记实例状态失败: {e}")
                self.show_message(f"标记实例状态失败: {str(e)}", "error", 5000)
                return
            
            # 2. 立即刷新UI，显示关机中状态
            self.refresh_instances(silent=True, skip_sync=True)
            
            # 3. 立即显示"成功发起关机"消息（用户确认后）
            self.show_message(f"成功发起关机，共{len(valid_ids)}个实例", "info", 5000)
            logger.info(f"UI消息: 成功发起关机，共{len(valid_ids)}个实例")
            
            # 4. 异步调用API关机
            def stop_task():
                """后台任务：调用API关机"""
                logger.info(f"开始调用API关机{len(valid_ids)}个实例")
                return self.cvm_manager.stop(valid_ids, False, skip_db_update=True)
            
            def on_success(result):
                """API调用成功"""
                logger.info(f"API关机成功: {result}")
                # 将实例加入关机监控（等待 STOPPED），每2秒轮询一次状态
                self.stopping_instance_ids.update([iid for iid in valid_ids if iid])
                if self.stopping_instance_ids and not self.pending_poll_timer.isActive():
                    self.pending_poll_timer.start()
                
                # 立即查询API获取最新状态并更新数据库
                try:
                    instances = self.cvm_manager.get_instances(self.cvm_manager.region, instance_ids=valid_ids)
                    if instances:
                        from utils.db_manager import get_db
                        db = get_db()
                        for inst in instances:
                            instance_id = inst.get("InstanceId")
                            api_status = inst.get("InstanceState", "")
                            if instance_id and api_status:
                                db.update_instance_status(instance_id, api_status)
                        logger.info(f"已更新{len(instances)}个实例的状态到数据库")
                except Exception as e:
                    logger.warning(f"查询最新状态失败: {e}，将使用轮询同步")
                
                self.show_message(f"关机成功，共{len(valid_ids)}个实例", "success", 5000)
                # 刷新UI，显示最新状态
                self.refresh_instances(silent=True, skip_sync=True)
                # 清除复选框选中状态
                self.instance_list.clear_selection()
            
            def on_error(err_msg):
                """API调用失败，回滚数据库状态"""
                logger.error(f"API关机失败: {err_msg}")
                # 回滚数据库状态
                try:
                    from utils.db_manager import get_db
                    db = get_db()
                    for iid in valid_ids:
                        original_status = original_states.get(iid)
                        if original_status:
                            db.update_instance_status(iid, original_status)
                        else:
                            # 如果没有原始状态，尝试从API获取最新状态
                            try:
                                instances = self.cvm_manager.get_instances(self.cvm_manager.region, instance_ids=[iid])
                                if instances:
                                    api_status = instances[0].get("InstanceState", "")
                                    if api_status:
                                        db.update_instance_status(iid, api_status)
                            except Exception:
                                pass
                    logger.info(f"已回滚{len(valid_ids)}个实例的状态")
                except Exception as rollback_err:
                    logger.error(f"回滚状态失败: {rollback_err}")
                
                # 刷新UI显示回滚后的状态
                self.refresh_instances(silent=True, skip_sync=True)
                self.show_message(f"关机失败: {err_msg}", "error", 5000)
                logger.info(f"UI消息: 关机失败: {err_msg}")
            
            # 获取主应用对象并调用后台任务
            main_app = self.window()
            if hasattr(main_app, "run_in_background"):
                main_app.run_in_background(
                    stop_task,
                    callback=on_success,
                    err_callback=on_error,
                    use_loading=False  # 关机不需要显示加载动画
                )
            else:
                # 降级方案：直接调用
                try:
                    result = stop_task()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
        
        # 显示确认对话框（关机操作）
        def show_dialog_stop():
            if skipped_ids:
                message = f"已选择 {len(selected_ids)} 个实例，其中 {len(skipped_ids)} 个已关机将被跳过。\n确定要停止剩余的 {len(valid_ids)} 个实例吗？"
            else:
                message = f"确定要停止 {len(valid_ids)} 个实例吗？"
            
            reply = QMessageBox.question(
                self,
                "确认操作",
                message,
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                execute_stop()
            else:
                self.show_message("已取消关机操作", "info", 3000)
        
        # 如果有跳过的实例，延迟显示确认对话框，让提示信息先显示
        if skipped_ids:
            QTimer.singleShot(300, show_dialog_stop)
        else:
            show_dialog_stop()
    
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
            import logging
            logger = logging.getLogger("CVM_Manager")
            
            # 保存原始状态用于回滚
            from utils.db_manager import get_db
            db = get_db()
            original_states = {}
            try:
                original_instances = db.get_instances(selected_ids)
                for inst in original_instances:
                    original_states[inst.get("instance_id")] = inst.get("status")
            except Exception as e:
                logger.warning(f"获取实例原始状态失败: {e}")
            
            # 1. 立即在数据库中标记为-1
            try:
                for iid in selected_ids:
                    db.update_instance_status(iid, "-1")
                logger.info(f"已在数据库中标记{len(selected_ids)}个实例为删除状态")
            except Exception as e:
                logger.error(f"标记实例状态失败: {e}")
                self.show_message(f"标记实例状态失败: {str(e)}", "error", 5000)
                return
            
            # 2. 立即刷新UI，隐藏这些实例
            self.refresh_instances(silent=True, skip_sync=True)
            
            # 3. 立即显示"成功发起销毁"消息
            self.show_message(f"成功发起销毁，共{len(selected_ids)}个实例", "info", 5000)
            logger.info(f"UI消息: 成功发起销毁，共{len(selected_ids)}个实例")
            
            # 4. 异步调用API销毁实例
            def terminate_task():
                """后台任务：调用API销毁实例"""
                logger.info(f"开始调用API销毁{len(selected_ids)}个实例")
                return self.cvm_manager.terminate(selected_ids, skip_db_update=True)
            
            def on_success(result):
                """API调用成功"""
                logger.info(f"API销毁成功: {result}")
                self.show_message(f"销毁成功，共{len(selected_ids)}个实例", "success", 5000)
                # 只刷新UI，不触发同步（因为销毁是异步的，API可能还没完全删除实例）
                # 定时器会在1分钟后自动同步，或者用户手动刷新时会同步
                self.refresh_instances(silent=True, skip_sync=True)
            
            def on_error(err_msg):
                """API调用失败，回滚数据库状态"""
                logger.error(f"API销毁失败: {err_msg}")
                # 回滚数据库状态
                try:
                    from utils.db_manager import get_db
                    db = get_db()
                    for iid in selected_ids:
                        original_status = original_states.get(iid)
                        if original_status:
                            db.update_instance_status(iid, original_status)
                        else:
                            # 如果没有原始状态，尝试从API获取最新状态
                            try:
                                instances = self.cvm_manager.get_instances(self.cvm_manager.region, instance_ids=[iid])
                                if instances and len(instances) > 0:
                                    api_status = instances[0].get("InstanceState", "")
                                    db.update_instance_status(iid, api_status)
                                    logger.info(f"从API获取实例{iid}的状态: {api_status}")
                                else:
                                    # API中也没有，保持-1状态但记录警告
                                    logger.warning(f"无法获取实例{iid}的状态，保持删除标记")
                            except Exception as api_err:
                                logger.warning(f"从API获取实例{iid}状态失败: {api_err}，保持删除标记")
                    logger.info(f"已回滚{len(selected_ids)}个实例的数据库状态")
                    # 刷新UI显示回滚后的状态
                    self.refresh_instances(silent=True)
                except Exception as rollback_err:
                    logger.error(f"回滚数据库状态失败: {rollback_err}")
                
                self.show_message(f"销毁失败: {err_msg}，已回滚状态", "error", 5000)
                logger.info(f"UI消息: 销毁失败: {err_msg}，已回滚状态")
            
            # 获取主应用对象以调用run_in_background
            main_app = self.parent()
            while main_app and not hasattr(main_app, 'run_in_background'):
                main_app = main_app.parent()
            
            if main_app and hasattr(main_app, 'run_in_background'):
                main_app.run_in_background(terminate_task, on_success, auto_stop=True, err_callback=on_error, use_loading=False)
            else:
                # 回退：同步执行（一般不会走到这里）
                try:
                    result = terminate_task()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
    
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
            import logging
            logger = logging.getLogger("CVM_Manager")
            
            # 检查有多少运行中的实例
            running_count = 0
            try:
                instances = self.cvm_manager.get_instances(None)
                for instance in instances:
                    if instance.get("InstanceId") in selected_ids and instance.get("InstanceState") == "RUNNING":
                        running_count += 1
            except Exception as e:
                logger.warning(f"获取实例状态失败: {e}")
            
            # 1. 立即显示"成功发起修改密码"消息
            self.show_message(f"成功发起修改密码，共{len(selected_ids)}个实例", "info", 5000)
            logger.info(f"UI消息: 成功发起修改密码，共{len(selected_ids)}个实例")
            
            # 2. 异步调用API重置密码
            def reset_password_task():
                """后台任务：调用API重置密码"""
                logger.info(f"开始调用API重置{len(selected_ids)}个实例的密码")
                return self.cvm_manager.reset_pwd(selected_ids, password)
            
            def on_success(result):
                """API调用成功"""
                logger.info(f"API重置密码成功: {result}")
                
                # 保存密码到配置
                try:
                    from config.config_manager import get_instance_config, save_instance_config
                    config = get_instance_config()
                    save_instance_config(
                        config.get("default_cpu", 2),
                        config.get("default_memory", 4),
                        config.get("default_region"),
                        config.get("default_zone"),
                        config.get("default_image_id"),
                        password,
                        config.get("default_disk_type", "CLOUD_PREMIUM"),
                        config.get("default_disk_size", 50),
                        config.get("default_bandwidth", 10),
                        config.get("default_bandwidth_charge", "TRAFFIC_POSTPAID_BY_HOUR")
                    )
                    logger.info("已保存密码到配置")
                except Exception as e:
                    logger.warning(f"保存密码到配置失败: {e}")
                
                # 显示成功消息
                if running_count > 0:
                    self.show_message(f"已重置{len(selected_ids)}个实例的密码，并自动开机{running_count}个原本运行中的实例", "success", 5000)
                else:
                    self.show_message(f"已重置{len(selected_ids)}个实例的密码", "success", 5000)
                
                # 刷新UI
                self.refresh_instances(silent=True, skip_sync=True)
                # 清除复选框选中状态
                self.instance_list.clear_selection()
            
            def on_error(err_msg):
                """API调用失败"""
                logger.error(f"API重置密码失败: {err_msg}")
                self.show_message(f"批量重置密码失败: {err_msg}", "error", 5000)
                logger.info(f"UI消息: 批量重置密码失败: {err_msg}")
            
            # 获取主应用对象并调用后台任务
            main_app = self.window()
            if hasattr(main_app, "run_in_background"):
                main_app.run_in_background(
                    reset_password_task,
                    callback=on_success,
                    err_callback=on_error,
                    use_loading=False  # 重置密码不需要显示加载动画
                )
            else:
                # 降级方案：直接调用
                try:
                    result = reset_password_task()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
    
    def show_settings(self):
        """显示设置对话框（API凭证设置）"""
        dialog = SettingsDialog(self)
        if dialog.exec_():
            # 重新初始化管理器（热更新，无需重启）
            if CVM_MANAGER_AVAILABLE:
                try:
                    api_config = get_api_config() if get_api_config else {}
                    secret_id = api_config.get("secret_id")
                    secret_key = api_config.get("secret_key")
                    self.cvm_manager = CVMManager(secret_id, secret_key, None)
                    self.show_message("API凭证已更新", "success", 2000)
                    # 可选：自动刷新实例列表
                    # self.refresh_instances()
                except Exception as e:
                    self.show_message(f"无法初始化CVM管理器: {str(e)}", "error", 5000)
    
    def show_instance_config(self):
        """显示实例配置对话框"""
        # 自定义镜像模式禁用实例配置
        if self.image_source_combo.currentData() == "PRIVATE":
            self.show_message("当前选择自定义镜像，实例配置不可用", "warning", 3000)
            return
        self.btn_instance_config.setEnabled(False)
        
        try:
            if not CVM_MANAGER_AVAILABLE:
                self.show_message("请先安装依赖：pip install -r requirements.txt", "error", 5000)
                self.btn_instance_config.setEnabled(True)
                return
            
            if not self.cvm_manager:
                api_config = get_api_config() if get_api_config else {}
                secret_id = api_config.get("secret_id")
                secret_key = api_config.get("secret_key")
                if not secret_id or not secret_key:
                    self.show_message("请先配置API凭证", "warning", 5000)
                    self.show_settings()
                    self.btn_instance_config.setEnabled(True)
                    return
                try:
                    from config.config_manager import get_instance_config
                    config = get_instance_config()
                    default_region = config.get("default_region")
                    self.cvm_manager = CVMManager(secret_id, secret_key, default_region)
                except Exception as e:
                    self.show_message(f"无法初始化CVM管理器: {str(e)}", "error", 5000)
                    self.btn_instance_config.setEnabled(True)
                    return
            
            dialog = InstanceConfigDialog(self.cvm_manager, self)
            dialog.exec_()
            if dialog.result() == QDialog.Accepted:
                # 检查是否是更新配置操作，如果是则不显示"保存配置成功"消息
                if not getattr(dialog, 'is_updating_config', False):
                    self.show_message("实例配置已保存", "success", 2000)
                    # 配置变更后立即同步一次并刷新本地
                    self.refresh_instances(silent=True)
            self.btn_instance_config.setEnabled(True)
        except Exception as e:
            self.show_message(f"打开配置对话框失败: {str(e)}", "error", 5000)
            self.btn_instance_config.setEnabled(True)

    def on_image_source_changed(self):
        """镜像来源切换时，更新自定义镜像列表与实例配置按钮状态"""
        source = self.image_source_combo.currentData()
        if source == "PRIVATE":
            self.btn_instance_config.setEnabled(False)
            self.custom_image_combo.setEnabled(True)
            if not self.custom_images:
                self.load_custom_images()
        else:
            self.btn_instance_config.setEnabled(True)
            self.custom_image_combo.setEnabled(False)
        self.refresh_image_selection()

    def load_custom_images(self):
        """加载自定义镜像列表"""
        if not CVM_MANAGER_AVAILABLE:
            return
        if not self.cvm_manager:
            return
        try:
            images = self.cvm_manager.get_images("PRIVATE_IMAGE")
            self.custom_images = images or []
            self.refresh_image_selection()
        except Exception as e:
            self.custom_image_combo.clear()
            self.custom_image_combo.addItem(f"加载失败: {str(e)}", None)
            self.custom_image_combo.setEnabled(False)
            self.btn_create.setEnabled(False)

    def refresh_image_selection(self):
        """根据镜像来源刷新下拉内容和创建按钮可用性"""
        source = self.image_source_combo.currentData()
        self.btn_create.setEnabled(True)
        self.custom_image_combo.clear()
        if source == "PRIVATE":
            self.btn_instance_config.setEnabled(False)
            if not self.custom_images:
                self.custom_image_combo.addItem("无可用自定义镜像", None)
                self.custom_image_combo.setEnabled(False)
                self.btn_create.setEnabled(False)
            else:
                for img in self.custom_images:
                    name = img.get("ImageName") or img.get("ImageId")
                    self.custom_image_combo.addItem(f"{name} ({img.get('ImageId')})", img.get("ImageId"))
                self.custom_image_combo.setEnabled(True)
                self.custom_image_combo.setCurrentIndex(0)
                if self.custom_image_combo.currentData() is None:
                    self.btn_create.setEnabled(False)
        else:
            # 公共镜像模式：显示当前实例配置中的镜像
            from config.config_manager import get_instance_config
            config = get_instance_config()
            image_id = config.get("default_image_id")
            label = image_id or "请配置实例镜像"
            self.custom_image_combo.addItem(label, image_id)
            self.custom_image_combo.setEnabled(False)
            self.btn_instance_config.setEnabled(True)
            if not image_id:
                self.btn_create.setEnabled(False)


