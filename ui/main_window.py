"""
主窗口内容区域。

职责：
    - 提供实例列表、统计信息与批量操作入口。
    - 负责实例创建、启动、关机、销毁、密码重置等交互逻辑。
    - 统一触发顶部消息条，反馈成功或异常信息。
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox, QGroupBox, QFrame, QMainWindow, QSpinBox, QDialog, QComboBox, QApplication
from PyQt5.QtCore import Qt, QTimer
from core.preload import preload_reference_data
import time
from ui.components.instance_list import InstanceList
from ui.components.message_bar import MessageBar
from ui.dialogs.settings_dialog import SettingsDialog
from ui.dialogs.instance_config_dialog import InstanceConfigDialog
from ui.dialogs.send_command_dialog import SendCommandDialog
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
        # 标记是否正在进行实例配置信息更新（区域/可用区/镜像预加载）
        self.is_reference_updating = False
        # 控制在配置更新期间以及刚结束后的短时间内禁止创建实例
        self.block_creates_until = 0.0
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
        # 指令执行中监控（存储InvocationId）
        self.executing_invocation_ids = set()
        self.pending_poll_timer = QTimer()
        self.pending_poll_timer.setInterval(2_000)
        self.pending_poll_timer.timeout.connect(self._poll_pending_instances)
        self.custom_images = []  # 缓存自定义镜像列表
        self.init_ui()
        self.auto_refresh_on_start()

    def _set_reference_update_loading(self, loading: bool):
        """
        控制“配置更新中”时的软 loading 状态：
            - 禁用/启用主要操作按钮，避免误操作。
            - 不直接覆写状态栏文案，由调用方决定具体文案。
        """
        controls = [
            getattr(self, "btn_refresh", None),
            getattr(self, "btn_create", None),
            getattr(self, "btn_instance_config", None),
            getattr(self, "btn_settings", None),
            getattr(self, "btn_start", None),
            getattr(self, "btn_stop", None),
            getattr(self, "btn_terminate", None),
            getattr(self, "btn_reset_pwd", None),
            getattr(self, "btn_send_command", None),
            getattr(self, "platform_combo", None),
            getattr(self, "custom_image_combo", None),
            getattr(self, "image_source_combo", None),
        ]
        for w in controls:
            if w is not None:
                w.setEnabled(not loading)
    
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

        # 系统类型筛选（公共镜像模式下按平台过滤）
        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumWidth(120)
        self.platform_combo.currentIndexChanged.connect(self.on_platform_changed)
        self.platform_combo.setToolTip("选择系统类型")

        # 镜像列表
        self.custom_image_combo = QComboBox()
        self.custom_image_combo.setMinimumWidth(220)
        self.custom_image_combo.setEnabled(False)
        self.custom_image_combo.setToolTip("选择镜像")
        
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
        btn_group1.addWidget(QLabel("系统类型:"))
        btn_group1.addWidget(self.platform_combo)
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
        
        self.btn_send_command = QPushButton("📤 下发指令")
        self.btn_send_command.setProperty("class", "")
        self.btn_send_command.clicked.connect(self.batch_send_command)
        self.btn_send_command.setFixedHeight(32)
        self.btn_send_command.setStyleSheet("font-size: 12px; padding: 4px 12px;")
        
        batch_btn_layout.addWidget(self.btn_start)
        batch_btn_layout.addWidget(self.btn_stop)
        batch_btn_layout.addWidget(self.btn_terminate)
        batch_btn_layout.addWidget(self.btn_reset_pwd)
        batch_btn_layout.addWidget(self.btn_send_command)
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
            # 先同步一次（异步拉远端），完成后自动刷新展示
            self.refresh_instances(silent=True)
            # 开启定时：1分钟远端同步，4秒本地轮询
            if not self.refresh_timer.isActive():
                self.refresh_timer.start()
            if not self.db_poll_timer.isActive():
                self.db_poll_timer.start()
    
    def _update_instances_from_db(self, silent: bool = False):
        """从本地数据库读取实例并刷新列表 + 统计信息（仅做轻量级 UI 操作）"""
        db = get_db()
        raw_instances = db.list_instances()
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
                "Password": row.get("password") or ""
            })

        self.instance_list.update_instances(instances)
        self.update_stats(instances)
        if self.parent():
            self.parent().statusBar().showMessage(f"已加载 {len(instances)} 个实例", 3000)
        if not silent:
            self.show_message(f"成功刷新，共{len(instances)}个实例", "success", 2000)

    def refresh_instances(self, silent=False, sync_only=False, skip_sync=False):
        """
        刷新实例列表。
        sync_only: 只拉取远端到本地，不更新UI。
        skip_sync: 跳过远端调用，直接读本地。
        说明：
            - 所有“远端 API + 大批写库”的重活都放到后台线程执行。
            - 主线程只做本地 DB 读取 + UI 更新，避免阻塞界面。
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

        # 仅从本地库读数据并刷新 UI，不做远端同步（轻量，直接在主线程执行）
        if skip_sync:
            self._update_instances_from_db(silent=silent)
            return

        # 需要远端同步：将“标记删除 + 拉全量实例”的重活丢到后台线程
        def sync_task():
            """
            后台任务：
                - 调用腾讯云 API 拉取最新实例列表，写入本地 SQLite。
                - get_instances(None) 内部会通过 soft_delete_missing 标记
                  不在 API 返回中的实例为 -1，无需预先批量标记。
            """
            # 与原实现一致：None 表示拉取当前区域的所有实例
            self.cvm_manager.get_instances(None)
            return None

        from utils.utils import setup_logger
        logger = setup_logger()

        def on_done(_result):
            # 同步完成后，如果只要求“同步不更新 UI”，直接返回
            if sync_only:
                return
            # 否则从本地库读取并刷新界面
            self._update_instances_from_db(silent=silent)

        def on_error(msg):
            # 远端同步失败，提示用户并继续使用本地缓存
            logger.warning(f"无法同步实例列表: {msg}，将使用本地缓存")
            if not silent:
                self.show_message(f"无法同步实例列表: {msg}，将使用本地缓存", "warning", 5000)
            # 使用现有本地数据刷新 UI
            if not sync_only:
                self._update_instances_from_db(silent=silent)

        main_app = self.window()
        if hasattr(main_app, "run_in_background"):
            main_app.run_in_background(
                sync_task,
                callback=on_done,
                auto_stop=True,
                err_callback=on_error,
                use_loading=not sync_only,
                task_desc="同步实例列表",
            )
        else:
            # 回退方案：在当前线程执行（行为与旧版一致，可能阻塞 UI）
            try:
                sync_task()
            except Exception as e:
                on_error(str(e))
                return
            on_done(None)
    
    def _poll_pending_instances(self):
        """轮询新创建/开关机中实例状态以及指令执行状态，每2s查询一次，达成条件即停止监控。

        说明：
            - 重的网络请求全部放在后台线程执行。
            - 主线程只负责更新本地状态集合 + 刷新 UI。
        """
        from utils.utils import setup_logger
        logger = setup_logger()

        has_pending = bool(self.pending_instance_ids)
        has_starting = bool(self.starting_instance_ids)
        has_stopping = bool(self.stopping_instance_ids)
        has_executing = bool(self.executing_invocation_ids)

        if not has_pending and not has_starting and not has_stopping and not has_executing:
            if self.pending_poll_timer.isActive():
                self.pending_poll_timer.stop()
            return

        if not self.cvm_manager:
            return

        # 在主线程中快照当前需要监控的 ID，避免与 UI 修改产生竞争
        pending_ids = list(self.pending_instance_ids)
        starting_ids = list(self.starting_instance_ids)
        stopping_ids = list(self.stopping_instance_ids)
        executing_ids = list(self.executing_invocation_ids)

        def poll_task():
            """后台任务：查询实例与指令执行状态"""
            # 合并所有需要监控的实例ID
            all_ids = list(set(pending_ids) | set(starting_ids) | set(stopping_ids))
            instances = []
            if all_ids:
                instances = self.cvm_manager.get_instances(None, all_ids) or []

            inv_results = {}
            for invocation_id in executing_ids:
                try:
                    result = self.cvm_manager.describe_invocation_tasks(invocation_id=invocation_id) or {}
                    inv_results[invocation_id] = result
                except Exception as e:
                    logger.warning(f"查询执行任务状态失败: {e}")
            return {
                "instances": instances,
                "inv_results": inv_results,
                "pending_ids": pending_ids,
                "starting_ids": starting_ids,
                "stopping_ids": stopping_ids,
                "executing_ids": executing_ids,
            }

        def on_done(data):
            instances = data.get("instances") or []
            inv_results = data.get("inv_results") or {}

            # 处理创建中的实例（等待 RUNNING 或 IP）
            if has_pending:
                pending_completed = set()
                for inst in instances:
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
                for inst in instances:
                    instance_id = inst.get("InstanceId")
                    if instance_id in self.starting_instance_ids:
                        state = inst.get("InstanceState")
                        if state == "RUNNING":
                            starting_completed.add(instance_id)
                self.starting_instance_ids.difference_update(starting_completed)

            # 处理关机中的实例（等待 STOPPED）
            if has_stopping:
                stopping_completed = set()
                for inst in instances:
                    instance_id = inst.get("InstanceId")
                    if instance_id in self.stopping_instance_ids:
                        state = inst.get("InstanceState")
                        if state == "STOPPED":
                            stopping_completed.add(instance_id)
                self.stopping_instance_ids.difference_update(stopping_completed)

            # 处理指令执行中的任务（查询执行任务状态）
            if has_executing:
                executing_completed = set()
                for invocation_id, result in inv_results.items():
                    tasks = result.get("InvocationTaskSet", [])
                    # 检查所有任务是否都已完成（SUCCESS或FAILED）
                    all_completed = True
                    for task in tasks:
                        status = task.get("TaskStatus", "")
                        if status not in ["SUCCESS", "FAILED"]:
                            all_completed = False
                            break
                    if all_completed and tasks:
                        executing_completed.add(invocation_id)
                self.executing_invocation_ids.difference_update(executing_completed)

            # 刷新本地展示（跳过同步，避免额外 API）
            self.refresh_instances(silent=True, skip_sync=True)

            # 如果所有监控都完成了，停止定时器
            if (not self.pending_instance_ids
                and not self.starting_instance_ids
                and not self.stopping_instance_ids
                and not self.executing_invocation_ids
                and self.pending_poll_timer.isActive()):
                self.pending_poll_timer.stop()

        def on_error(msg):
            logger.error(f"轮询状态失败: {msg}")
            self.show_message(f"轮询实例状态失败: {str(msg)}", "warning", 3000)

        main_app = self.window()
        if hasattr(main_app, "run_in_background"):
            main_app.run_in_background(
                poll_task,
                callback=on_done,
                auto_stop=False,
                err_callback=on_error,
                use_loading=False,
            )
        else:
            # 回退方案：在当前线程执行（行为与旧版一致，可能阻塞 UI）
            try:
                data = poll_task()
            except Exception as e:
                on_error(str(e))
                return
            on_done(data)

    def _is_action_blocked_by_update(self) -> bool:
        """
        判断当前是否因为“配置更新中”而暂时禁止发起云端操作。
        若被禁止，静默丢弃本次操作，不打断用户。
        """
        now_ts = time.time()
        if getattr(self, "is_reference_updating", False) or now_ts < getattr(self, "block_creates_until", 0.0):
            return True
        return False
    
    def create_instances(self):
        """使用配置的参数创建实例"""
        # 若当前正在更新实例配置信息，或刚刚更新完成（短暂保护期内），统一拦截
        if self._is_action_blocked_by_update():
            return
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
        
        # 根据选择的镜像来源确定镜像ID
        source = self.image_source_combo.currentData()
        image_id = self.custom_image_combo.currentData()
        if source == "PRIVATE":
            if not self.custom_images:
                self.show_message("没有可用的自定义镜像", "warning", 3000)
                return
            if not image_id:
                self.show_message("请选择自定义镜像", "warning", 3000)
                return
        else:
            if not image_id:
                self.show_message("未选择公共镜像，请先选择或配置", "warning", 3000)
                return
        
        # 为本次创建生成随机密码（同批实例共享同一密码）
        from utils.utils import generate_password
        random_password = generate_password()
        
        # 立即显示"正在创建"提示（前置反馈）
        if count == 1:
            self.show_message("已提交创建请求，正在创建实例...", "info", 5000)
        else:
            self.show_message(f"已提交创建请求，正在创建 {count} 个实例...", "info", 5000)
        
        # 强制刷新UI，确保消息立即显示
        QApplication.processEvents()
        
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
                random_password,
                image_id,
                None,
                config.get("default_zone"),
                count,
                config.get("default_disk_type", "CLOUD_PREMIUM"),
                config.get("default_disk_size", 50),
                config.get("default_bandwidth", 10),
                config.get("default_bandwidth_charge", "TRAFFIC_POSTPAID_BY_HOUR")
            )
        
        # 延迟启动后台任务，给UI时间显示第一条消息（50ms足够）
        def start_create_task():
            main_app.run_in_background(create_task, on_success, auto_stop=True, err_callback=on_error)
        
        def on_success(result):
            # 获取创建的实例ID列表
            if count == 1:
                instance_id = result.get('InstanceId') or (result.get('InstanceIds', [None])[0] if result.get('InstanceIds') else None)
                instance_ids = [instance_id] if instance_id else []
            else:
                instance_ids = result.get('InstanceIds', [])
            
            logger.info(f"[创建任务成功] 实例ID列表={instance_ids} warnings={result.get('Warnings')}")
            
            # 将密码存储到数据库中对应的实例记录
            try:
                db = get_db()
                db.set_instances_password([iid for iid in instance_ids if iid], random_password)
                logger.info(f"已保存密码到 {len(instance_ids)} 个实例记录")
            except Exception as e:
                logger.warning(f"保存密码到实例记录失败: {e}")
            
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
            
            # 延迟刷新本地展示，避免阻塞主线程（数据库已写入）
            QTimer.singleShot(100, lambda: self.refresh_instances(silent=True, skip_sync=True))
        
        def on_error(err_msg):
            logger.error(f"创建实例失败: {err_msg}")
            self.show_message(f"无法创建实例: {err_msg}", "error", 5000)
        
        if hasattr(main_app, "run_in_background"):
            # 延迟50ms启动后台任务，确保"发起创建"消息先显示
            QTimer.singleShot(50, start_create_task)
        else:
            # 回退：同步执行（一般不会走到这里）
            try:
                res = create_task()
                on_success(res)
            except Exception as e:
                on_error(str(e))
    
    def batch_start(self):
        """批量开机"""
        if self._is_action_blocked_by_update():
            return
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
        if self._is_action_blocked_by_update():
            return
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
        if self._is_action_blocked_by_update():
            return
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
                main_app.run_in_background(terminate_task, on_success, auto_stop=True, err_callback=on_error)
            else:
                # 回退：同步执行（一般不会走到这里）
                try:
                    result = terminate_task()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
    
    def batch_reset_password(self):
        """批量重置密码"""
        if self._is_action_blocked_by_update():
            return
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
                
                # 保存新密码到每个实例的数据库记录
                try:
                    db = get_db()
                    db.set_instances_password(selected_ids, password)
                    logger.info(f"已保存密码到 {len(selected_ids)} 个实例记录")
                except Exception as e:
                    logger.warning(f"保存密码到实例记录失败: {e}")
                
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
                )
            else:
                # 降级方案：直接调用
                try:
                    result = reset_password_task()
                    on_success(result)
                except Exception as e:
                    on_error(str(e))
    
    def batch_send_command(self):
        """批量下发指令"""
        if self._is_action_blocked_by_update():
            return
        from utils.utils import setup_logger
        logger = setup_logger()
        
        if not self.cvm_manager:
            self.show_message("CVM管理器未初始化，请先配置API凭证", "error", 5000)
            return
        
        # 1. 获取选中的实例ID
        selected_ids = self.instance_list.get_selected_instance_ids()
        if not selected_ids:
            self.show_message("请先选择要下发指令的实例", "warning", 3000)
            return
        
        # 2. 从数据库获取选中实例的Platform信息
        db = get_db()
        instances = db.get_instances(selected_ids)
        
        if len(instances) != len(selected_ids):
            self.show_message("无法获取部分实例的信息", "error", 5000)
            return
        
        platforms = set()
        instance_platforms = {}
        
        for instance in instances:
            instance_id = instance.get("instance_id")
            platform = (instance.get("platform") or "").upper()
            # 判断是Linux还是Windows
            if "WINDOWS" in platform:
                platform_type = "WINDOWS"
            else:
                # 默认为Linux（包括Ubuntu、CentOS、Debian等）
                platform_type = "LINUX"
            
            platforms.add(platform_type)
            instance_platforms[instance_id] = platform_type
        
        # 3. 检查是否都是同一类型系统
        if len(platforms) > 1:
            platform_names = {
                "WINDOWS": "Windows",
                "LINUX": "Linux"
            }
            platform_list = [platform_names.get(p, p) for p in platforms]
            self.show_message(f"选中的实例系统类型不一致（包含：{', '.join(platform_list)}），只能对单一系统类型下发指令", "error", 5000)
            return
        
        # 4. 确定系统类型
        platform_type = list(platforms)[0]
        platform_name = "Windows" if platform_type == "WINDOWS" else "Linux"
        
        # 5. 打开指令输入对话框
        dialog = SendCommandDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            command = dialog.get_command()
            if command:
                # 6. 立即显示"成功发起下发指令"消息
                self.show_message(f"成功发起下发指令，共{len(selected_ids)}个实例", "info", 5000)
                
                # 7. 确定命令类型和工作目录
                if platform_type == "WINDOWS":
                    command_type = "POWERSHELL"
                    working_directory = r"C:\Program Files\qcloud\tat_agent\workdir"
                    username = "System"
                else:
                    command_type = "SHELL"
                    working_directory = "/root"
                    username = "root"
                
                # 9. 异步调用API执行命令
                def execute_command_task():
                    """后台任务：调用API执行命令"""
                    if not self.cvm_manager:
                        raise RuntimeError("CVM管理器未初始化")
                    
                    result = self.cvm_manager.run_command(
                        instance_ids=selected_ids,
                        command_content=command,
                        command_type=command_type,
                        working_directory=working_directory,
                        timeout=60,
                        username=username
                    )
                    return result
                
                def on_success(result):
                    """API调用成功"""
                    invocation_id = result.get("InvocationId")
                    command_id = result.get("CommandId")
                    logger.info(f"API下发指令成功: InvocationId={invocation_id}, CommandId={command_id}")
                    
                    # 添加到监控列表
                    if invocation_id:
                        self.executing_invocation_ids.add(invocation_id)
                        # 启动轮询定时器（如果还没启动）
                        if not self.pending_poll_timer.isActive():
                            self.pending_poll_timer.start()
                    
                    # 显示成功消息
                    self.show_message(f"指令下发成功，共{len(selected_ids)}个实例", "success", 5000)
                
                def on_error(err_msg):
                    """API调用失败"""
                    logger.error(f"API下发指令失败: {err_msg}")
                    self.show_message(f"指令下发失败: {err_msg}", "error", 5000)
                
                # 获取主应用对象并调用后台任务
                main_app = self.window()
                if hasattr(main_app, "run_in_background"):
                    main_app.run_in_background(
                        execute_command_task,
                        callback=on_success,
                        err_callback=on_error,
                    )
                else:
                    # 降级方案：直接调用
                    try:
                        result = execute_command_task()
                        on_success(result)
                    except Exception as e:
                        on_error(str(e))
    
    def show_settings(self):
        """显示设置对话框（API凭证设置）"""
        dialog = SettingsDialog(self)
        if dialog.exec_():
            # API 凭证变更后，不在 UI 线程里同步初始化 CVMManager，
            # 而是清空已有管理器，后续在需要时按新凭证懒加载。
            if CVM_MANAGER_AVAILABLE:
                # 清空旧管理器实例，确保后续使用最新凭证重新初始化
                self.cvm_manager = None
                # 若当前已经在更新配置中，则避免重复触发，仅静默等待本轮完成
                if not getattr(self, "is_reference_updating", False):
                    # 提示用户并触发一次异步的实例配置信息预加载
                    self.show_message("API凭证已更新，正在刷新实例配置信息...", "info", 3000)
                    self._start_reference_update()
    
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
            
            current_image_id = self.custom_image_combo.currentData()
            dialog = InstanceConfigDialog(self.cvm_manager, self, current_image_id=current_image_id)
            dialog.exec_()

            # 是否是“更新配置”操作（由对话框中的按钮触发）
            is_updating_config = getattr(dialog, 'is_updating_config', False)
            if is_updating_config:
                # 交给统一的异步更新入口处理（包含提示与软 loading）
                self._start_reference_update()
            elif dialog.result() == QDialog.Accepted:
                # 正常保存实例配置
                self.show_message("实例配置已保存", "success", 2000)
                # 配置变更后刷新镜像列表（区域可能变了）
                self.refresh_image_selection()
                # 配置变更后立即同步一次并刷新本地
                self.refresh_instances(silent=True)

            # 仅在当前不处于“配置更新中”状态时，才重新启用按钮
            if not getattr(self, "is_reference_updating", False):
                self.btn_instance_config.setEnabled(True)
        except Exception as e:
            self.show_message(f"打开配置对话框失败: {str(e)}", "error", 5000)
            self.btn_instance_config.setEnabled(True)

    def _start_reference_update(self):
        """
        启动实例配置信息异步更新
        """
        # 若已在更新中，则忽略重复请求，避免并行预加载
        if getattr(self, "is_reference_updating", False):
            return
        # 获取顶层应用窗口（CVMApp），用于调度后台任务
        app_window = self.window()

        # 如果主窗口不存在或不支持 run_in_background，则直接放弃本次更新，避免阻塞 UI
        if app_window is None or not hasattr(app_window, "run_in_background"):
            self.show_message("当前窗口不支持后台更新配置，请重启程序后重试", "error", 5000)
            # 确保状态与标记被复原
            self.is_reference_updating = False
            return

        # 标记为更新中，供创建实例等操作进行拦截
        self.is_reference_updating = True
        # 在更新期间以及结束后的一小段时间内，禁止创建实例
        self.block_creates_until = float("inf")

        # 进入“配置更新中”软 loading 状态：禁用主要操作按钮
        self._set_reference_update_loading(True)
        # 立即给用户一个气泡提示
        self.show_message("已发起配置更新，请稍候...", "info", 3000)

        # 强制刷新UI，确保状态更新立即显示
        QApplication.processEvents()

        def on_done(_result):
            # 更新完成后解除"更新中"标记，并设置短暂保护期，避免积压点击触发创建
            self.is_reference_updating = False
            self.block_creates_until = time.time() + 2.0
            # 退出“配置更新中” loading 状态，恢复按钮可用
            self._set_reference_update_loading(False)
            # 提示用户更新成功，并刷新实例列表视图
            self.show_message("实例配置信息已更新", "success", 3000)
            # 延迟刷新实例列表，避免阻塞UI
            QTimer.singleShot(100, lambda: self.refresh_instances(silent=True, sync_only=True))

        def on_error(msg):
            # 更新失败后解除"更新中"标记，并设置短暂保护期
            self.is_reference_updating = False
            self.block_creates_until = time.time() + 2.0
            # 退出“配置更新中” loading 状态，恢复按钮可用
            self._set_reference_update_loading(False)
            self.show_message(f"配置更新失败: {msg}", "error", 5000)

        # 延迟启动后台任务，确保UI状态已更新
        def start_update_task():
            # 使用主窗口提供的通用后台执行器，避免阻塞 UI
            app_window.run_in_background(
                preload_reference_data,
                callback=on_done,
                auto_stop=True,
                err_callback=on_error,
                use_loading=True,
                task_desc="同步配置数据",
            )
        
        # 延迟50ms启动，确保UI状态已更新
        QTimer.singleShot(50, start_update_task)

    def on_image_source_changed(self):
        """镜像来源切换时，更新镜像列表与控件状态"""
        source = self.image_source_combo.currentData()
        if source == "PRIVATE":
            self.btn_instance_config.setEnabled(False)
            self.platform_combo.setEnabled(False)
            self.custom_image_combo.setEnabled(True)
            if not self.custom_images:
                self.load_custom_images()
        else:
            self.btn_instance_config.setEnabled(True)
            self.platform_combo.setEnabled(True)
        self.refresh_image_selection()

    def load_custom_images(self):
        """加载自定义镜像列表（后台线程，避免阻塞 UI）"""
        if not CVM_MANAGER_AVAILABLE:
            return
        if not self.cvm_manager:
            return

        manager = self.cvm_manager

        def _fetch():
            return manager.get_images("PRIVATE_IMAGE")

        def _on_done(images):
            self.custom_images = images or []
            self.refresh_image_selection()

        def _on_error(msg):
            self.custom_image_combo.clear()
            self.custom_image_combo.addItem(f"加载失败: {msg}", None)
            self.custom_image_combo.setEnabled(False)
            self.btn_create.setEnabled(False)

        main_app = self.window()
        if hasattr(main_app, "run_in_background"):
            main_app.run_in_background(
                _fetch,
                callback=_on_done,
                auto_stop=True,
                err_callback=_on_error,
                use_loading=False,
            )
        else:
            try:
                _on_done(_fetch())
            except Exception as e:
                _on_error(str(e))

    def _categorize_images(self, images):
        """按平台归类镜像"""
        buckets = {}
        for img in images or []:
            platform = (img.get("Platform") or "OTHER").upper()
            if platform.startswith("WINDOWS"):
                key = "WINDOWS"
            elif platform.startswith("UBUNTU"):
                key = "UBUNTU"
            elif platform.startswith("CENTOS"):
                key = "CENTOS"
            elif platform.startswith("DEBIAN"):
                key = "DEBIAN"
            elif platform.startswith("REDHAT") or platform.startswith("RED HAT"):
                key = "REDHAT"
            elif platform.startswith("SUSE") or platform.startswith("OPENSUSE"):
                key = "SUSE"
            elif platform.startswith("TENCENT"):
                key = "TENCENTOS"
            elif platform.startswith("OPENCLOUD"):
                key = "OPENCLOUDOS"
            elif platform.startswith("ALMA"):
                key = "ALMALINUX"
            elif platform.startswith("ROCKY"):
                key = "ROCKY"
            elif platform.startswith("FEDORA"):
                key = "FEDORA"
            elif platform.startswith("FREEBSD"):
                key = "FREEBSD"
            elif platform.startswith("COREOS"):
                key = "COREOS"
            else:
                key = "OTHER"
            buckets.setdefault(key, []).append(img)
        return buckets

    def _populate_platform_combo(self, platform_images):
        """刷新系统类型下拉框"""
        self.platform_combo.blockSignals(True)
        self.platform_combo.clear()
        platform_labels = {
            "WINDOWS": "Windows",
            "UBUNTU": "Ubuntu",
            "CENTOS": "CentOS",
            "DEBIAN": "Debian",
            "REDHAT": "RedHat",
            "SUSE": "SUSE/openSUSE",
            "TENCENTOS": "TencentOS",
            "OPENCLOUDOS": "OpenCloudOS",
            "ALMALINUX": "AlmaLinux",
            "ROCKY": "Rocky Linux",
            "FEDORA": "Fedora",
            "FREEBSD": "FreeBSD",
            "COREOS": "CoreOS",
            "OTHER": "Other"
        }
        if platform_images:
            platform_keys = list(platform_images.keys())
            # Debian 优先
            if "DEBIAN" in platform_keys:
                platform_keys = ["DEBIAN"] + [k for k in platform_keys if k != "DEBIAN"]
            if "OTHER" in platform_keys:
                platform_keys = [k for k in platform_keys if k != "OTHER"] + ["OTHER"]
            for pk in platform_keys:
                imgs = platform_images[pk]
                label = f"{platform_labels.get(pk, pk.title())} ({len(imgs)})"
                self.platform_combo.addItem(label, pk)
        else:
            self.platform_combo.addItem("无可用镜像", None)
        self.platform_combo.blockSignals(False)

    def on_platform_changed(self):
        """系统类型切换时，刷新镜像列表"""
        source = self.image_source_combo.currentData()
        if source != "PUBLIC":
            return
        platform_key = self.platform_combo.currentData()
        if not platform_key:
            return
        from config.config_manager import get_instance_config
        config = get_instance_config()
        region = config.get("default_region")
        default_image_id = config.get("default_image_id")
        if not region:
            return
        db = get_db()
        all_images = db.list_images(region, "PUBLIC_IMAGE") or []
        platform_images = self._categorize_images(all_images)
        filtered = platform_images.get(platform_key, [])
        self.custom_image_combo.clear()
        if filtered:
            selected_index = 0
            for i, img in enumerate(filtered):
                name = img.get("ImageName") or img.get("ImageId")
                self.custom_image_combo.addItem(f"{name} ({img.get('ImageId')})", img.get("ImageId"))
                if img.get("ImageId") == default_image_id:
                    selected_index = i
            self.custom_image_combo.setEnabled(True)
            self.custom_image_combo.setCurrentIndex(selected_index)
        else:
            self.custom_image_combo.addItem("无可用镜像", None)
            self.custom_image_combo.setEnabled(False)
        self.btn_create.setEnabled(bool(filtered))

    def refresh_image_selection(self):
        """根据镜像来源刷新下拉内容和创建按钮可用性"""
        source = self.image_source_combo.currentData()
        self.btn_create.setEnabled(True)
        self.custom_image_combo.clear()
        if source == "PRIVATE":
            self.btn_instance_config.setEnabled(False)
            self.platform_combo.setEnabled(False)
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
            # 公共镜像模式：按系统类型筛选
            from config.config_manager import get_instance_config
            config = get_instance_config()
            region = config.get("default_region")
            self.btn_instance_config.setEnabled(True)
            self.platform_combo.setEnabled(True)
            if region:
                db = get_db()
                all_images = db.list_images(region, "PUBLIC_IMAGE") or []
                platform_images = self._categorize_images(all_images)
                if platform_images:
                    self._populate_platform_combo(platform_images)
                    # 触发按当前平台过滤镜像
                    self.on_platform_changed()
                    return
            # 无数据时
            self.platform_combo.clear()
            self.platform_combo.addItem("无可用镜像", None)
            self.platform_combo.setEnabled(False)
            default_image_id = config.get("default_image_id") if region else None
            label = default_image_id or "请配置实例镜像"
            self.custom_image_combo.addItem(label, default_image_id)
            self.custom_image_combo.setEnabled(bool(default_image_id))
            if not default_image_id:
                self.btn_create.setEnabled(False)


