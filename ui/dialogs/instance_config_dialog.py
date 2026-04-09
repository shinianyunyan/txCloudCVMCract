"""
实例配置对话框。

用途：
    - 配置创建实例所需的默认参数（规格、区域、镜像、密码等）。
    - 支持后台拉取区域与公共镜像，并按平台分类筛选。
    - 提供价格预估与参数校验。
"""
import json
import os
import tempfile
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QSpinBox, QComboBox, QLineEdit, QLabel, QMessageBox, QDialogButtonBox, QScrollArea, QWidget
from PyQt5.QtCore import Qt, QThread, pyqtSignal, pyqtSlot, QTimer
from PyQt5.QtGui import QIntValidator
from config.config_manager import get_instance_config, save_instance_config
from utils.db_manager import get_db

# 延迟导入
try:
    from core.cvm_manager import CVMManager
    CVM_MANAGER_AVAILABLE = True
except ImportError:
    CVM_MANAGER_AVAILABLE = False
    CVMManager = None


class InstanceConfigDialog(QDialog):
    """
    用于设置默认实例参数的对话框。

    负责：
        - 加载已有配置并回填表单。
        - 拉取区域/镜像数据并按平台分类。
        - 校验输入、展示价格并持久化配置。
    """
    
    def __init__(self, cvm_manager=None, parent=None, current_image_id=None):
        super().__init__(parent)
        self.cvm_manager = cvm_manager
        self.current_image_id = current_image_id  # 主窗口当前选中的镜像 ID
        # 标记是否为“更新配置”操作，由主窗口根据该标记决定后续行为
        self.is_updating_config = False
        self.config_data = None
        self.regions_data = []
        self.images_data = []
        self.platform_images = {}
        self.all_images = []
        self.zones_cache = {}
        # 默认优先展示 Debian 镜像
        self.current_platform = "DEBIAN"
        self.temp_image_file = None
        self._old_threads = []  # 保存旧线程引用，防止GC在线程运行中销毁
        self.init_ui()
        self.load_from_db()
    
    def init_ui(self):
        """
        初始化UI
        
        弹窗大小设置：宽度700像素，高度500像素
        """
        self.setWindowTitle("实例配置")
        self.setModal(True)
        self.resize(700, 500)
        
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域包装表单，避免窗口过长
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area_widget = QWidget()
        form_container = QVBoxLayout(scroll_area_widget)
        form_container.setSpacing(16)
        form_container.setContentsMargins(20, 20, 20, 20)
        
        # 说明
        info_label = QLabel("配置创建实例的参数（按量计费）。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 10px;")
        form_container.addWidget(info_label)
        
        # 表单
        form_layout = QFormLayout()
        
        # CPU 核数
        self.cpu_edit = QLineEdit()
        self.cpu_edit.setText("2")
        self.cpu_edit.setValidator(QIntValidator(1, 64))
        self.cpu_edit.textChanged.connect(self.update_price)
        self.cpu_edit.setPlaceholderText("1-64")
        form_layout.addRow("CPU核数:", self.cpu_edit)
        
        # 内存大小
        memory_layout = QHBoxLayout()
        self.memory_edit = QLineEdit()
        self.memory_edit.setText("4")
        self.memory_edit.setValidator(QIntValidator(1, 256))
        self.memory_edit.textChanged.connect(self.update_price)
        self.memory_edit.setPlaceholderText("1-256")
        memory_label = QLabel("GB")
        memory_layout.addWidget(self.memory_edit)
        memory_layout.addWidget(memory_label)
        memory_layout.addStretch()
        form_layout.addRow("内存大小:", memory_layout)

        # 系统盘类型（与官方界面一致的几类）
        self.disk_type_combo = QComboBox()
        self.disk_type_combo.addItem("通用型SSD云硬盘", "CLOUD_BSSD")
        self.disk_type_combo.addItem("增强型SSD云硬盘", "CLOUD_HSSD")
        self.disk_type_combo.addItem("高性能云硬盘", "CLOUD_PREMIUM")
        self.disk_type_combo.addItem("SSD云硬盘", "CLOUD_SSD")
        self.disk_type_combo.currentIndexChanged.connect(self.on_price_related_changed)
        form_layout.addRow("系统盘类型:", self.disk_type_combo)

        # 系统盘大小（限制 20-2048 GiB，禁用滚轮触发）
        self.disk_size_edit = QSpinBox()
        self.disk_size_edit.setRange(20, 2048)
        self.disk_size_edit.setValue(50)
        self.disk_size_edit.setSuffix(" GiB")
        self.disk_size_edit.setKeyboardTracking(False)
        self.disk_size_edit.valueChanged.connect(self.on_price_related_changed)
        self.disk_size_edit.installEventFilter(self)
        form_layout.addRow("系统盘大小:", self.disk_size_edit)
        disk_hint = QLabel("范围：20-2048 GiB")
        disk_hint.setStyleSheet("color: #d9534f; font-size: 11px;")
        form_layout.addRow("", disk_hint)

        # 公网带宽（限制 1-200 Mbps，禁用滚轮）
        self.bandwidth_edit = QSpinBox()
        self.bandwidth_edit.setRange(1, 200)
        self.bandwidth_edit.setValue(10)
        self.bandwidth_edit.setSuffix(" Mbps")
        self.bandwidth_edit.setKeyboardTracking(False)
        self.bandwidth_edit.valueChanged.connect(self.on_price_related_changed)
        self.bandwidth_edit.installEventFilter(self)
        form_layout.addRow("公网带宽:", self.bandwidth_edit)
        bw_hint = QLabel("范围：1-200 Mbps")
        bw_hint.setStyleSheet("color: #d9534f; font-size: 11px;")
        form_layout.addRow("", bw_hint)

        # 带宽计费方式（官方两种：按流量后付费 / 按小时带宽后付费）
        self.bandwidth_charge_combo = QComboBox()
        self.bandwidth_charge_combo.addItem("按流量计费（后付费）", "TRAFFIC_POSTPAID_BY_HOUR")
        self.bandwidth_charge_combo.addItem("按小时带宽计费（后付费）", "BANDWIDTH_POSTPAID_BY_HOUR")
        self.bandwidth_charge_combo.currentIndexChanged.connect(self.on_price_related_changed)
        form_layout.addRow("带宽计费方式:", self.bandwidth_charge_combo)
        
        # 区域选择
        self.region_combo = QComboBox()
        self.region_combo.currentTextChanged.connect(self.on_region_changed)
        form_layout.addRow("区域:", self.region_combo)
        
        # 可用区选择
        self.zone_combo = QComboBox()
        self.zone_combo.currentTextChanged.connect(self.update_price)
        form_layout.addRow("可用区:", self.zone_combo)
        
        form_container.addLayout(form_layout)
        
        # 提示
        tip_label = QLabel("提示：可用区和镜像可以为空，创建实例时会自动选择。密码将在创建时自动生成。")
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("color: #999; font-size: 11px; padding: 5px;")
        form_container.addWidget(tip_label)
        form_container.addStretch()
        
        scroll_area.setWidget(scroll_area_widget)
        layout.addWidget(scroll_area)

        # 价格显示（放在滚动区外，便于随时查看）
        self.price_label = QLabel("价格: 请配置完整参数后查看")
        self.price_label.setWordWrap(True)
        self.price_label.setStyleSheet("color: #ff6600; font-size: 14px; font-weight: bold; padding: 10px; background-color: #fff5e6; border: 1px solid #ffcc99; border-radius: 4px;")
        layout.addWidget(self.price_label)
        
        # 底部按钮区：
        #   左侧：更新配置（触发异步刷新区域/可用区/镜像等配置信息）
        #   右侧：保存 / 取消（保存当前默认实例配置）
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.button(QDialogButtonBox.Save).setText("保存")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.save_btn = button_box.button(QDialogButtonBox.Save)
        self.update_config_btn = QPushButton("更新配置")
        self.update_config_btn.setToolTip("刷新区域、可用区与公共镜像等配置信息")
        self.update_config_btn.clicked.connect(self.on_update_config_clicked)

        btn_layout = QHBoxLayout()
        # 左侧“更新配置”按钮
        btn_layout.addWidget(self.update_config_btn)
        # 中间拉伸，右侧对齐保存/取消
        btn_layout.addStretch()
        btn_layout.addWidget(button_box)

        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def on_update_config_clicked(self):
        """
        触发“更新配置”流程：
            - 仅标记为更新配置操作，不保存当前表单内容
            - 关闭对话框，由主窗口根据 is_updating_config 启动异步更新
        """
        self.is_updating_config = True
        # 不保存当前配置，仅关闭窗口
        self.reject()
    
    def load_from_db(self):
        """从本地数据库读取预同步的数据"""
        db = get_db()
        self.config_data = get_instance_config()

        # 标准化区域字段名，兼容后续 UI 使用的键
        raw_regions = db.list_regions()
        self.regions_data = [
            {
                "Region": r.get("region") or r.get("Region"),
                "RegionName": r.get("region_name") or r.get("RegionName"),
                "RegionState": r.get("region_state") or r.get("RegionState"),
            }
            for r in raw_regions
            if r
        ]
        if not self.regions_data:
            self._show_message("数据库中缺少区域数据，请检查启动时同步是否成功", "warning")

        default_region = self.config_data.get("default_region")
        if not default_region and self.regions_data:
            default_region = self.regions_data[0].get("Region")

        if default_region:
            self.all_images = db.list_images(default_region, "PUBLIC_IMAGE") or []
        else:
            self.all_images = []
        self.platform_images = self._categorize_images(self.all_images)
        self.on_config_loaded(self.config_data, self.regions_data, self.all_images)
    
    def on_config_loaded(self, config, regions, images):
        """配置加载完成回调"""
        self.config_data = config
        self.regions_data = regions
        self.images_data = images
        self.all_images = images or []
        self.platform_images = self._categorize_images(self.all_images)
        self._save_temp_images()
        self.load_config()
    
    def load_config(self):
        """加载配置到UI"""
        if not self.config_data:
            config = get_instance_config()
        else:
            config = self.config_data
        
        # 设置默认值
        self.cpu_edit.setText(str(config.get("default_cpu", 2)))
        self.memory_edit.setText(str(config.get("default_memory", 4)))
        disk_type_val = config.get("default_disk_type", "CLOUD_PREMIUM")
        idx_disk = self.disk_type_combo.findData(disk_type_val)
        if idx_disk >= 0:
            self.disk_type_combo.setCurrentIndex(idx_disk)
        else:
            self.disk_type_combo.setCurrentText(disk_type_val)
        self.disk_size_edit.setValue(int(config.get("default_disk_size", 50)))
        self.bandwidth_edit.setValue(int(config.get("default_bandwidth", 10)))
        charge = config.get("default_bandwidth_charge", "TRAFFIC_POSTPAID_BY_HOUR")
        idx_charge = self.bandwidth_charge_combo.findData(charge)
        if idx_charge >= 0:
            self.bandwidth_charge_combo.setCurrentIndex(idx_charge)
        
        # 加载区域
        if self.regions_data:
            for region in self.regions_data:
                if region.get("RegionState") == "AVAILABLE":
                    self.region_combo.addItem(
                        f"{region['Region']} - {region['RegionName']}",
                        region['Region']
                    )
        
        # 设置已保存的配置
        if config.get("default_region"):
            index = self.region_combo.findData(config["default_region"])
            if index >= 0:
                self.region_combo.setCurrentIndex(index)
                self.on_region_changed()
        
        if config.get("default_zone"):
            index = self.zone_combo.findData(config["default_zone"])
            if index >= 0:
                self.zone_combo.setCurrentIndex(index)
        
        self.update_price()
    
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

    def _save_temp_images(self):
        """将拉取的镜像缓存到临时文件，方便后续筛选"""
        try:
            data = {
                "all_images": self.all_images,
                "platform_images_keys": list(self.platform_images.keys())
            }
            temp_path = os.path.join(tempfile.gettempdir(), "cvm_images_cache.json")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self.temp_image_file = temp_path
        except Exception:
            # 缓存失败不影响主流程
            self.temp_image_file = None

    def _cleanup_temp_images(self):
        """删除临时镜像缓存文件"""
        if self.temp_image_file and os.path.exists(self.temp_image_file):
            try:
                os.remove(self.temp_image_file)
            except Exception:
                pass

    def accept(self):
        """保存配置"""
        try:
            super().accept()
        finally:
            self._stop_price_thread()
            self._cleanup_temp_images()

    def reject(self):
        """取消配置"""
        try:
            super().reject()
        finally:
            self._stop_price_thread()
            self._cleanup_temp_images()

    def closeEvent(self, event):
        """窗口关闭时清理缓存文件"""
        self._stop_price_thread()
        self._cleanup_temp_images()
        super().closeEvent(event)
    
    def on_region_changed(self):
        """区域变化时更新可用区"""
        self.zone_combo.clear()
        self.zone_combo.addItem("(自动选择)", None)
        region_data = self.region_combo.currentData()

        if region_data:
            db = get_db()
            zones = db.list_zones(region_data)
            self.zones_cache[region_data] = zones
            for zone in zones or []:
                if zone.get("zone_state") == "AVAILABLE" or zone.get("ZoneState") == "AVAILABLE":
                    zone_code = zone.get("zone") or zone.get("Zone")
                    zone_name = zone.get("zone_name") or zone.get("ZoneName") or ""
                    self.zone_combo.addItem(f"{zone_code} - {zone_name}", zone_code)

        self.update_price()
    
    def update_price(self):
        """兼容旧调用，内部触发节流的价格查询"""
        self.schedule_price_update()

    def on_price_related_changed(self, *args, **kwargs):
        """相关字段变化时，节流触发价格查询"""
        self.schedule_price_update()

    def schedule_price_update(self):
        """延迟触发价格查询，避免频繁调用导致卡顿"""
        if getattr(self, "_price_query_running", False):
            self._price_query_pending = True
            return
        if not hasattr(self, "price_timer"):
            self.price_timer = QTimer(self)
            self.price_timer.setSingleShot(True)
            self.price_timer.timeout.connect(self._trigger_price_update)
        self.price_timer.start(400)  # 400ms 节流
        self._mark_price_pending()

    def _mark_price_pending(self):
        """标记价格查询中，禁用保存按钮，显示占位"""
        if hasattr(self, "save_btn") and self.save_btn:
            self.save_btn.setEnabled(False)
        self.price_label.setText("价格: 查询中...")

    def _trigger_price_update(self):
        """执行价格查询（后台），完成后才允许保存"""
        if not self.cvm_manager or not CVM_MANAGER_AVAILABLE:
            return
        
        cpu_text = self.cpu_edit.text().strip()
        memory_text = self.memory_edit.text().strip()
        region_data = self.region_combo.currentData()
        zone_data = self.zone_combo.currentData()
        # 镜像已移至主窗口选择，优先使用主窗口传入的当前镜像
        image_data = self.current_image_id or (self.config_data or get_instance_config()).get("default_image_id")
        disk_type = self.disk_type_combo.currentData() or self.disk_type_combo.currentText()
        disk_size = self.disk_size_edit.value()
        bandwidth = self.bandwidth_edit.value()
        bandwidth_charge = self.bandwidth_charge_combo.currentData()
        
        # 基础合法性检查
        if not cpu_text.isdigit() or int(cpu_text) <= 0:
            self.price_label.setText("价格: 请配置完整参数后查看")
            return
        if not memory_text.isdigit() or int(memory_text) <= 0:
            self.price_label.setText("价格: 请配置完整参数后查看")
            return
        if not region_data or not image_data:
            self.price_label.setText("价格: 请配置完整参数后查看")
            return
        
        cpu = int(cpu_text)
        memory = int(memory_text)
        
        from utils.utils import setup_logger
        logger = setup_logger()
        logger.info(f"开始询价: cpu={cpu}, mem={memory}, region={region_data}, zone={zone_data}, image={image_data}, disk={disk_size}({disk_type}), bw={bandwidth}, bw_charge={bandwidth_charge}")

        from PyQt5.QtCore import QObject, pyqtSignal

        # 如果上一次询价线程还在，先停止
        self._stop_price_thread()

        class PriceWorker(QObject):
            finished = pyqtSignal(dict)
            error = pyqtSignal(str)

            def __init__(self, func):
                super().__init__()
                self.func = func

            @pyqtSlot()
            def run(self):
                try:
                    res = self.func()
                    self.finished.emit(res)
                except Exception as ex:
                    self.error.emit(str(ex))

        self.price_label.setText("价格: 查询中...")
        if hasattr(self, "save_btn") and self.save_btn:
            self.save_btn.setEnabled(False)

        self._price_thread = QThread()
        self._price_worker = PriceWorker(lambda: self.cvm_manager.get_price(cpu, memory, region_data, image_data, zone_data, disk_size, bandwidth, disk_type, bandwidth_charge))
        self._price_worker.moveToThread(self._price_thread)

        def on_done(price_info):
            cvm_price = price_info.get("cvm_price", "0")
            cvm_unit = price_info.get("cvm_unit", "HOUR")
            bandwidth_price = price_info.get("bandwidth_price", "0")
            bandwidth_unit = price_info.get("bandwidth_unit", "GB")
            price_text = f"价格: 实例 {cvm_price}/{cvm_unit}"
            if bandwidth_price and bandwidth_price != "0":
                price_text += f"，带宽 {bandwidth_price}/{bandwidth_unit}"
            self.price_label.setText(price_text)
            if hasattr(self, "save_btn") and self.save_btn:
                self.save_btn.setEnabled(True)
            self._price_query_running = False
            if getattr(self, "_price_query_pending", False):
                self._price_query_pending = False
                self.schedule_price_update()

        def on_error(msg):
            error_msg = str(msg)
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            self.price_label.setText(f"价格: 查询失败 - {error_msg}")
            logger.error(f"查询价格失败: {error_msg}")
            if hasattr(self, "save_btn") and self.save_btn:
                self.save_btn.setEnabled(True)
            self._price_query_running = False
            if getattr(self, "_price_query_pending", False):
                self._price_query_pending = False
                self.schedule_price_update()

        self._price_thread.started.connect(self._price_worker.run, Qt.DirectConnection)
        self._price_worker.finished.connect(on_done)
        self._price_worker.error.connect(on_error)
        self._price_worker.finished.connect(self._price_thread.quit)
        self._price_worker.error.connect(self._price_thread.quit)
        # 线程结束后从旧线程列表中清理
        self._price_thread.finished.connect(lambda t=self._price_thread: self._cleanup_old_thread(t))
        self._price_query_running = True
        self._price_query_pending = False
        logger.info(f"开始询价: cpu={cpu}, mem={memory}, region={region_data}, zone={zone_data}, image={image_data}, disk={disk_size}({disk_type}), bw={bandwidth}, bw_charge={bandwidth_charge}")
        self._price_thread.start()

    def _stop_price_thread(self):
        """安全停止正在运行的询价线程"""
        thread = getattr(self, "_price_thread", None)
        worker = getattr(self, "_price_worker", None)
        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
                    if not thread.wait(2000):
                        # 线程仍在运行，保留引用防止GC销毁
                        self._old_threads.append((thread, worker))
            except Exception:
                pass
        self._price_thread = None
        self._price_worker = None

    def _cleanup_old_thread(self, thread):
        """线程结束后从旧线程列表中移除"""
        self._old_threads = [(t, w) for t, w in self._old_threads if t is not thread]
    
    def accept(self):
        """保存配置（同步写本地，避免多余后台日志）"""
        if not self.cvm_manager:
            self._show_message("CVM管理器未初始化，无法保存配置", "error")
            return
        
        cpu_text = self.cpu_edit.text().strip()
        memory_text = self.memory_edit.text().strip()
        region_data = self.region_combo.currentData()
        zone_data = self.zone_combo.currentData()
        # 镜像已移至主窗口选择，优先使用主窗口传入的当前镜像
        existing_config = self.config_data or get_instance_config()
        image_data = self.current_image_id or existing_config.get("default_image_id")
        
        if not cpu_text or not cpu_text.isdigit() or int(cpu_text) <= 0:
            self._show_message("请输入有效的CPU核数（大于0的数字）", "warning")
            return
        
        if not memory_text or not memory_text.isdigit() or int(memory_text) <= 0:
            self._show_message("请输入有效的内存大小（大于0的数字）", "warning")
            return
        
        cpu = int(cpu_text)
        memory = int(memory_text)
        
        if not region_data:
            self._show_message("请选择区域", "warning")
            return
        
        def do_validate_and_save():
            # 校验可用区，保存配置
            if region_data and not zone_data:
                zones = self.cvm_manager.get_zones(region_data)
                if not zones:
                    raise RuntimeError(f"区域 {region_data} 没有可用区，请检查配置")
        
            success = save_instance_config(
                int(cpu_text),
                int(memory_text),
                region_data,
                zone_data,
                image_data,
                existing_config.get("default_password", ""),
                self.disk_type_combo.currentData() or self.disk_type_combo.currentText(),
                int(self.disk_size_edit.value()),
                int(self.bandwidth_edit.value()),
                self.bandwidth_charge_combo.currentData()
            )
            if not success:
                raise RuntimeError("配置保存失败，请重试")
            return True

        # 同步校验+保存，不再走后台任务
        try:
            do_validate_and_save()
            super().accept()
        except Exception as e:
            self._show_message(str(e), "error")

    def _get_main_app(self):
        """向上找到具有 run_in_background 的主窗口"""
        parent = self.parent()
        while parent and not hasattr(parent, "run_in_background"):
            parent = parent.parent()
        return parent

    def eventFilter(self, obj, event):
        """用于禁用滚轮对特定 SpinBox 的影响"""
        from PyQt5.QtCore import QEvent
        if event.type() == QEvent.Wheel:
            block_list = [
                getattr(self, "disk_size_edit", None),
                getattr(self, "bandwidth_edit", None),
                getattr(self, "cpu_edit", None),
                getattr(self, "memory_edit", None),
                getattr(self, "region_combo", None),
                getattr(self, "zone_combo", None),
                getattr(self, "image_platform_combo", None),
                getattr(self, "image_combo", None),
                getattr(self, "disk_type_combo", None),
                getattr(self, "bandwidth_charge_combo", None),
            ]
            if obj in block_list:
                return True
        return super().eventFilter(obj, event)
    
    def _show_message(self, message, message_type):
        """显示消息提示（通过父窗口）"""
        from utils.utils import setup_logger
        logger = setup_logger()
        
        if message_type == "error":
            logger.error(f"UI消息: {message}")
        elif message_type == "warning":
            logger.warning(f"UI消息: {message}")
        else:
            logger.info(f"UI消息: {message}")
        
        if self.parent() and hasattr(self.parent(), 'show_message'):
            self.parent().show_message(message, message_type, 5000)
        else:
            # 如果无法访问父窗口的消息功能，使用默认弹窗作为后备
            if message_type == "error":
                QMessageBox.critical(self, "错误", message)
            elif message_type == "warning":
                QMessageBox.warning(self, "警告", message)
            else:
                QMessageBox.information(self, "提示", message)

