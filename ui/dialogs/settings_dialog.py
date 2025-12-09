"""
设置对话框
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QDialogButtonBox, QMessageBox, QLabel, QApplication, QHBoxLayout
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
import os, sys
from config.config_manager import get_api_config, save_api_config
from config.config import SECRET_ID, SECRET_KEY, DEFAULT_REGION

try:
    from core.api_validator import validate_api
    API_VALIDATOR_AVAILABLE = True
except ImportError:
    API_VALIDATOR_AVAILABLE = False
    validate_api = None


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_settings()
    
    def init_ui(self):
        """
        初始化UI
        
        弹窗大小设置：宽度600像素，高度350像素
        如需调整，修改下面的 resize() 参数
        """
        self.setWindowTitle("设置")
        self.setModal(True)
        # 弹窗大小：宽度600，高度350（可根据需要调整）
        self.resize(600, 350)
        
        layout = QVBoxLayout()
        
        # 说明
        info_label = QLabel("请配置腾讯云 API 凭证。您可以在腾讯云控制台的 API 密钥管理中获取。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(info_label)
        
        # 表单
        form_layout = QFormLayout()
        
        # SecretId
        self.secret_id_edit = QLineEdit()
        self.secret_id_edit.setPlaceholderText("请输入 SecretId")
        form_layout.addRow("SecretId:", self.secret_id_edit)
        
        # SecretKey
        self.secret_key_edit = QLineEdit()
        self.secret_key_edit.setEchoMode(QLineEdit.Password)
        self.secret_key_edit.setPlaceholderText("请输入 SecretKey")
        form_layout.addRow("SecretKey:", self.secret_key_edit)
        
        # 默认区域
        self.region_edit = QLineEdit()
        self.region_edit.setPlaceholderText("例如: ap-beijing")
        form_layout.addRow("默认区域:", self.region_edit)
        
        # 验证状态标签（放在表单下方）
        self.validate_status_label = QLabel()
        self.validate_status_label.setWordWrap(True)
        self.validate_status_label.setStyleSheet("""
            QLabel {
                padding: 8px;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        self.validate_status_label.setVisible(False)
        form_layout.addRow("", self.validate_status_label)
        
        layout.addLayout(form_layout)
        
        # 提示
        tip_label = QLabel("提示：您也可以通过环境变量 TENCENT_SECRET_ID 和 TENCENT_SECRET_KEY 来配置。")
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("color: #999; font-size: 10px; padding: 5px;")
        layout.addWidget(tip_label)
        
        layout.addStretch()
        
        # 验证按钮
        self.validate_btn = QPushButton("验证凭证")
        self.validate_btn.setProperty("class", "")
        self.validate_btn.clicked.connect(self.validate_credentials)
        self.validate_btn.setToolTip("验证 API 凭证是否有效")
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        # 将验证按钮添加到按钮框
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.validate_btn)
        button_layout.addStretch()
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def load_settings(self):
        """加载设置（从配置文件热读取）"""
        # 从配置文件读取（支持热更新）
        api_config = get_api_config()
        secret_id = api_config.get("secret_id") or SECRET_ID
        secret_key = api_config.get("secret_key") or SECRET_KEY
        region = api_config.get("default_region") or DEFAULT_REGION
        
        if secret_id:
            self.secret_id_edit.setText(secret_id)
        if secret_key:
            self.secret_key_edit.setText(secret_key)
        if region:
            self.region_edit.setText(region)
    
    def validate_credentials(self):
        """验证API凭证有效性"""
        secret_id = self.secret_id_edit.text().strip()
        secret_key = self.secret_key_edit.text().strip()
        region = self.region_edit.text().strip() or "ap-beijing"
        
        if not secret_id or not secret_key:
            self.validate_status_label.setText("❌ 请先输入 SecretId 和 SecretKey")
            self.validate_status_label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    background-color: #fff1f0;
                    color: #ff4d4f;
                }
            """)
            self.validate_status_label.setVisible(True)
            return
        
        if not API_VALIDATOR_AVAILABLE:
            self.validate_status_label.setText("⚠️ API 验证功能不可用")
            self.validate_status_label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    background-color: #fffbe6;
                    color: #faad14;
                }
            """)
            self.validate_status_label.setVisible(True)
            return
        
        # 显示验证中状态
        self.validate_btn.setEnabled(False)
        self.validate_btn.setText("验证中...")
        self.validate_status_label.setText("⏳ 正在验证 API 凭证...")
        self.validate_status_label.setStyleSheet("""
            QLabel {
                padding: 8px;
                border-radius: 4px;
                font-size: 12px;
                background-color: #e6f7ff;
                color: #1890ff;
            }
        """)
        self.validate_status_label.setVisible(True)
        
        # 在后台线程中验证（避免阻塞UI）
        self.validate_thread = ValidationThread(secret_id, secret_key, region)
        self.validate_thread.finished.connect(self.on_validation_finished)
        self.validate_thread.start()
    
    def on_validation_finished(self, is_valid, message):
        """验证完成回调"""
        self.validate_btn.setEnabled(True)
        self.validate_btn.setText("验证凭证")
        
        if is_valid:
            self.validate_status_label.setText(f"✅ {message}")
            self.validate_status_label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    background-color: #f6ffed;
                    color: #52c41a;
                }
            """)
        else:
            self.validate_status_label.setText(f"❌ {message}")
            self.validate_status_label.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    background-color: #fff1f0;
                    color: #ff4d4f;
                }
            """)
        self.validate_status_label.setVisible(True)
    
    def accept(self):
        """
        确认设置（热更新，无需重启）
        """
        secret_id = self.secret_id_edit.text().strip()
        secret_key = self.secret_key_edit.text().strip()
        region = self.region_edit.text().strip()
        if not region:
            region = "ap-beijing"
        
        if not secret_id or not secret_key:
            self._show_message("请输入SecretId和SecretKey", "warning")
            return
        
        success = save_api_config(secret_id, secret_key, region)
        
        if success:
            # 直接关闭对话框，消息由主窗口显示
            super().accept()
        else:
            # 使用消息提示代替弹窗
            self._show_message("配置保存失败，请重试", "error")
    
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


class ValidationThread(QThread):
    """API验证线程（避免阻塞UI）"""
    finished = pyqtSignal(bool, str)
    
    def __init__(self, secret_id, secret_key, region):
        super().__init__()
        self.secret_id = secret_id
        self.secret_key = secret_key
        self.region = region
    
    def run(self):
        """执行验证"""
        try:
            from core.api_validator import validate_api
            is_valid, message = validate_api(self.secret_id, self.secret_key, self.region)
            self.finished.emit(is_valid, message)
        except Exception as e:
            self.finished.emit(False, f"验证过程出错: {str(e)}")


