"""
密码输入对话框。

场景：批量重置实例密码时，输入并即时校验新密码。
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QLabel, QPushButton, QDialogButtonBox, QMessageBox
from PyQt5.QtCore import Qt
from utils.utils import validate_password, setup_logger


class PasswordDialog(QDialog):
    """密码输入与校验对话框，支持实时提示与一致性检查。"""
    
    def __init__(self, parent=None, is_windows=False):
        super().__init__(parent)
        self.is_windows = is_windows
        self.init_ui()
    
    def init_ui(self):
        """构建密码输入表单、提示信息与确认按钮。"""
        self.setWindowTitle("重置密码")
        self.setModal(True)
        self.resize(400, 250)
        
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        tip_text = "密码要求：8-30位，至少包含大小写字母、数字和特殊字符中的至少三种"
        tip_label = QLabel(tip_text)
        tip_label.setWordWrap(True)
        tip_label.setStyleSheet("color: #666; font-size: 12px; padding: 5px;")
        layout.addWidget(tip_label)
        
        form_layout = QFormLayout()
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("请输入新密码")
        self.password_edit.textChanged.connect(self.validate_password_input)
        form_layout.addRow("新密码:", self.password_edit)
        
        password_hint = QLabel("")
        password_hint.setStyleSheet("font-size: 11px; padding-left: 5px;")
        form_layout.addRow("", password_hint)
        self.password_hint = password_hint
        
        self.password_confirm_edit = QLineEdit()
        self.password_confirm_edit.setEchoMode(QLineEdit.Password)
        self.password_confirm_edit.setPlaceholderText("请再次输入密码")
        self.password_confirm_edit.textChanged.connect(self.validate_confirm_input)
        form_layout.addRow("确认密码:", self.password_confirm_edit)
        
        confirm_hint = QLabel("")
        confirm_hint.setStyleSheet("font-size: 11px; padding-left: 5px;")
        form_layout.addRow("", confirm_hint)
        self.confirm_hint = confirm_hint
        
        layout.addLayout(form_layout)
        layout.addStretch()
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setText("确定")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
        self.is_password_valid = False
        self.is_confirm_valid = False
    
    def validate_password_input(self):
        """实时验证密码输入"""
        password = self.password_edit.text()
        if not password:
            self.password_hint.setText("")
            self.is_password_valid = False
            return
        
        is_valid, error_msg = validate_password(password)
        if is_valid:
            self.password_hint.setText("* 密码合规")
            self.password_hint.setStyleSheet("font-size: 11px; padding-left: 5px; color: #28a745;")
            self.is_password_valid = True
        else:
            self.password_hint.setText(f"* {error_msg}")
            self.password_hint.setStyleSheet("font-size: 11px; padding-left: 5px; color: #dc3545;")
            self.is_password_valid = False
        
        self.validate_confirm_input()
    
    def validate_confirm_input(self):
        """实时验证确认密码输入"""
        password = self.password_edit.text()
        password_confirm = self.password_confirm_edit.text()
        
        if not password_confirm:
            self.confirm_hint.setText("")
            self.is_confirm_valid = False
            return
        
        if password == password_confirm:
            self.confirm_hint.setText("* 密码一致")
            self.confirm_hint.setStyleSheet("font-size: 11px; padding-left: 5px; color: #28a745;")
            self.is_confirm_valid = True
        else:
            self.confirm_hint.setText("* 两次输入的密码不一致")
            self.confirm_hint.setStyleSheet("font-size: 11px; padding-left: 5px; color: #dc3545;")
            self.is_confirm_valid = False
    
    def accept(self):
        """验证密码"""
        logger = setup_logger()
        password = self.password_edit.text()
        password_confirm = self.password_confirm_edit.text()
        
        if not password:
            msg = "请输入密码"
            logger.warning(f"UI消息: {msg}")
            QMessageBox.warning(self, "警告", msg)
            return
        
        if not self.is_password_valid:
            msg = "密码不符合要求"
            logger.error(f"UI消息: {msg}")
            QMessageBox.critical(self, "错误", msg)
            return
        
        if not self.is_confirm_valid:
            msg = "两次输入的密码不一致"
            logger.warning(f"UI消息: {msg}")
            QMessageBox.warning(self, "警告", msg)
            return
        
        super().accept()
    
    def get_password(self):
        """获取输入的密码"""
        return self.password_edit.text()





