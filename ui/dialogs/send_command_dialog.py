"""
下发指令对话框。

用途：
    - 用户输入需要下发的指令
    - 支持从文件读取指令内容
    - 支持确定和取消操作
"""
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QDialogButtonBox, QFileDialog, QMessageBox
from PyQt5.QtCore import Qt


class SendCommandDialog(QDialog):
    """
    下发指令对话框。
    
    用于输入需要下发的指令内容。
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.command_text = ""
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("下发指令")
        self.setModal(True)
        self.resize(600, 400)
        
        layout = QVBoxLayout()
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 说明标签
        info_label = QLabel("请输入需要下发的指令：")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 13px; padding: 5px;")
        layout.addWidget(info_label)
        
        # 指令输入框
        self.command_edit = QTextEdit()
        self.command_edit.setPlaceholderText("请输入指令内容...")
        self.command_edit.setStyleSheet("""
            QTextEdit {
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 13px;
            }
            QTextEdit:focus {
                border: 1px solid #1890ff;
            }
        """)
        layout.addWidget(self.command_edit)
        
        # 按钮区域：左侧"选择文件"按钮，右侧"确定"和"取消"按钮
        button_layout = QHBoxLayout()
        
        # 左侧：选择文件按钮
        self.btn_select_file = QPushButton("选择文件")
        self.btn_select_file.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #d0d0d0;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-color: #1890ff;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """)
        self.btn_select_file.clicked.connect(self.on_select_file_clicked)
        button_layout.addWidget(self.btn_select_file)
        
        # 右侧：确定和取消按钮
        button_layout.addStretch()  # 添加弹性空间，将按钮推到右侧
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.button(QDialogButtonBox.Ok).setText("确定")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def on_select_file_clicked(self):
        """选择文件按钮点击事件"""
        # 打开文件选择对话框
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择文件",
            "",  # 默认路径为空，使用系统默认
            "所有文件 (*.*);;文本文件 (*.txt);;脚本文件 (*.sh *.bat *.ps1);;Python文件 (*.py)"
        )
        
        if not file_path:
            return  # 用户取消了文件选择
        
        try:
            # 读取文件内容
            # 尝试使用UTF-8编码
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # 如果UTF-8失败，尝试使用GBK编码（常见于Windows中文环境）
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    # 如果都失败，使用latin-1（不会失败，但可能显示乱码）
                    with open(file_path, 'r', encoding='latin-1') as f:
                        content = f.read()
            
            # 将内容填充到输入框
            self.command_edit.setPlainText(content)
        except Exception as e:
            QMessageBox.critical(
                self,
                "错误",
                f"读取文件失败：\n{str(e)}"
            )
    
    def get_command(self):
        """获取输入的指令内容"""
        return self.command_edit.toPlainText().strip()
    
    def accept(self):
        """确定按钮点击事件"""
        command = self.get_command()
        if not command:
            QMessageBox.warning(self, "提示", "请输入指令内容")
            return
        
        self.command_text = command
        super().accept()

