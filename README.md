# Abaqus RPY Monitor

为 **当前 Abaqus/CAE 或 Abaqus/Viewer 会话** 打开一个独立的 RPY 命令监控浮窗，每 0.5 秒读取一次已写入回放文件的命令。

同时打开多个 Abaqus 窗口时，工作目录中可能出现很多时间接近的 `abaqus.rpy`、`abaqus.rpy.1` 等文件。本插件直接向启动它的 Abaqus 会话查询回放文件路径，并显示完整路径和内核 PID，帮助你确认当前操作记录在哪个文件中。

**已验证环境：Windows + Abaqus 2023（CAE / Viewer，Python 3.10）。** 使用 Abaqus 自带的 Python 和 Tk，不需要 `pip`、另外安装 Python 或连接网络服务。其他版本尚未验证；当前版本不支持 Linux。

## 下载

- 直接下载 [v1.0.0 插件安装包](dist/Abaqus_RPY_Monitor_v1.0.0.zip)，然后完整解压。
- 或在 GitHub 仓库首页选择 **Code → Download ZIP**，然后完整解压。

解压后，请保持 `install_rpy_monitor.py`、`open_rpy_monitor.py` 和 `abaqus_rpy_monitor` 文件夹处于同一目录。不要只下载一个入口脚本，也不要直接在压缩包中运行脚本。

## 安装到 Abaqus 的 Plug-ins 菜单

### 方法一：运行安装脚本（推荐）

1. 打开 Abaqus/CAE 或 Abaqus/Viewer。
2. 选择 **File → Run Script**。
3. 选择解压目录中的 **`install_rpy_monitor.py`** 并运行。
4. 消息区出现 `Installed RPY Monitor:` 后，插件已复制到当前用户的插件目录：

   ```text
   C:\Users\<用户名>\abaqus_plugins\rpy_monitor\
   ```

5. 保存当前工作，并重新启动需要使用菜单入口的 Abaqus 窗口。
6. 在新启动的窗口中选择：

   **Plug-ins → RPY Monitor → Open Current Session**

安装脚本自动创建目标目录；通常不需要管理员权限，也不需要修改 Abaqus 的程序安装目录。脚本使用 `os.path.expanduser('~')` 获取当前用户主目录；上面是 Windows 的常见路径，实际安装位置以消息区输出为准。

安装脚本也可以通过普通 Python 3 运行，但打开监控窗口的入口必须从目标 Abaqus 会话中执行。

### 方法二：手动复制到插件目录

如果希望自己管理插件文件，可以按以下步骤操作：

1. 打开当前用户的 `abaqus_plugins` 文件夹；没有则创建。在 Windows 资源管理器地址栏输入 `%USERPROFILE%\abaqus_plugins` 可快速定位常见安装位置。
2. 将解压目录中的 **`abaqus_rpy_monitor` 文件夹**复制进去，并将复制后的文件夹重命名为 **`rpy_monitor`**。
3. 检查最终目录结构。下面五个 `.py` 文件必须直接位于 `rpy_monitor` 中：

   ```text
   C:\Users\<用户名>\abaqus_plugins\
   └── rpy_monitor\
       ├── __init__.py
       ├── rpy_monitor_plugin.py
       ├── rpy_monitor_kernel.py
       ├── rpy_monitor_window.py
       └── rpy_tail.py
   ```

4. 重新启动 Abaqus，然后选择 **Plug-ins → RPY Monitor → Open Current Session**。

`rpy_monitor_plugin.py` 是 Abaqus 自动加载的菜单注册文件。不要把它单独复制过去，也不要用 **File → Run Script** 执行它或 `rpy_monitor_window.py`。`install_rpy_monitor.py` 和 `open_rpy_monitor.py` 保留在解压目录即可，不需要放入插件目录。

## 已打开的 Abaqus：无需重启，立即使用

如果已经打开模型或 ODB，可以先直接启动监控，无需等待安装菜单生效：

1. 切换到**需要监控的那个 Abaqus 窗口**。
2. 选择 **File → Run Script**。
3. 运行解压目录中的 **`open_rpy_monitor.py`**。
4. 在监控浮窗顶部确认 **RPY 文件**的完整路径和**内核 PID**。
5. 回到该 Abaqus 窗口继续操作，浮窗会更新已写入 `.rpy` 的命令。

这条入口依赖旁边的 `abaqus_rpy_monitor` 文件夹，请保持解压目录完整。

## 多窗口时如何使用

在每个需要监控的 Abaqus 窗口中，分别打开一次插件。每个浮窗持续绑定启动它的那个会话。

例如，先在 CAE 窗口 A 打开监控，再在 Viewer 窗口 B 打开监控，就会得到两个独立浮窗。通过各自顶部的文件路径和内核 PID 区分即可，不必根据 `.rpy` 文件的修改时间或数字后缀猜测。

- **切换 Windows 前台窗口不会让已有浮窗改绑到另一个会话。** 要监控另一个窗口，请在那个窗口中打开插件。
- 在同一个 Abaqus 会话中打开多个 ODB，仍然共用该会话的回放日志；插件不为每个 ODB 单独生成日志。
- 在同一会话中重复使用同一个入口打开插件，通常会唤回已有浮窗。
- 顶部的 ODB / 模型名称是打开浮窗时的参考信息，不随切换视口实时更新；会话绑定依据是内核 PID 和回放文件身份。

## 窗口功能

| 控件 | 用法 |
| --- | --- |
| **暂停 / 继续** | 暂停或恢复读取；暂停期间 Abaqus 仍照常记录，继续后读取新增内容。积累内容很大时只显示最近部分。 |
| **跟随最新命令** | 自动滚动到末尾；取消勾选后可向上查看历史内容。 |
| **窗口置顶** | 让监控浮窗保持在其他窗口之上。 |
| **复制选中** | 复制选中的命令，也可使用 `Ctrl+C`。 |
| **复制全部** | 复制浮窗中当前保留的全部文本。 |
| **复制路径** | 复制当前绑定的 `.rpy` 文件完整路径。 |
| **清空显示** | 清空浮窗中的文本，后续新增命令继续显示；不会清空或修改原始 `.rpy`。 |
| **记事本打开** | 用记事本打开当前绑定的原始文件，查看完整历史。 |
| **打开文件夹** | 打开回放文件所在目录。 |
| **编码** | 可选“自动”“UTF-8”“GB18030”；自动模式优先识别 UTF-8 BOM 或文件头编码声明。 |

文本区域还支持 `Ctrl+A` 全选、右键复制、水平和垂直滚动。

## 显示范围与工作方式

- 刷新间隔为 **500 ms**。显示的是 Abaqus **已经写入磁盘**的回放内容；如果 Abaqus 尚未刷新文件，浮窗也需要等待。
- 这是回放日志查看器。Abaqus 不记录到 `.rpy` 的操作不会出现在浮窗中；**File → Run Script 内部的每条 Python 语句不保证被逐条记录**。
- 首次读取，以及一次积累过多新增内容时，会读取文件末尾最多 **512 KiB** 的预览。浮窗最多保留 **500,000 个字符**，超过后移除较旧的显示内容。两者分别是读取字节数和显示字符数限制。
- **复制全部**只复制当前显示内容。查看完整历史请使用**记事本打开**。
- 文件被移动、删除或被其他同名文件替换时，浮窗会显示状态提示，不会按时间搜索或自动切换到其他 `.rpy`。回到原 Abaqus 窗口重新打开插件，可重新查询当前会话的文件。
- 会话结束后，浮窗会保留最后显示的命令；如果关闭 Abaqus 时正在暂停，可点击**继续**补读最后内容。

内核通过 `abaqus.getReplayFileName()` 获取当前会话的回放文件名，通过 `abaqus.getStartupDir()` 解析相对路径，并记录文件身份。监控界面在独立进程中只读文件，不会定时向 Abaqus 内核发送查询命令，也不会修改模型、ODB、`journalOptions` 或原始回放文件。

## 升级与卸载

**升级：** 关闭监控浮窗，完整解压新版本，再运行新版本的 `install_rpy_monitor.py`。安装脚本会把原来的 `rpy_monitor` 文件夹备份到当前用户主目录下的 `abaqus_plugin_backups`，然后更新插件文件。重新启动 Abaqus 后使用新版菜单入口。

如果采用手动安装，请先将旧文件夹移到 `abaqus_plugins` 以外的位置，再复制新版本。不要把备份保留在 `abaqus_plugins` 内，以免 Abaqus 重复注册菜单。

**卸载：** 关闭监控浮窗，删除当前用户插件目录中的 `rpy_monitor` 文件夹，然后重新启动 Abaqus。原始 `.rpy` 文件和其他插件不受影响；需要时可另行删除解压目录与旧版本备份。

## 常见问题

**安装后没有看到 RPY Monitor 菜单**

先重新启动 Abaqus。检查插件是否安装在当前运行 Abaqus 的用户主目录下，以及 `rpy_monitor_plugin.py` 是否位于上面展示的正确位置。已打开的会话可以先通过 **File → Run Script → `open_rpy_monitor.py`** 使用。

**运行脚本后没有出现浮窗**

检查 Abaqus 消息区是否输出错误或 `Diagnostic log:`。诊断日志位于系统临时目录中的 `abaqus_rpy_monitor_<PID>_*` 子目录，具体路径以消息区为准。确认当前环境是 Windows Abaqus 2024，并保留完整的解压目录结构。

**提示缺少 `getReplayFileName()` 或找不到 `SMAPython.exe`**

当前版本需要相应的 Abaqus 接口和自带 Python 运行环境。其他版本尚未验证，不能仅将脚本复制过去就保证兼容。请在 Abaqus 会话中启动监控，不要用系统 Python 或双击 `open_rpy_monitor.py` 来启动。

**中文乱码**

尝试把“编码”从“自动”切换为“UTF-8”或“GB18030”。切换编码会重新读取文件末尾的预览。

**有操作，但内容没有马上更新**

确认没有暂停，并检查顶部路径和 PID 是否对应目标会话。等待 Abaqus 将命令写入文件；某些操作或脚本内部语句不会被 Abaqus 记录到 `.rpy`。可以用**记事本打开**检查原文件内容。

**提示文件不可用或已经被替换**

在对应的 Abaqus 窗口中重新打开插件。若该会话报告的回放文件本身已不存在，插件会明确报错，不会选择目录中其他相似文件作为替代。

## 项目结构与开发测试

```text
.
├── abaqus_rpy_monitor/
│   ├── __init__.py
│   ├── rpy_monitor_plugin.py   # Abaqus 菜单注册
│   ├── rpy_monitor_kernel.py   # 查询当前会话并启动浮窗
│   ├── rpy_monitor_window.py   # 独立 Tk 监控界面
│   └── rpy_tail.py             # 增量读取与文件身份检查
├── tests/                     # 内核、读取器和窗口测试
├── install_rpy_monitor.py      # 安装 / 升级入口
├── open_rpy_monitor.py         # 无需安装的会话内启动入口
├── README.md
├── README_使用说明.txt
└── dist/
    └── Abaqus_RPY_Monitor_v1.0.0.zip
```

在已配置 Abaqus 命令的终端中，进入项目根目录运行：

```powershell
abaqus python -m unittest discover -s tests -v
```

当前包含 **32 项测试**，覆盖会话路径解析、多会话隔离、文件替换与截断、增量读取、中文字符解码、暂停恢复及只读窗口行为。窗口测试需要可用的 Tk 图形环境；测试结果不能替代在具体 Abaqus 版本中的实际兼容性验证。
