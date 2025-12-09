"""
实例列表组件
"""
import os
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QToolButton, QWidget, QHBoxLayout, QLabel, QStyledItemDelegate
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon, QClipboard
from PyQt5.QtWidgets import QApplication
from utils.utils import get_instance_status_name, get_region_name


class InstanceList(QTableWidget):
    """实例列表表格"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        # 设置列
        columns = ["选择", "实例ID", "实例名称", "状态", "IP", "密码", "CPU", "内存(GB)", "区域", "可用区", "创建时间"]
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        
        # 设置选择模式
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setFocusPolicy(Qt.NoFocus)
        
        # 设置第一列（复选框列）的委托，确保复选框居中
        class CenteredCheckboxDelegate(QStyledItemDelegate):
            def initStyleOption(self, option, index):
                super().initStyleOption(option, index)
                option.displayAlignment = Qt.AlignCenter | Qt.AlignVCenter
        
        self.setItemDelegateForColumn(0, CenteredCheckboxDelegate(self))
        
        # 设置列宽（可手动调整，自动适配内容）
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignCenter)
        self.setColumnWidth(0, 50)
        self.setColumnWidth(1, 170)
        self.setColumnWidth(2, 170)
        self.setColumnWidth(3, 90)
        self.setColumnWidth(4, 170)
        self.setColumnWidth(5, 190)
        self.setColumnWidth(6, 70)
        self.setColumnWidth(7, 90)
        self.setColumnWidth(8, 130)
        self.setColumnWidth(9, 120)
        self.setColumnWidth(10, 180)
        
        # 设置行高
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        
        # 设置表格样式（移除虚线框，美化选中效果）
        self.setStyleSheet("""
            QTableWidget {
                border: 1px solid #e0e0e0;
                background-color: #ffffff;
                gridline-color: #f0f0f0;
                alternate-background-color: #f9f9f9;
            }
            QTableWidget::item {
                border: none;
                padding: 5px;
            }
            QTableWidget::item:focus,
            QTableWidget::item:selected:focus {
                outline: none;
                border: none;
                background-color: #e3f2fd;
            }
            QTableWidget::item:selected {
                background-color: #e3f2fd;
                border: none;
                outline: none;
            }
            QTableWidget::item {
                outline: none;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
                padding: 8px 12px;
                font-weight: 500;
            }
            QTableCornerButton::section {
                background-color: #f8f9fa;
                border: 1px solid #e0e0e0;
            }
        """)
    
    def update_instances(self, instances):
        """更新实例列表"""
        self.setRowCount(0)
        
        for instance in instances:
            row = self.rowCount()
            self.insertRow(row)
            
            # 选择框（使用复选框，居中显示）
            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checkbox.setCheckState(Qt.Unchecked)
            checkbox.setText("")
            checkbox.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.setItem(row, 0, checkbox)
            
            # 实例ID
            self.setItem(row, 1, QTableWidgetItem(instance.get("InstanceId", "")))
            
            # 实例名称
            self.setItem(row, 2, QTableWidgetItem(instance.get("InstanceName", "")))
            
            # 状态
            status = instance.get("InstanceState", "")
            status_item = QTableWidgetItem(get_instance_status_name(status))
            # 根据状态设置颜色
            if status == "RUNNING":
                status_item.setForeground(Qt.darkGreen)
            elif status == "STOPPED":
                status_item.setForeground(Qt.darkRed)
            elif status == "PENDING":
                status_item.setForeground(Qt.darkYellow)
            self.setItem(row, 3, status_item)
            
            # IP（带复制功能）
            ip_address = instance.get("IpAddress", "")
            ip_widget = self._create_copy_cell(ip_address)
            self.setCellWidget(row, 4, ip_widget)
            
            # 密码（默认隐藏）
            password = instance.get("Password", "")
            masked = "*" * len(password) if password else ""
            pwd_widget = self._create_password_cell(password, masked)
            self.setCellWidget(row, 5, pwd_widget)
            
            # CPU
            self.setItem(row, 6, QTableWidgetItem(str(instance.get("CPU", ""))))
            
            # 内存
            self.setItem(row, 7, QTableWidgetItem(str(instance.get("Memory", ""))))
            
            # 区域
            region = instance.get("Region", "")
            self.setItem(row, 8, QTableWidgetItem(f"{region} ({get_region_name(region)})"))
            
            # 可用区
            self.setItem(row, 9, QTableWidgetItem(instance.get("Zone", "")))
            
            # 创建时间
            created_time = instance.get("CreatedTime", "")
            self.setItem(row, 10, QTableWidgetItem(str(created_time)))
    
    def _create_copy_cell(self, text):
        """创建带复制功能的单元格"""
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignVCenter)
        label = QLabel(text)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        copy_icon = QIcon(os.path.join(assets_dir, "复制.svg"))
        copied_icon = QIcon(os.path.join(assets_dir, "已复制.svg"))
        
        btn = QToolButton()
        btn.setAutoRaise(False)
        btn.setFixedSize(20, 20)
        btn.setIcon(copy_icon)
        btn.setIconSize(btn.size() * 0.7)
        btn.setToolTip("复制")
        btn.setStyleSheet("""
            QToolButton { 
                border: none; 
                background: transparent; 
                padding: 0; 
                margin: 0;
            }
            QToolButton:pressed { 
                background: transparent; 
            }
        """)
        
        timer = QTimer()
        timer.setSingleShot(True)
        
        def copy_text():
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            btn.setIcon(copied_icon)
            btn.setToolTip("已复制")
            timer.timeout.connect(lambda: (btn.setIcon(copy_icon), btn.setToolTip("复制")))
            timer.start(2000)
        
        btn.clicked.connect(copy_text)
        layout.addWidget(label, 0, Qt.AlignVCenter)
        layout.addWidget(btn, 0, Qt.AlignVCenter)
        layout.addStretch()
        container.setLayout(layout)
        return container
    
    def _create_password_cell(self, password, masked):
        """创建带显示/隐藏和复制功能的密码单元格"""
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignVCenter)
        label = QLabel(masked)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
        show_icon = QIcon(os.path.join(assets_dir, "眼睛_显示.svg"))
        hide_icon = QIcon(os.path.join(assets_dir, "眼睛_隐藏.svg"))
        copy_icon = QIcon(os.path.join(assets_dir, "复制.svg"))
        copied_icon = QIcon(os.path.join(assets_dir, "已复制.svg"))
        
        eye_btn = QToolButton()
        eye_btn.setCheckable(True)
        eye_btn.setAutoRaise(False)
        eye_btn.setFixedSize(20, 20)
        eye_btn.setIcon(show_icon)
        eye_btn.setIconSize(eye_btn.size() * 0.7)
        eye_btn.setToolTip("显示/隐藏密码")
        eye_btn.setStyleSheet("""
            QToolButton { 
                border: none; 
                background: transparent; 
                padding: 0; 
                margin: 0;
            }
            QToolButton:pressed { 
                background: transparent; 
            }
            QToolButton:checked { 
                background: transparent; 
            }
        """)
        
        copy_btn = QToolButton()
        copy_btn.setAutoRaise(False)
        copy_btn.setFixedSize(20, 20)
        copy_btn.setIcon(copy_icon)
        copy_btn.setIconSize(copy_btn.size() * 0.7)
        copy_btn.setToolTip("复制密码")
        copy_btn.setStyleSheet("""
            QToolButton { 
                border: none; 
                background: transparent; 
                padding: 0; 
                margin: 0;
            }
            QToolButton:pressed { 
                background: transparent; 
            }
        """)
        
        timer = QTimer()
        timer.setSingleShot(True)
        
        def toggle():
            if eye_btn.isChecked():
                label.setText(password)
                eye_btn.setIcon(hide_icon)
            else:
                label.setText(masked)
                eye_btn.setIcon(show_icon)
        
        def copy_password():
            clipboard = QApplication.clipboard()
            clipboard.setText(password)
            copy_btn.setIcon(copied_icon)
            copy_btn.setToolTip("已复制")
            timer.timeout.connect(lambda: (copy_btn.setIcon(copy_icon), copy_btn.setToolTip("复制密码")))
            timer.start(2000)
        
        eye_btn.toggled.connect(toggle)
        copy_btn.clicked.connect(copy_password)
        layout.addWidget(label, 0, Qt.AlignVCenter)
        layout.addWidget(eye_btn, 0, Qt.AlignVCenter)
        layout.addWidget(copy_btn, 0, Qt.AlignVCenter)
        layout.addStretch()
        container.setLayout(layout)
        return container
    
    def get_selected_instance_ids(self):
        """获取选中的实例ID列表"""
        selected_ids = []
        for row in range(self.rowCount()):
            checkbox = self.item(row, 0)
            if checkbox and checkbox.checkState() == Qt.Checked:
                instance_id_item = self.item(row, 1)
                if instance_id_item:
                    selected_ids.append(instance_id_item.text())
        return selected_ids


