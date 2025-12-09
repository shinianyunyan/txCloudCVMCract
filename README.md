# 腾讯云 CVM 实例管理工具

基于腾讯云 API 的云服务器（CVM）实例管理工具，提供图形化界面和 Python API，实现对云服务器实例的创建、管理和批量操作。

## 项目简介

本项目提供了一套完整的腾讯云 CVM 实例管理解决方案，包含友好的图形用户界面（GUI），支持通过可视化界面或 Python 脚本管理云服务器实例，包括实例创建、批量操作、实例管理以及自定义镜像配置等功能。

## 功能特性

### 1. 智能创建实例

- **灵活配置选择**：支持自定义选择 CPU 核数、内存大小和部署区域
- **智能区域适配**：当指定区域资源不足时，自动检测并选择其他有可用资源的区域
- **密码设置**：创建实例时支持设置服务器登录密码
- **自定义镜像支持**：支持使用自定义镜像创建实例，可在创建时选择已配置的自定义镜像

### 2. 批量操作功能

- **批量开机**：支持批量启动多个实例
- **批量关机**：支持批量关闭多个实例
- **批量重置密码**：支持批量重置多个实例的登录密码

### 3. 实例管理

- **暂停实例**：支持暂停运行中的实例
- **销毁实例**：支持销毁不再需要的实例

### 4. 自定义镜像管理

- **配置自定义镜像**：支持配置和管理自定义镜像
- **镜像选择**：在创建实例时可以选择使用自定义镜像

### 5. 图形化用户界面

- **可视化操作**：提供直观的图形界面，无需编写代码即可管理实例
- **实例列表展示**：实时显示实例状态、配置信息等
- **批量选择操作**：支持在界面中多选实例进行批量操作
- **配置管理**：通过界面配置 API 凭证和默认参数

## 环境要求

- Python 3.6+
- 腾讯云账号及 API 密钥（SecretId 和 SecretKey）

## 安装说明

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装：

```bash
pip install tencentcloud-sdk-python
# 根据使用的UI框架选择安装（如：PyQt5、tkinter、streamlit等）
```

### 2. 配置 API 凭证

在项目配置文件中设置腾讯云 API 凭证：

```python
# config.py 或环境变量
SECRET_ID = "your-secret-id"
SECRET_KEY = "your-secret-key"
REGION = "ap-beijing"  # 默认区域
```

或者使用环境变量：

```bash
export TENCENT_SECRET_ID="your-secret-id"
export TENCENT_SECRET_KEY="your-secret-key"
```

## 使用方法

### 启动图形界面

```bash
python main.py
```

启动后，在图形界面中：

1. **首次使用**：在设置中配置腾讯云 API 凭证（SecretId 和 SecretKey）
2. **创建实例**：点击"创建实例"按钮，填写配置信息（核数、内存、区域、密码等）
3. **管理实例**：在实例列表中查看所有实例，支持单选或多选进行批量操作
4. **镜像管理**：在镜像管理页面配置和管理自定义镜像

### 命令行/API 使用

#### 创建实例

```python
from cvm_manager import CVMManager

manager = CVMManager()

# 创建实例，指定核数、内存、区域和密码
instance = manager.create_instance(
    cpu=2,                    # CPU 核数
    memory=4,                 # 内存大小（GB）
    region="ap-beijing",      # 区域
    password="YourPassword123!",  # 实例密码
    image_id="img-xxxxx"      # 可选：自定义镜像ID
)
```

### 批量操作

```python
# 批量开机
manager.start_instances(instance_ids=["ins-xxxxx1", "ins-xxxxx2"])

# 批量关机
manager.stop_instances(instance_ids=["ins-xxxxx1", "ins-xxxxx2"])

# 批量重置密码
manager.reset_passwords(
    instance_ids=["ins-xxxxx1", "ins-xxxxx2"],
    password="NewPassword123!"
)
```

### 实例管理

```python
# 暂停实例
manager.stop_instance(instance_id="ins-xxxxx")

# 销毁实例
manager.terminate_instance(instance_id="ins-xxxxx")
```

### 自定义镜像管理

```python
# 配置自定义镜像
manager.create_custom_image(
    instance_id="ins-xxxxx",
    image_name="my-custom-image"
)

# 获取自定义镜像列表
images = manager.list_custom_images()

# 使用自定义镜像创建实例
instance = manager.create_instance(
    cpu=2,
    memory=4,
    region="ap-beijing",
    password="YourPassword123!",
    image_id="img-custom-xxxxx"  # 使用自定义镜像
)
```

## 相关 API 文档

本项目基于腾讯云 CVM API 实现，主要使用的 API 接口包括：

- [创建实例 (RunInstances)](https://cloud.tencent.com/document/api/213/15730)
- [查询地域列表 (DescribeRegions)](https://cloud.tencent.com/document/api/213/15708)
- [查询可用区列表 (DescribeZones)](https://cloud.tencent.com/document/api/213/15709)
- [查看镜像列表 (DescribeImages)](https://cloud.tencent.com/document/api/213/15715)
- [启动实例 (StartInstances)](https://cloud.tencent.com/document/api/213/15724)
- [关闭实例 (StopInstances)](https://cloud.tencent.com/document/api/213/15725)
- [重置实例密码 (ResetInstancesPassword)](https://cloud.tencent.com/document/api/213/15736)
- [销毁实例 (TerminateInstances)](https://cloud.tencent.com/document/api/213/15727)
- [创建自定义镜像 (CreateImage)](https://cloud.tencent.com/document/api/213/16726)

完整 API 文档：https://cloud.tencent.com/document/api/213/15689

## 注意事项

### 权限管理

- 确保 API 密钥具有相应的 CVM 操作权限
- 建议使用子账号并配置最小权限原则
- 妥善保管 API 密钥，避免泄露

### 费用控制

- 实例创建和运行会产生费用，请合理规划资源使用
- 及时销毁不再使用的实例，避免产生不必要的费用
- 注意不同区域和配置的价格差异

### 区域选择

- 系统会自动适配可用区域，但建议优先选择业务就近区域
- 不同区域的实例可能存在网络延迟差异

### 密码安全

- 密码应符合腾讯云密码复杂度要求
- 建议使用强密码，并定期更换
- 批量重置密码时注意密码安全

## 项目结构

```
txCloudCVMCract/
├── README.md              # 项目说明文档
├── requirements.txt       # 依赖包列表
├── main.py               # 主程序入口（启动UI）
├── config/                # 配置相关文件
│   ├── config.py         # 配置文件
│   └── config_manager.py # 配置管理器
├── core/                  # 核心功能
│   └── cvm_manager.py    # CVM 管理核心类
├── utils/                 # 工具函数
│   └── utils.py
├── ui/                    # UI界面相关文件
│   ├── app.py            # UI应用主文件
│   ├── main_window.py    # 主窗口
│   ├── dialogs/          # 对话框
│   │   ├── create_dialog.py  # 创建实例对话框
│   │   ├── instance_config_dialog.py  # 实例配置对话框
│   │   └── settings_dialog.py # 设置对话框
│   └── components/       # UI组件
│       ├── instance_list.py  # 实例列表组件
│       └── message_bar.py    # 消息提示条
└── examples/             # 使用示例
    ├── create_instance.py
    ├── batch_operations.py
    └── image_management.py
```

## 界面预览

### 主要功能界面

- **主界面**：显示实例列表，支持筛选、搜索和批量操作
- **创建实例界面**：配置核数、内存、区域、密码和镜像选择
- **设置界面**：配置 API 凭证和默认参数
- **镜像管理界面**：查看和管理自定义镜像

## 开发计划

- [x] 实现图形化用户界面
- [ ] 实现区域自动适配逻辑
- [ ] 实现批量操作功能
- [ ] 实现自定义镜像管理
- [ ] 添加错误处理和日志记录
- [ ] 添加单元测试
- [ ] 完善文档和示例

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 参考链接

- [腾讯云云服务器 API 概览](https://cloud.tencent.com/document/api/213/15689)
- [腾讯云 Python SDK 文档](https://cloud.tencent.com/document/sdk/Python)
- [腾讯云控制台](https://console.cloud.tencent.com/cvm)

