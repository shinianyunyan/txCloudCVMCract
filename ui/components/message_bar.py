"""
消息提示条组件。

用于在主窗口内以叠加方式展示多条错误/警告/成功/提示信息，
自动处理消息队列、位置与定时隐藏。
"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QColor, QPalette, QPainter
import uuid


class MessageItem(QWidget):
    """单条消息组件，负责绘制背景、图标及关闭按钮。"""
    
    closed = pyqtSignal(object)  # 关闭时发出信号，传递自身
    
    def __init__(self, message: str, message_type: str = "info", duration: int = 5000, parent=None):
        super().__init__(parent)
        self.message_id = str(uuid.uuid4())
        self.message_type = message_type
        self.duration = duration
        # 设为子部件，跟随父窗口隐藏/最小化
        self.setWindowFlags(Qt.Widget)
        # 确保MessageItem不继承父容器的透明背景，并且能正确显示背景颜色
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_NoSystemBackground, False)  # 允许系统背景
        self.init_ui()
        self.set_message(message)
        
        # 定时器，用于自动隐藏
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.close_message)
        
        if duration > 0:
            self.hide_timer.start(duration)
    
    def init_ui(self):
        """构建消息行的布局与关闭按钮。"""
        layout = QHBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 消息图标和文本
        self.message_label = QLabel()
        self.message_label.setWordWrap(False)
        self.message_label.setTextFormat(Qt.RichText)
        self.message_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # 关闭按钮
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.clicked.connect(self.close_message)
        
        layout.addWidget(self.message_label)
        layout.addStretch()
        layout.addWidget(self.close_btn)
        layout.setAlignment(self.close_btn, Qt.AlignVCenter)
        layout.setAlignment(self.message_label, Qt.AlignVCenter)
        
        self.setLayout(layout)
        self.setMinimumHeight(40)
    
    def set_message(self, message: str):
        """设置消息内容"""
        icon_map = {
            "error": "❌",
            "warning": "⚠️",
            "success": "✅",
            "info": "ℹ️"
        }
        icon = icon_map.get(self.message_type, "ℹ️")
        self.message_label.setText(f"{icon} {message}")
        
        # 设置背景颜色和文字颜色
        color_map = {
            "error": ("#fff1f0", "#d32f2f"),  # 浅红色背景，深红色文字
            "warning": ("#fffbe6", "#d48806"),  # 浅黄色背景，深黄色文字
            "success": ("#f6ffed", "#389e0d"),  # 浅绿色背景，深绿色文字
            "info": ("#e6f7ff", "#0958d9")  # 浅蓝色背景，深蓝色文字
        }
        bg_color, text_color = color_map.get(self.message_type, ("#e6f7ff", "#0958d9"))
        
        # 使用对象名来确保样式只应用到当前MessageItem，不影响父容器
        self.setObjectName("MessageItem")
        
        # 保存背景颜色，用于paintEvent绘制
        self.bg_color = bg_color
        self.text_color = text_color
        
        # 先设置QPalette背景颜色（更可靠的方法）
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(bg_color))
        self.setPalette(palette)
        self.setAutoFillBackground(True)  # 必须设置为True才能显示背景
        
        # 设置样式表
        self.setStyleSheet(f"""
            MessageItem#MessageItem {{
                background-color: {bg_color};
                border: none;
                border-radius: 4px;
            }}
            MessageItem#MessageItem QLabel {{
                color: {text_color};
                font-size: 14px;
                font-weight: 500;
                padding: 4px;
                background-color: transparent;
            }}
            MessageItem#MessageItem QPushButton {{
                background-color: transparent;
                border: none;
                color: {text_color};
                font-size: 18px;
                font-weight: bold;
                border-radius: 12px;
            }}
            MessageItem#MessageItem QPushButton:hover {{
                background-color: rgba(0, 0, 0, 0.1);
            }}
        """)
        
        # 调整大小以适应内容
        self.adjustSize()
    
    def close_message(self):
        """关闭消息并停止自动隐藏定时器。"""
        self.hide_timer.stop()
        self.closed.emit(self)
    
    def get_height(self):
        """获取消息高度"""
        return self.height()
    
    def paintEvent(self, event):
        """绘制圆角背景后交由父类渲染文本与按钮。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制圆角矩形背景（无边框）
        rect = self.rect()
        painter.setBrush(QColor(self.bg_color))
        painter.setPen(Qt.NoPen)  # 无边框
        painter.drawRoundedRect(rect, 4, 4)
        
        # 调用父类的paintEvent绘制其他内容
        super().paintEvent(event)


class MessageBar(QWidget):
    """
    消息提示条管理器
    
    支持显示多个不同类型的消息（错误、警告、成功、信息）
    自动管理消息队列，当消息消失时自动上移其他消息
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setVisible(False)
        
        # 设置为主窗口子窗口，确保只在主界面范围内显示
        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        
        # 移除所有透明背景设置
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        
        self.messages = []  # 存储所有消息项
        self.message_spacing = 16  # 消息之间的间距（增加间距，确保有间隔）
        self.top_margin = 20  # 距离顶部距离
        self.right_margin = 20  # 距离右侧距离
        
        self.init_ui()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.message_spacing)
        self.setLayout(layout)
        
        # MessageBar容器本身不设置背景色，让MessageItem的背景色显示出来
        # 使用对象名避免影响子组件
        self.setObjectName("MessageBar")
        self.setStyleSheet("""
            QWidget#MessageBar {
                background-color: transparent;
            }
        """)
    
    def show_message(self, message, message_type, duration):
        """
        显示消息
        
        Args:
            message: 消息内容
            message_type: 消息类型（error, warning, success, info）
            duration: 显示时长（毫秒），0表示不自动隐藏
        """
        # 创建新的消息项（独立窗口，不添加到布局）
        message_item = MessageItem(message, message_type, duration, self.parent_window)
        message_item.closed.connect(self.remove_message)
        
        # 添加到列表（不添加到布局，因为每个都是独立窗口）
        self.messages.append(message_item)
        
        # 显示消息项
        message_item.show()
        
        # 更新位置和大小
        self.update_layout()
    
    def remove_message(self, message_item: MessageItem):
        """移除消息"""
        if message_item in self.messages:
            self.messages.remove(message_item)
            message_item.close()  # 关闭独立窗口
            message_item.deleteLater()
            
            # 更新布局
            self.update_layout()
    
    def update_layout(self):
        """更新布局和位置"""
        if not self.parent_window:
            return
        
        parent_rect = self.parent_window.geometry()
        # 设置合适的宽度（父窗口宽度的35%，最小250，最大400）- 做小一点
        width = max(250, min(400, int(parent_rect.width() * 0.35)))
        
        # 计算右侧位置（不居中）
        x = parent_rect.x() + parent_rect.width() - width - self.right_margin
        y = parent_rect.y() + self.top_margin
        
        # 更新每个消息项的位置和大小（每个都是独立窗口）
        for i, msg in enumerate(self.messages):
            # 设置消息项宽度
            msg.setFixedWidth(width)
            
            # 更新每个消息项的标签宽度，以便正确换行和计算高度
            # 减去左右padding(16+16)、间距(12)、关闭按钮宽度(24)
            label_max_width = width - 16 - 16 - 12 - 24
            msg.message_label.setMaximumWidth(label_max_width)
            
            # 强制更新布局以重新计算高度
            msg.updateGeometry()
            msg.adjustSize()  # 重新调整大小以适应内容
            
            # 计算消息项的Y位置（考虑之前的消息高度和间距）
            msg_y = y
            for j in range(i):
                msg_y += self.messages[j].height() + self.message_spacing
            
            # 移动消息项到正确位置
            msg.move(x, msg_y)
    
    def show_error(self, message: str, duration: int = 5000):
        """显示错误消息"""
        self.show_message(message, "error", duration)
    
    def show_warning(self, message: str, duration: int = 5000):
        """显示警告消息"""
        self.show_message(message, "warning", duration)
    
    def show_success(self, message: str, duration: int = 3000):
        """显示成功消息"""
        self.show_message(message, "success", duration)
    
    def show_info(self, message: str, duration: int = 3000):
        """显示信息消息"""
        self.show_message(message, "info", duration)
