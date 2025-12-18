"""
实例列表组件。

职责：
    - 以表格形式展示实例核心信息。
    - 支持行选择、批量操作勾选、复制 IP/密码、显示/隐藏密码。
"""
import os
from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QToolButton, QWidget, QHBoxLayout, QLabel, QStyledItemDelegate
from PyQt5.QtCore import Qt, QTimer, QRect
from PyQt5.QtGui import QIcon, QClipboard
from PyQt5.QtWidgets import QApplication
from utils.utils import get_instance_status_name, get_region_name


class InstanceList(QTableWidget):
    """实例列表表格"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        """初始化表格列配置、交互模式与基础样式。"""
        # 设置列标题与顺序
        columns = ["选择", "实例ID", "实例名称", "状态", "IP", "密码", "CPU", "内存(GB)", "区域", "创建时间"]
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        
        # 设置选择/编辑行为：整行选中、不可编辑、交替行色
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setFocusPolicy(Qt.NoFocus)
        
        # 第一列复选框使用委托保持居中
        class CenteredCheckboxDelegate(QStyledItemDelegate):
            def __init__(self, table_widget, parent=None):
                super().__init__(parent)
                self.table_widget = table_widget
            
            def paint(self, painter, option, index):
                # 获取复选框状态
                item = self.table_widget.item(index.row(), index.column())
                if not item:
                    super().paint(painter, option, index)
                    return
                
                # 设置选项为居中
                option.displayAlignment = Qt.AlignCenter | Qt.AlignVCenter
                option.decorationAlignment = Qt.AlignCenter | Qt.AlignVCenter
                
                # 计算复选框应该绘制的中心位置
                rect = option.rect
                checkbox_size = 16  # 复选框大小
                x = rect.left() + (rect.width() - checkbox_size) // 2
                y = rect.top() + (rect.height() - checkbox_size) // 2
                checkbox_rect = QRect(x, y, checkbox_size, checkbox_size)
                
                # 创建复选框选项
                from PyQt5.QtWidgets import QStyleOptionButton, QStyle, QApplication
                from PyQt5.QtCore import QEvent
                checkbox_option = QStyleOptionButton()
                checkbox_option.rect = checkbox_rect
                checkbox_option.state = QStyle.State_Enabled
                if item.checkState() == Qt.Checked:
                    checkbox_option.state |= QStyle.State_On
                else:
                    checkbox_option.state |= QStyle.State_Off
                
                # 绘制复选框
                style = QApplication.style()
                style.drawControl(QStyle.CE_CheckBox, checkbox_option, painter)
            
            def editorEvent(self, event, model, option, index):
                """处理复选框点击事件"""
                from PyQt5.QtCore import QEvent
                if event.type() == QEvent.MouseButtonPress or event.type() == QEvent.MouseButtonDblClick:
                    item = self.table_widget.item(index.row(), index.column())
                    if item:
                        # 计算复选框区域
                        rect = option.rect
                        checkbox_size = 16
                        x = rect.left() + (rect.width() - checkbox_size) // 2
                        y = rect.top() + (rect.height() - checkbox_size) // 2
                        checkbox_rect = QRect(x, y, checkbox_size, checkbox_size)
                        
                        # 检查点击是否在复选框区域内
                        if checkbox_rect.contains(event.pos()):
                            # 切换复选框状态
                            if item.checkState() == Qt.Checked:
                                item.setCheckState(Qt.Unchecked)
                            else:
                                item.setCheckState(Qt.Checked)
                            return True
                return super().editorEvent(event, model, option, index)
        
        self.setItemDelegateForColumn(0, CenteredCheckboxDelegate(self, self))
        
        # 默认列宽（用户仍可手动调整）
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignCenter)
        # "选择"列需要足够宽度以显示表头文本（☑ 选择、☐ 选择、☒ 选择）
        header.setMinimumSectionSize(80)
        self.setColumnWidth(0, 80)
        
        # 在表头第一列添加全选复选框（使用自定义表头项）
        header_item = QTableWidgetItem("☑ 选择")
        header_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.setHorizontalHeaderItem(0, header_item)
        
        # 连接表头点击事件，实现全选功能
        header.sectionClicked.connect(self._on_header_section_clicked)
        
        # 连接项目改变事件，监听复选框状态变化
        self.itemChanged.connect(self._on_item_changed)
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
        
        # 隐藏行头，保持网格线
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        
        # 基础样式：去除虚线框，突出选中行
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
        """根据实例数据刷新表格行，并附加复制/显示密码控件。"""
        # 保存当前选中的实例ID列表
        selected_ids = self.get_selected_instance_ids()
        
        # 禁用重绘以提高性能，避免 UI 卡顿
        self.setUpdatesEnabled(False)
        
        try:
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
                
                # 连接复选框状态改变事件，更新表头状态
                # 注意：QTableWidgetItem 没有直接的信号，我们需要通过 itemChanged 信号来监听
                
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
                
                # 创建时间
                created_time = instance.get("CreatedTime", "")
                self.setItem(row, 9, QTableWidgetItem(str(created_time)))
            
            # 恢复之前选中的复选框状态（暂时断开信号避免触发更新）
            self.itemChanged.disconnect(self._on_item_changed)
            for row in range(self.rowCount()):
                instance_id_item = self.item(row, 1)
                if instance_id_item and instance_id_item.text() in selected_ids:
                    checkbox = self.item(row, 0)
                    if checkbox:
                        checkbox.setCheckState(Qt.Checked)
            self.itemChanged.connect(self._on_item_changed)
            
            # 确保"选择"列宽度足够（防止被压缩）
            if self.columnWidth(0) < 80:
                self.setColumnWidth(0, 80)
            
            # 更新表头复选框状态
            self._update_header_checkbox_state()
        finally:
            # 恢复重绘，确保 UI 更新
            self.setUpdatesEnabled(True)
    
    def _create_copy_cell(self, text):
        """创建带复制按钮的 IP 单元格。"""
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
        """创建可显示/隐藏与复制密码的单元格。"""
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
    
    def clear_selection(self):
        """清除所有复选框的选中状态"""
        for row in range(self.rowCount()):
            checkbox = self.item(row, 0)
            if checkbox:
                checkbox.setCheckState(Qt.Unchecked)
        # 更新表头复选框状态
        self._update_header_checkbox_state()
    
    def _on_item_changed(self, item):
        """处理项目改变事件，更新表头复选框状态"""
        # 只处理第一列（复选框列）的变化
        if item.column() == 0:
            self._update_header_checkbox_state()
    
    def _on_header_section_clicked(self, logical_index):
        """处理表头点击事件，实现全选/取消全选功能"""
        if logical_index == 0:  # 第一列（选择列）
            # 检查当前是否全部选中
            all_checked = True
            has_items = False
            for row in range(self.rowCount()):
                checkbox = self.item(row, 0)
                if checkbox:
                    has_items = True
                    if checkbox.checkState() != Qt.Checked:
                        all_checked = False
                        break
            
            # 如果全部选中则取消全选，否则全选
            new_state = Qt.Unchecked if all_checked and has_items else Qt.Checked
            
            for row in range(self.rowCount()):
                checkbox = self.item(row, 0)
                if checkbox:
                    checkbox.setCheckState(new_state)
            
            # 更新表头显示
            self._update_header_checkbox_state()
    
    def _update_header_checkbox_state(self):
        """更新表头复选框的显示状态"""
        if self.rowCount() == 0:
            header_item = self.horizontalHeaderItem(0)
            if header_item:
                header_item.setText("☐ 选择")
            return
        
        # 检查是否全部选中
        all_checked = True
        any_checked = False
        for row in range(self.rowCount()):
            checkbox = self.item(row, 0)
            if checkbox:
                if checkbox.checkState() == Qt.Checked:
                    any_checked = True
                else:
                    all_checked = False
        
        header_item = self.horizontalHeaderItem(0)
        if header_item:
            if all_checked and any_checked:
                header_item.setText("☑ 选择")
            elif any_checked:
                header_item.setText("☒ 选择")  # 部分选中
            else:
                header_item.setText("☐ 选择")


