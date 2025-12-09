"""
实例配置对话框
用于配置创建实例时的默认参数
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QPushButton, QSpinBox, QComboBox, QLineEdit, QLabel, QMessageBox, QDialogButtonBox
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIntValidator
from config.config_manager import get_instance_config, save_instance_config

# 延迟导入
try:
    from core.cvm_manager import CVMManager
    CVM_MANAGER_AVAILABLE = True
except ImportError:
    CVM_MANAGER_AVAILABLE = False
    CVMManager = None


class ConfigLoadThread(QThread):
    """配置加载线程"""
    data_loaded = pyqtSignal(dict, list, list)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, cvm_manager):
        super().__init__()
        self.cvm_manager = cvm_manager
    
    def run(self):
        """在后台线程中加载数据"""
        try:
            from config.config_manager import get_instance_config
            config = get_instance_config()
            
            regions = []
            images = []
            
            if self.cvm_manager:
                try:
                    default_region = config.get("default_region")
                    if default_region:
                        if default_region != self.cvm_manager.region:
                            self.cvm_manager._init_client(default_region)
                    regions = self.cvm_manager.get_regions()
                    images = self.cvm_manager.get_images("PUBLIC_IMAGE")
                except Exception as e:
                    self.error_occurred.emit(str(e))
                    return
            
            self.data_loaded.emit(config, regions, images)
        except Exception as e:
            self.error_occurred.emit(str(e))


class InstanceConfigDialog(QDialog):
    """实例配置对话框"""
    
    def __init__(self, cvm_manager=None, parent=None):
        super().__init__(parent)
        self.cvm_manager = cvm_manager
        self.config_data = None
        self.regions_data = []
        self.images_data = []
        self.init_ui()
        self.start_load_config()
    
    def init_ui(self):
        """
        初始化UI
        
        弹窗大小设置：宽度700像素，高度500像素
        """
        self.setWindowTitle("实例配置")
        self.setModal(True)
        self.resize(700, 500)
        
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 说明
        info_label = QLabel("配置创建实例的参数（按量计费）。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(info_label)
        
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
        
        # 区域选择
        self.region_combo = QComboBox()
        self.region_combo.currentTextChanged.connect(self.on_region_changed)
        form_layout.addRow("区域:", self.region_combo)
        
        # 可用区选择
        self.zone_combo = QComboBox()
        self.zone_combo.currentTextChanged.connect(self.update_price)
        form_layout.addRow("可用区:", self.zone_combo)
        
        # 镜像选择
        self.image_combo = QComboBox()
        self.image_combo.currentTextChanged.connect(self.update_price)
        form_layout.addRow("镜像:", self.image_combo)
        
        # 密码
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Linux: 8-16位，至少2项；Windows: 12-16位，至少3项")
        form_layout.addRow("密码:", self.password_edit)
        
        # 确认密码
        self.password_confirm_edit = QLineEdit()
        self.password_confirm_edit.setEchoMode(QLineEdit.Password)
        form_layout.addRow("确认密码:", self.password_confirm_edit)
        
        layout.addLayout(form_layout)
        
        # 价格显示
        self.price_label = QLabel("价格: 请配置完整参数后查看")
        self.price_label.setWordWrap(True)
        self.price_label.setStyleSheet("color: #ff6600; font-size: 14px; font-weight: bold; padding: 10px; background-color: #fff5e6; border: 1px solid #ffcc99; border-radius: 4px;")
        layout.addWidget(self.price_label)
        
        # 提示
        tip_label = QLabel("提示：可用区和镜像可以为空，创建实例时会自动选择。密码必须设置。")
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("color: #999; font-size: 11px; padding: 5px;")
        layout.addWidget(tip_label)
        
        layout.addStretch()
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.button(QDialogButtonBox.Save).setText("保存")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def start_load_config(self):
        """启动异步加载配置"""
        self.load_thread = ConfigLoadThread(self.cvm_manager)
        self.load_thread.data_loaded.connect(self.on_config_loaded)
        self.load_thread.error_occurred.connect(self.on_load_error)
        self.load_thread.start()
    
    def on_config_loaded(self, config, regions, images):
        """配置加载完成回调"""
        self.config_data = config
        self.regions_data = regions
        self.images_data = images
        self.load_config()
    
    def on_load_error(self, error_msg):
        """加载错误回调"""
        self.config_data = get_instance_config()
        self.regions_data = []
        self.images_data = []
        self.load_config()
        self._show_message(f"无法加载数据: {error_msg}", "error")
    
    def load_config(self):
        """加载配置到UI"""
        if not self.config_data:
            config = get_instance_config()
        else:
            config = self.config_data
        
        # 设置默认值
        self.cpu_edit.setText(str(config.get("default_cpu", 2)))
        self.memory_edit.setText(str(config.get("default_memory", 4)))
        
        if config.get("default_password"):
            self.password_edit.setText(config["default_password"])
            self.password_confirm_edit.setText(config["default_password"])
        
        # 加载区域和镜像
        if self.regions_data:
            for region in self.regions_data:
                if region.get("RegionState") == "AVAILABLE":
                    self.region_combo.addItem(
                        f"{region['Region']} - {region['RegionName']}",
                        region['Region']
                    )
        
        if self.images_data:
            self.image_combo.addItem("(自动选择)", None)
            for image in self.images_data[:20]:
                self.image_combo.addItem(
                    f"{image['ImageName']} ({image['ImageId']})",
                    image['ImageId']
                )
        
        # 设置已保存的配置
        if config.get("default_region"):
            index = self.region_combo.findData(config["default_region"])
            if index >= 0:
                self.region_combo.setCurrentIndex(index)
                self.on_region_changed()
        
        if config.get("default_image_id"):
            index = self.image_combo.findData(config["default_image_id"])
            if index >= 0:
                self.image_combo.setCurrentIndex(index)
        
        if config.get("default_zone"):
            index = self.zone_combo.findData(config["default_zone"])
            if index >= 0:
                self.zone_combo.setCurrentIndex(index)
        
        self.update_price()
    
    def on_region_changed(self):
        """区域变化时更新可用区"""
        self.zone_combo.clear()
        self.zone_combo.addItem("(自动选择)", None)
        self.update_price()
        
        if not self.cvm_manager:
            return
        
        region_data = self.region_combo.currentData()
        if not region_data:
            return
        
        try:
            zones = self.cvm_manager.get_zones(region_data)
            if zones:
                for zone in zones:
                    if zone.get("ZoneState") == "AVAILABLE":
                        self.zone_combo.addItem(
                            f"{zone['Zone']} - {zone['ZoneName']}",
                            zone['Zone']
                        )
        except Exception as e:
            self._show_message(f"无法加载可用区: {str(e)}", "error")
    
    def update_price(self):
        """更新价格显示"""
        if not self.cvm_manager or not CVM_MANAGER_AVAILABLE:
            return
        
        cpu_text = self.cpu_edit.text().strip()
        memory_text = self.memory_edit.text().strip()
        region_data = self.region_combo.currentData()
        zone_data = self.zone_combo.currentData()
        image_data = self.image_combo.currentData()
        
        if not cpu_text or not cpu_text.isdigit() or int(cpu_text) <= 0:
            self.price_label.setText("价格: 请配置完整参数后查看")
            return
        
        if not memory_text or not memory_text.isdigit() or int(memory_text) <= 0:
            self.price_label.setText("价格: 请配置完整参数后查看")
            return
        
        if not region_data:
            self.price_label.setText("价格: 请配置完整参数后查看")
            return
        
        if not image_data:
            self.price_label.setText("价格: 请配置完整参数后查看")
            return
        
        cpu = int(cpu_text)
        memory = int(memory_text)
        
        try:
            price_info = self.cvm_manager.get_price(cpu, memory, region_data, image_data, zone_data, 0, 0)
            
            cvm_price = price_info.get("cvm_price", "0")
            cvm_unit = price_info.get("cvm_unit", "HOUR")
            bandwidth_price = price_info.get("bandwidth_price", "0")
            bandwidth_unit = price_info.get("bandwidth_unit", "GB")
            
            price_text = f"价格: 实例 {cvm_price} 元/{cvm_unit}"
            if bandwidth_price and bandwidth_price != "0":
                price_text += f" | 带宽 {bandwidth_price} 元/{bandwidth_unit}"
            
            self.price_label.setText(price_text)
        except Exception as e:
            error_msg = str(e)
            if len(error_msg) > 50:
                error_msg = error_msg[:47] + "..."
            self.price_label.setText(f"价格: 查询失败 - {error_msg}")
    
    def accept(self):
        """保存配置"""
        if not self.cvm_manager:
            self._show_message("CVM管理器未初始化，无法保存配置", "error")
            return
        
        cpu_text = self.cpu_edit.text().strip()
        memory_text = self.memory_edit.text().strip()
        region_data = self.region_combo.currentData()
        zone_data = self.zone_combo.currentData()
        image_data = self.image_combo.currentData()
        password = self.password_edit.text()
        password_confirm = self.password_confirm_edit.text()
        
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
        
        if not password:
            self._show_message("请输入密码", "warning")
            return
        
        if password != password_confirm:
            self._show_message("两次输入的密码不一致", "warning")
            return
        
        if image_data:
            try:
                images = self.cvm_manager.get_images("PUBLIC_IMAGE")
                for img in images:
                    if img['ImageId'] == image_data:
                        break
            except:
                pass
        
        from utils.utils import validate_password
        is_valid, error_msg = validate_password(password)
        if not is_valid:
            self._show_message(f"密码验证失败: {error_msg}", "error")
            return
        
        if region_data and not zone_data:
            try:
                zones = self.cvm_manager.get_zones(region_data)
                if not zones:
                    self._show_message(f"区域 {region_data} 没有可用区，请检查配置", "error")
                    return
            except Exception as e:
                self._show_message(f"无法验证区域配置: {str(e)}", "error")
                return
        
        if image_data:
            try:
                images = self.cvm_manager.get_images("PUBLIC_IMAGE")
                all_images = [img['ImageId'] for img in images]
                if image_data not in all_images:
                    self._show_message(f"镜像 {image_data} 不可用，请重新选择", "error")
                    return
            except Exception as e:
                self._show_message(f"无法验证镜像配置: {str(e)}", "error")
                return
        
        success = save_instance_config(int(cpu_text), int(memory_text), region_data, zone_data, image_data, password)
        
        if success:
            super().accept()
        else:
            self._show_message("配置保存失败，请重试", "error")
    
    def showEvent(self, event):
        """对话框显示事件"""
        super().showEvent(event)
        if hasattr(self, 'load_thread') and self.load_thread.isRunning():
            pass
    
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

