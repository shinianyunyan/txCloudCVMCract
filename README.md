# 腾讯云 CVM 实例管理工具

基于腾讯云 API v3 的桌面图形工具，用于管理和批量创建 CVM 实例（公共镜像 / 自定义镜像）。

## 主要功能
- **实例创建**：公共镜像（用实例配置中的镜像 ID）或自定义镜像（自动拉取账号下私有镜像列表）
- **批量操作**：开机、关机、销毁、重置密码、下发指令
- **下发指令**：基于腾讯云 TAT（自动化工具）API，支持向 Linux/Windows 实例批量下发命令
  - 支持从本地文件读取指令内容
  - 自动识别实例操作系统类型（Linux/Windows）
  - 自动设置命令类型和工作目录
  - 实时监控指令执行状态
- **密码重置行为**：运行中实例会被强制关机，重置完成后自动开机；已关机实例保持关机
- **实例列表**：展示状态/IP/配置，密码支持显示/隐藏与复制
- **配置管理**：界面可保存默认 CPU/内存/区域/公共镜像/密码，启动时自动读取；支持更新配置信息（区域、可用区、镜像）
- **异步操作**：所有批量操作采用异步处理，不阻塞界面，实时反馈操作状态
- **日志与提示**：界面消息提示，`cvm_manager.log` 记录关键操作

## 主要功能界面
![mainWindow](https://github.com/shinianyunyan/txCloudCVMCract/blob/master/images/mainWindow.jpg)
![mainWindow2](https://github.com/shinianyunyan/txCloudCVMCract/blob/master/images/mainwindow2.jpg)
![setting](https://github.com/shinianyunyan/txCloudCVMCract/blob/master/images/setting.jpg)
![crearing](https://github.com/shinianyunyan/txCloudCVMCract/blob/master/images/creating.jpg)
![runCommand](https://github.com/shinianyunyan/txCloudCVMCract/blob/master/images/runCommand.jpg)

## 环境要求
- Python 3.8+（推荐 3.10+）
- 腾讯云账号与 API 密钥（SecretId、SecretKey）
- 依赖：PyQt5、tencentcloud-sdk-python、requests（见 `requirements.txt`）
- Go 1.20+：用于构建本地预加载服务，负责区域 / 可用区 / 公共镜像 / 实例列表全量同步到本地 SQLite

## 安装
```bash
pip install -r requirements.txt
```

## 配置 API 凭证与默认参数
- 方式一：首次启动后，在界面中的「设置」里填写并保存 API 凭证
- 方式二：使用环境变量
  - Windows PowerShell: `set TENCENT_SECRET_ID=xxx`，`set TENCENT_SECRET_KEY=xxx`
  - Linux/macOS: `export TENCENT_SECRET_ID=xxx`，`export TENCENT_SECRET_KEY=xxx`

## 启动图形界面
```bash
python main.py
```

启动流程说明：
- 程序启动后会先显示一个加载窗口（Splash），然后执行：
  - 尝试启动或连接本地 Go 预加载服务（`go_preload/go_preload_server.exe`）；
  - 由 Go 服务拉取「区域 / 可用区 / 公共镜像 / 实例列表」，并写入本地 SQLite 缓存库；
- Go 预加载成功：关闭加载窗口，主界面从 SQLite 中读取最新数据；
- Go 预加载失败（未编译、未找到或调用失败）：
  - 启动不会中断，加载窗口会提示“预加载失败，将使用缓存数据”；
  - 主界面仍然可以打开，并**只使用现有 SQLite 缓存**（如果是第一次启动且没有缓存，则相关列表为空）；
  - 此时启动预加载 / 手动点击「更新配置」不会再由 Python 直接访问腾讯云，只读取旧缓存。

## Go 预加载服务

本项目内置一个基于 Go 的 HTTP 服务，用来接管以下「高负载、IO 密集」的工作：

- 高并发调用腾讯云 CVM API：`DescribeRegions` / `DescribeZones` / `DescribeImages` / `DescribeInstances`
- 直接写入本地 SQLite 数据库（`data/cvm_cache.db`，启用 WAL 模式和合理的 busy_timeout）
- 提供 HTTP 接口给 Python 侧调用：
  - `/health`：健康检查
  - `/preload_all`：一次性同步区域/可用区/镜像/实例到 SQLite

Python 侧此时只负责：
- 在启动时或手动点击「更新配置」时，通过 HTTP 触发 Go 服务的 `/preload_all`
- 从本地 SQLite 中读取区域 / 可用区 / 公共镜像 / 实例列表并刷新 UI
- 实例的创建 / 开关机 / 销毁 / 重置密码 / 下发指令等操作仍由 Python 直接调用腾讯云 SDK 完成（不依赖 Go）

### 构建 Go 预加载服务

前提：已安装 Go 1.20+，并在命令行中可执行 `go`。

```bash
cd go_preload
go build -o go_preload_server.exe main.go
```

成功后会在 `go_preload/` 下生成 `go_preload_server.exe`，Python 在启动时会自动检测并按需拉起该服务。

> **没有 Go 服务时的行为：**
>
> - 程序可以正常启动，主界面也能打开；
> - 只要本地已有 `data/cvm_cache.db`，界面就会使用其中的缓存数据；
> - Python 没有访问腾讯云的功能，启动预加载 / 手动点击「更新配置」不会刷新为最新配置，只能使用旧数据；
> - 实例的创建 / 开机 / 关机 / 销毁 / 重置密码 / 下发指令等功能仍可使用，它们直接调用腾讯云 SDK，不依赖 Go 服务。

## 界面操作要点
- **设置**：录入并保存 API 凭证（必填，否则无法正常调用腾讯云接口）
- **实例配置**：设置创建实例时使用的默认参数（CPU / 内存 / 区域 / 公共镜像 ID / 密码 等）
  - 提供「更新配置信息」按钮，用于刷新区域 / 可用区 / 公共镜像缓存
- **镜像来源**：
  - 公共镜像：从配置的公共镜像 ID 创建实例；
  - 自定义镜像：从账号的私有镜像列表中选择，选中后实例配置中的镜像选项不再生效；
- **刷新**：从本地 SQLite 缓存读取实例列表并更新界面
- **创建实例**：按当前镜像来源和数量创建实例；如果缺少必要配置（如密码）按钮会处于禁用状态
- **批量操作**：
  - **批量开机**：对选中且当前处于关机状态的实例发起开机；
  - **批量关机**：对选中且当前处于运行状态的实例发起关机；
  - **批量销毁**：销毁选中的实例；
  - **批量重置密码**：运行中实例会先关机，重置完成后自动开机；已关机实例仅重置密码；
  - **下发指令**：
    - 选中需要执行指令的实例（必须是同一操作系统类型）；
    - 在对话框中输入指令内容或从本地文件读取；
    - 支持 Linux（SHELL）和 Windows（POWERSHELL）命令；
    - 程序会根据实例类型设置命令类型和工作目录。

## Python 代码示例（仅供二次开发参考）
```python
from core.cvm_manager import CVMManager

# 使用 config_manager 时，可传入 None 自动读取配置文件
manager = CVMManager(None, None, None)

# 创建实例（单台）
manager.create(
    cpu=2,
    memory=4,
    region="ap-beijing",
    password="YourPassword123!",
    image_id=None,
    instance_name="demo",
    zone=None,
    count=1
)

# 获取实例列表
instances = manager.get_instances(None)

# 批量开机/关机
ids = [i["InstanceId"] for i in instances[:2]]
manager.start(ids)
manager.stop(ids, force=False)

# 重置密码（运行中会强制关机并在完成后自动开机）
manager.reset_pwd(ids, "NewPassword123!")

# 下发指令（需要实例安装 TAT Agent）
result = manager.run_command(
    instance_ids=ids,
    command_content="ls -l /root",
    command_type="SHELL",
    working_directory="/root",
    timeout=60,
    username="root"
)
invocation_id = result["InvocationId"]

# 查询指令执行结果
tasks = manager.describe_invocation_tasks(invocation_id=invocation_id)
for task in tasks["InvocationTaskSet"]:
    print(f"实例 {task['InstanceId']}: 状态={task['TaskStatus']}, 退出码={task['TaskResult']['ExitCode']}")

# 销毁实例
manager.terminate(ids)
```

## 行为与限制说明
- **密码复杂度**：按腾讯云官方规则校验（Linux/Windows 规则差异已处理）
- **重置密码**：运行中实例 ForceStop 后重置并自动开机；关机实例不自动开机
- **批量操作**：
  - 批量操作数量受腾讯云 API 限制（通常 100 台/次）
  - 自动过滤已处于目标状态的实例，避免重复操作
  - 所有操作采用异步处理，实时反馈状态
- **下发指令**：
  - 实例必须安装 TAT Agent 才能使用下发指令功能
    - 注意：腾讯云的新版公共镜像通常已预装 TAT Agent
    - 如果使用旧镜像或自定义镜像，可能需要手动安装
  - 实例必须处于 RUNNING 状态
  - 实例必须处于 VPC 网络
  - 同时只能对单一操作系统类型（Linux 或 Windows）的实例下发指令
  - 支持从本地文件读取指令内容
- **创建实例**：需满足账户余额与配额

## 项目结构
```
txCloudCVMCract/
├── README.md
├── requirements.txt
├── main.py                  # 启动 GUI，显示加载窗口并通过 Go 预加载基础数据
├── config/
│   └── config_manager.py    # 读取/保存默认参数与凭证
├── core/
│   ├── cvm_manager.py       # 核心 API 封装（CVM + TAT）
│   └── preload.py           # 预加载入口，仅负责调用本地 Go 预加载服务
├── go_preload/              # Go 预加载服务（高并发拉取 + 写 SQLite）
│   ├── main.go
│   ├── go.mod
│   ├── go.sum
│   └── go_preload_server.exe（构建后生成）
├── ui/
│   ├── app.py               # 主应用窗口
│   ├── main_window.py       # 主界面逻辑
│   ├── dialogs/
│   │   ├── settings_dialog.py          # 设置对话框
│   │   ├── instance_config_dialog.py   # 实例配置对话框
│   │   └── send_command_dialog.py     # 下发指令对话框
│   └── components/
│       ├── instance_list.py            # 实例列表组件
│       └── message_bar.py              # 消息提示条
├── utils/
│   ├── db_manager.py        # SQLite 数据库管理
│   └── utils.py             # 工具函数
└── API说明文档/
    ├── 创建命令.txt
    ├── 执行命令.txt
    └── 查询执行任务.txt
```

## 注意事项
- **API 密钥安全**：妥善保管 API 密钥，建议使用子账号并配置最小权限
- **费用管理**：关注实例费用，按需关机或销毁；地域与规格价格可能不同
- **TAT Agent**：
  - 腾讯云的新版公共镜像通常已预装 TAT Agent，可直接使用下发指令功能
  - 如果实例未安装 TAT Agent（会提示错误），需要手动安装：
    - Linux：执行安装脚本 `bash tat_agent_install.sh`
    - Windows：从腾讯云控制台下载并安装
  - 本项目不会自动安装 TAT Agent，依赖镜像本身是否包含
- **日志排查**：遇到问题可查看 `cvm_manager.log` 日志排查
- **异步操作**：批量操作采用异步处理，操作完成后会自动更新实例状态

## 许可证
MIT

