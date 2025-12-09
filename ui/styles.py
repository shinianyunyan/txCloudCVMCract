"""
UI 样式定义模块
定义应用程序的界面样式（QSS样式表）

功能：
    - 根据屏幕DPI自动调整字体大小和间距
    - 提供统一的界面风格
    - 支持高分辨率屏幕适配

样式说明：
    - 使用QSS（Qt Style Sheets）语法，类似CSS
    - 所有CSS大括号需要转义为 {{ 和 }}（因为使用.format()方法）
    - 变量通过 .format() 方法注入
"""
import os
from PyQt5.QtWidgets import QApplication


def get_dpi_scale():
    """
    获取DPI缩放比例
    
    根据屏幕的DPI（每英寸点数）计算缩放比例
    用于在高分辨率屏幕上自动调整字体和控件大小
    
    Returns:
        float: 缩放比例，范围在1.0到2.5之间
    """
    try:
        app = QApplication.instance()
        if app is None:
            return 1.0
        screen = app.primaryScreen()
        if screen is None:
            return 1.0
        dpi = screen.logicalDotsPerInch()
        # 标准DPI是96，计算缩放比例
        scale = dpi / 96.0
        # 限制缩放范围在1.0到2.5之间，避免过大或过小
        return max(1.0, min(2.5, scale))
    except:
        return 1.0


def get_style_sheet():
    """
    获取样式表，根据DPI自动调整字体大小
    
    根据当前屏幕的DPI自动计算合适的字体大小和间距
    使界面在高分辨率屏幕上也能清晰显示
    
    Returns:
        str: 完整的QSS样式表字符串
    """
    scale = get_dpi_scale()
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    arrow_icon_down = os.path.abspath(os.path.join(assets_dir, "向下.svg")).replace("\\", "/")
    arrow_icon_up = os.path.abspath(os.path.join(assets_dir, "向上.svg")).replace("\\", "/")
    
    # 基础字体大小
    base_font_size = 13
    base_small_font_size = 12
    base_large_font_size = 14
    
    # 根据DPI缩放字体
    font_size = int(base_font_size * scale)
    small_font_size = int(base_small_font_size * scale)
    large_font_size = int(base_large_font_size * scale)
    
    # 根据DPI缩放padding和间距
    base_padding = 8
    base_small_padding = 6
    base_large_padding = 10
    
    padding = int(base_padding * scale)
    small_padding = int(base_small_padding * scale)
    large_padding = int(base_large_padding * scale)
    
    # 根据DPI缩放高度
    base_min_height = 32
    min_height = int(base_min_height * scale)
    
    # 使用普通字符串 + format()，CSS大括号需要转义为 {{ 和 }}
    style = """
/* 主窗口样式 */
QMainWindow {{
    background-color: #f5f5f5;
}}

/* 工具栏按钮样式 */
QPushButton {{
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    padding: {padding}px {padding2}px;
    font-size: {font_size}px;
    color: #333333;
    min-height: {min_height}px;
}}

QPushButton:hover {{
    background-color: #f0f0f0;
    border-color: #1890ff;
}}

QPushButton:pressed {{
    background-color: #e0e0e0;
}}

QPushButton:disabled {{
    background-color: #f5f5f5;
    color: #999999;
    border-color: #e0e0e0;
}}

/* 主要操作按钮 */
QPushButton[class="primary"] {{
    background-color: #1890ff;
    color: #ffffff;
    border-color: #1890ff;
}}

QPushButton[class="primary"]:hover {{
    background-color: #40a9ff;
    border-color: #40a9ff;
}}

QPushButton[class="primary"]:pressed {{
    background-color: #096dd9;
}}

/* 危险操作按钮 */
QPushButton[class="danger"] {{
    background-color: #ff4d4f;
    color: #ffffff;
    border-color: #ff4d4f;
}}

QPushButton[class="danger"]:hover {{
    background-color: #ff7875;
    border-color: #ff7875;
}}

QPushButton[class="danger"]:pressed {{
    background-color: #d9363e;
}}

/* 成功操作按钮 */
QPushButton[class="success"] {{
    background-color: #52c41a;
    color: #ffffff;
    border-color: #52c41a;
}}

QPushButton[class="success"]:hover {{
    background-color: #73d13d;
    border-color: #73d13d;
}}

/* 表格样式 */
QTableWidget {{
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    gridline-color: #f0f0f0;
    selection-background-color: #e6f7ff;
    selection-color: #1890ff;
    font-size: {font_size}px;
}}

QTableWidget::item {{
    padding: {padding}px;
    border: none;
}}

QTableWidget::item:selected {{
    background-color: #e6f7ff;
    color: #1890ff;
}}

QTableWidget::item:hover {{
    background-color: #fafafa;
}}

QHeaderView::section {{
    background-color: #fafafa;
    border: none;
    border-bottom: 2px solid #e0e0e0;
    border-right: 1px solid #e0e0e0;
    padding: {large_padding}px;
    font-weight: 600;
    font-size: {font_size}px;
    color: #333333;
}}

QHeaderView::section:first {{
    border-top-left-radius: 4px;
}}

QHeaderView::section:last {{
    border-top-right-radius: 4px;
    border-right: none;
}}

/* 输入框样式 */
QLineEdit, QSpinBox, QComboBox {{
    background-color: #ffffff;
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    padding: {small_padding}px {padding2}px;
    font-size: {font_size}px;
    color: #333333;
    min-height: {min_height}px;
}}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: #1890ff;
    outline: none;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 0px;
    border: none;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
    background-color: transparent;
}}

QComboBox::down-arrow {{
    image: url("{arrow_icon_down}");
    width: 12px;
    height: 12px;
    margin-right: 6px;
    margin-top: 2px;
}}

QComboBox::down-arrow:on {{
    image: url("{arrow_icon_up}");
}}

QComboBox QAbstractItemView {{
    border: 1px solid #d0d0d0;
    border-radius: 4px;
    background-color: #ffffff;
    selection-background-color: #e6f7ff;
    selection-color: #1890ff;
    padding: 4px;
}}

/* 对话框样式 */
QDialog {{
    background-color: #ffffff;
}}

QDialog QLabel {{
    color: #333333;
    font-size: {font_size}px;
}}

/* 状态栏样式 */
QStatusBar {{
    background-color: #fafafa;
    border-top: 1px solid #e0e0e0;
    color: #666666;
    font-size: {small_font_size}px;
}}

/* 菜单栏样式 */
QMenuBar {{
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    color: #333333;
    font-size: {font_size}px;
    padding: {small_padding}px;
}}

QMenuBar::item {{
    padding: {small_padding}px {padding2}px;
    border-radius: 4px;
}}

QMenuBar::item:selected {{
    background-color: #f0f0f0;
}}

QMenu {{
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: {small_padding}px;
}}

QMenu::item {{
    padding: {padding}px {padding4}px {padding}px {padding4}px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: #e6f7ff;
    color: #1890ff;
}}

/* 滚动条样式 */
QScrollBar:vertical {{
    background-color: #f5f5f5;
    width: 12px;
    border: none;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: #d0d0d0;
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #b0b0b0;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background-color: #f5f5f5;
    height: 12px;
    border: none;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: #d0d0d0;
    border-radius: 6px;
    min-width: 30px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #b0b0b0;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* 标签页样式 */
QTabWidget::pane {{
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    background-color: #ffffff;
}}

QTabBar::tab {{
    background-color: #f5f5f5;
    border: 1px solid #e0e0e0;
    border-bottom: none;
    padding: {padding}px {padding2}px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}

QTabBar::tab:selected {{
    background-color: #ffffff;
    border-color: #1890ff;
    color: #1890ff;
}}

QTabBar::tab:hover {{
    background-color: #fafafa;
}}

/* 分组框样式 */
QGroupBox {{
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
    color: #333333;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 8px;
    background-color: #ffffff;
}}

/* 工具提示样式 */
QToolTip {{
    background-color: #333333;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: {small_padding}px {large_padding}px;
    font-size: {small_font_size}px;
}}
""".format(
        padding=padding,
        padding2=padding * 2,
        padding4=int(padding * 4),
        font_size=font_size,
        small_font_size=small_font_size,
        large_font_size=large_font_size,
        small_padding=small_padding,
        large_padding=large_padding,
        min_height=min_height,
        arrow_icon_down=arrow_icon_down,
        arrow_icon_up=arrow_icon_up
    )
    return style


# 为了向后兼容，保留STYLE_SHEET变量
STYLE_SHEET = get_style_sheet()
