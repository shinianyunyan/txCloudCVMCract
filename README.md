# 腾讯云 CVM 实例管理工具

基于腾讯云 API v3 的 PyQt5 桌面图形工具，用于管理和批量创建 CVM 实例。内置 Go 高并发预加载模块（编译为 DLL，通过 ctypes 直接调用），实现区域、可用区、镜像、实例数据的快速同步与本地缓存。**支持 PyInstaller 打包为单文件 exe 分发。**

## 主要功能

### 实例创建与管理
- **双镜像来源**：公共镜像（按平台分类筛选，支持 Debian、Ubuntu、CentOS、Windows 等 13 种平台）或自定义镜像（自动拉取账号下私有镜像列表）
- **批量创建**：一键创建 1–100 台实例，支持自定义 CPU / 内存 / 磁盘 / 带宽参数
- **实时询价**：实例配置对话框中修改参数后自动计算价格；价格查询使用主窗口当前选中的镜像

### 批量操作
- **批量开机 / 关机 / 销毁**：对选中实例一键操作
- **批量重置密码**：运行中实例先关机再重置并自动开机；已关机实例仅重置密码
- **下发指令**：基于腾讯云 TAT API，向 Linux / Windows 实例批量下发命令
  - 支持手动输入或从本地文件读取指令内容
  - 自动识别实例操作系统，设置命令类型（SHELL / POWERSHELL）和工作目录
  - 实时监控指令执行状态

### 实例列表
- 展示实例 ID、名称、状态（彩色标识）、IP、CPU、内存、区域、创建时间
- 实例 ID 和 IP 支持一键复制
- **密码管理**：每台实例独立存储密码，支持显示 / 隐藏切换与一键复制
- 表头全选 / 取消全选复选框

### 配置与缓存
- **设置对话框**：录入 API 凭证（SecretId / SecretKey），支持在线验证有效性
- **实例配置对话框**：保存默认 CPU / 内存 / 区域 / 可用区 / 磁盘类型与大小 / 带宽 / 镜像等参数
- **数据缓存**：区域、可用区、镜像列表通过 Go DLL 同步到本地 SQLite，离线时可使用缓存数据

### 其他
- **全异步**：所有网络操作均通过 QThread + pyqtSlot 在独立线程执行，不阻塞界面
- **自动刷新**：
  - 每 60 秒同步云端实例到本地（先 upsert 已获取的实例，后标记不存在的实例为已删除）
  - 每 4 秒轮询本地缓存刷新 UI（不触发 API 调用，避免竞态）
  - 实例关机后 (STOPPED 状态) 保持可见，仅销毁后才从列表移除
- **异常容错**：网络抖动或回调异常不会导致程序崩溃
- **日志**：界面顶部消息栏实时提示，`cvm_manager.log` 记录关键操作

## 界面截图

| 主界面 | 主界面（实例列表） |
|:---:|:---:|
| ![mainWindow](images/mainWindow.png) | ![mainWindow2](images/mainWindow2.png) |

| 设置 | 实例配置 | 下发指令 |
|:---:|:---:|:---:|
| ![setting](images/setting.jpg) | ![creating](images/creating.jpg) | ![runCommand](images/runCommand.jpg) |

## 环境要求

### 直接使用（推荐）
- 从 Release 下载 `txCloudCVM.exe`，双击即可运行，无需安装任何依赖

### 源码运行 / 开发
- Python 3.8+（推荐 3.10+）
- 腾讯云账号与 API 密钥（SecretId、SecretKey）
- 依赖：PyQt5、tencentcloud-sdk-python、requests（见 `requirements.txt`）
- Go 1.20+（可选）：仅在需要重新编译预加载 DLL 时使用；仓库已包含编译好的 `go_preload.dll`

## 快速开始

### 方式一：单文件 exe（推荐）
1. 下载 `txCloudCVM.exe`
2. 双击运行
3. 首次启动后，点击工具栏「设置」按钮，填写腾讯云 API 凭证并保存

> 数据库和日志文件会自动在 exe 同目录下创建（`data/cvm_cache.db`、`cvm_manager.log`）

### 方式二：源码运行
```bash
pip install -r requirements.txt
python main.py
```

### 配置 API 凭证
首次启动后，点击工具栏「设置」按钮，填写腾讯云 API 凭证并保存。

也可通过环境变量预配置：
```powershell
# Windows PowerShell
$env:TENCENT_SECRET_ID = "xxx"
$env:TENCENT_SECRET_KEY = "xxx"
```
```bash
# Linux / macOS
export TENCENT_SECRET_ID=xxx
export TENCENT_SECRET_KEY=xxx
```

## 启动流程

```
main.py 启动
  ↓ ensure_config_file() — 自动创建数据库与默认配置
  ↓ 显示加载窗口（带点动画）
  ↓ 后台线程通过 ctypes 调用 Go DLL
  ↓ Go 模块并发拉取区域 / 可用区 / 镜像 / 实例，写入 SQLite
  ↓ 预加载完成 → 关闭加载窗口，主界面从 SQLite 读取数据
```

- 首次运行时 `data/cvm_cache.db` 会自动创建，无需手动操作
- 预加载失败时程序仍可正常启动，使用已有缓存数据

## Go 预加载模块

Go 代码编译为 c-shared DLL，Python 通过 ctypes 直接调用，无需独立进程或 HTTP 通信：

- 并发调用腾讯云 API：`DescribeRegions` / `DescribeZones` / `DescribeImages`（分页遍历）/ `DescribeInstances`
- 实例同步流程：先从 API 拉取所有已存在实例并合并到本地 SQLite，再对比 API 结果标记本地已销毁/不存在的实例
- 数据直接写入本地 SQLite（WAL 模式），支持多线程并发访问
- 导出函数：
  | 函数 | 说明 |
  |------|------|
  | `GoPreloadInit(dbPath, logPath)` | 初始化数据库与日志路径 |
  | `GoPreloadAll(secretID, secretKey, region)` | 同步全量数据，返回 `"OK"` 或 `"ERROR:..."` |
  | `GoFreeString(ptr)` | 释放 Go 分配的 C 字符串内存 |

Python 侧职责：
- 通过 ctypes 加载 `go_preload.dll` 并调用导出函数完成区域 / 可用区 / 镜像 / 实例的预加载
- 从 SQLite 读取缓存数据刷新 UI
- 后续实例创建 / 开关机 / 销毁 / 重置密码 / 下发指令等操作直接调用腾讯云 SDK（不依赖 Go）
- 管理 QThread 生命周期，确保后台任务不阻塞界面

### ctypes 与 Go 指针生命周期

Go DLL 返回 C 字符串时采用 `c_void_p`（而非 `c_char_p`）以保留原始指针，配合 `GoFreeString` 由 Go 端正确释放，避免内存错误。

### 自行编译 Go DLL（可选）

仓库已包含编译好的 DLL。如需重新编译（需 Go 1.20+ 且 CGO 可用）：

```bash
cd go_preload
CGO_ENABLED=1 go build -buildmode=c-shared -o go_preload.dll main.go
```

> **没有 Go DLL 时：** 程序可正常启动，已有缓存时使用旧数据，首次无缓存时列表为空。实例操作功能不受影响。

## 打包为单文件 exe

项目支持通过 PyInstaller 打包为单个可执行文件，包含 Python 运行时、Go DLL 和所有 UI 资源：

```bash
pip install pyinstaller
pyinstaller txCloudCVM.spec --clean -y
```

产物在 `dist/txCloudCVM.exe`（约 45 MB）。运行时数据库和日志自动创建在 exe 同目录下。

## 数据安全

- **API 凭据**存储在本地 SQLite 数据库中，不随代码提交（`data/`、`*.db` 已在 `.gitignore` 中排除）
- **实例密码**以明文存储在本地数据库，仅用于界面展示和复制，不会上传
- 运行时环境变量（`TENCENT_SECRET_ID` / `TENCENT_SECRET_KEY`）仅在当前进程有效

## 行为与限制
- **密码复杂度**：按腾讯云官方规则校验（Linux / Windows 规则差异已处理）
- **批量操作**：数量受腾讯云 API 限制（通常 100 台/次），自动过滤已处于目标状态的实例
- **下发指令**：实例需安装 TAT Agent 且处于 RUNNING 状态；新版公共镜像通常已预装
- **创建实例**：需满足账户余额与配额

## 项目结构

```
├── main.py                  # 程序入口
├── config/
│   └── config_manager.py    # 配置管理（读写 SQLite）
├── core/
│   ├── cvm_manager.py       # 腾讯云 CVM API 封装
│   ├── api_validator.py     # API 凭证验证
│   └── preload.py           # 预加载逻辑（ctypes 调用 Go DLL）
├── ui/
│   ├── app.py               # 主窗口 & 异步任务调度
│   ├── main_window.py       # 工具栏、镜像选择、批量操作
│   ├── styles.py            # 全局样式
│   ├── components/
│   │   ├── instance_list.py # 实例列表组件
│   │   └── message_bar.py   # 顶部消息栏
│   └── dialogs/
│       ├── settings_dialog.py         # 设置对话框
│       ├── instance_config_dialog.py  # 实例配置对话框
│       ├── password_dialog.py         # 密码重置对话框
│       └── send_command_dialog.py     # 下发指令对话框
├── utils/
│   ├── db_manager.py        # SQLite 数据库管理
│   └── utils.py             # 日志、路径兼容等工具函数
├── go_preload/
│   ├── main.go              # Go 预加载模块（c-shared DLL 源码）
│   └── go_preload.dll       # 编译产物，随仓库分发
├── data/                    # 运行时数据（gitignored）
├── txCloudCVM.spec          # PyInstaller 打包配置
└── requirements.txt
```

## 代码示例（二次开发参考）

```python
from core.cvm_manager import CVMManager

manager = CVMManager(None, None, None)

# 创建实例
manager.create(
    cpu=2, memory=4, region="ap-beijing",
    password="YourPassword123!", image_id=None,
    instance_name="demo", zone=None, count=1
)

# 获取实例列表
instances = manager.get_instances(None)

# 批量开机 / 关机
ids = [i["InstanceId"] for i in instances[:2]]
manager.start(ids)
manager.stop(ids, force=False)

# 重置密码
manager.reset_pwd(ids, "NewPassword123!")

# 下发指令
result = manager.run_command(
    instance_ids=ids,
    command_content="ls -l /root",
    command_type="SHELL",
    working_directory="/root",
    timeout=60,
    username="root"
)

# 查询执行结果
tasks = manager.describe_invocation_tasks(invocation_id=result["InvocationId"])
for task in tasks["InvocationTaskSet"]:
    print(f"实例 {task['InstanceId']}: 状态={task['TaskStatus']}")

# 销毁实例
manager.terminate(ids)
```

## 注意事项
- **API 密钥安全**：妥善保管 API 密钥，建议使用子账号并配置最小权限
- **费用管理**：关注实例费用，按需关机或销毁
- **TAT Agent**：新版公共镜像通常已预装；旧镜像或自定义镜像可能需要手动安装

