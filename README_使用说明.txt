Abaqus 当前会话 RPY 实时监控插件 v1.0.0

用途
在你要监控的 CAE/Viewer 窗口内打开插件，显示这个会话实际使用的 .rpy 文件。
多个 Abaqus 窗口各自打开一个监控浮窗，按会话独立绑定，不按文件日期或编号猜测。
切换到另一个 Abaqus 窗口时，已有监控窗口仍跟随原会话；在另一个窗口再次打开即可。
一个 CAE 窗口中打开多个 ODB 时，它们属于同一个会话，共用该会话的回放日志。

当前已针对 Windows + Abaqus 2024 / Python 3.10 开发。
不需要 pip、额外 Python 或网络服务；使用 Abaqus 自带的 Python 和 Tk。

立即使用（已经打开的 CAE/Viewer，无需重启）
1. 保持整个插件包的目录结构，把压缩包完整解压。
2. 切换到你要监控的 Abaqus 窗口。
3. 选择 File > Run Script，运行同一目录中的 open_rpy_monitor.py。
4. 浮窗中检查“内核 PID”和“RPY 文件”完整路径，然后继续操作 Abaqus。
   不要用 Run Script 执行 rpy_monitor_plugin.py 或 rpy_monitor_window.py。

安装到 Plug-ins 菜单
1. 在 Abaqus 的 File > Run Script 中运行 install_rpy_monitor.py。
   也可以在正常 Python 中运行安装脚本。
2. 插件写入当前用户的 ~/abaqus_plugins/rpy_monitor。
3. 新启动的 CAE/Viewer 可通过以下菜单打开：
   Plug-ins > RPY Monitor > Open Current Session
4. 已经打开的 Abaqus 窗口仍可通过 open_rpy_monitor.py 立即使用，不必关闭模型。
升级时旧版会备份至 ~/abaqus_plugin_backups，避免重复注册菜单。

功能
- 约每 0.5 秒读取已经写入磁盘的新增命令，监控窗口不会阻塞 CAE。
- 可选自动滚动和窗口置顶。
- 暂停/继续显示；暂停期间 Abaqus 仍照常记录，继续后补读新增内容。
- 复制选中文本或当前显示的全部文本。
- 清空显示只清理浮窗内容，不会清空、修改或删除 .rpy 文件。
- 在记事本中打开原文件；定位所在文件夹。
- 编码可选择自动、UTF-8 或 GB18030。
- 重复点击同一会话的入口，会唤回现有浮窗。

边界与说明
- “实时”是查看 Abaqus 已写入 .rpy 的内容。Abaqus 尚未刷新到磁盘的命令，
  以及本来就不记录到 .rpy 的操作，不会提前显示。
- 这不是完整 Python 执行跟踪器；File > Run Script 中的内部语句是否写入回放，
  取决于 Abaqus 本身的记录机制。
- 顶部的 ODB/模型名称是打开浮窗时的参考信息；真正绑定依据是会话 PID 和文件身份。
- 大日志只显示最近约 512 KiB；复制全部只复制当前显示内容。
  查看完整历史请使用“打开文件”。显示内容过长时会移除较旧部分。
- 文件被删除、移走或被同名文件替换时，会提示异常并拒绝串到其他会话。
  此时回到原 Abaqus 窗口重新打开插件，让它重新查询当前回放文件。
- Windows Abaqus 2024 已实测；其他版本未验证。
  如果版本不提供所需接口，会明确报错，不会随意选一个相似文件。
- 不会改变 journalOptions、模型、ODB 数据或原文件内容。

实现依据
内核使用 abaqus.getReplayFileName() 获取本会话文件名，配合
abaqus.getStartupDir() 解析路径，并记录文件身份防止同名替换。
以上两个接口已在本机 Abaqus 2024 实测，包含更改工作目录后的路径验证。
菜单使用 sendCommand(command, False, False) 避免监控请求进入 replay/journal。
外部浮窗只读文件，不定时向 Abaqus 内核发送查询命令。

官方手册参考
回放文件：
https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-c-dbsfilesreplay.htm
GUI 插件菜单：
https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-c-plgregistergui.htm
发送内核命令：
https://docs.software.vt.edu/abaqusv2025/English/SIMACAECUSRefMap/simacus-c-comcommandsexecute.htm

排查
若浮窗没有出现，查看 Abaqus 消息区输出的 Diagnostic log 路径。
日志位于系统临时目录中的 abaqus_rpy_monitor_<PID>_* 子目录。
如果中文显示乱码，先切换编码；默认优先使用 .rpy 文件头的编码声明。
卸载时关闭监控窗口，删除 ~/abaqus_plugins/rpy_monitor 文件夹即可。
重新启动 Abaqus 后菜单消失；不会影响其他插件或原始 .rpy 文件。

开发测试
在插件包目录执行：
abaqus python -m unittest discover -s tests -v
测试覆盖多会话隔离、文件身份、增量读取、中文解码和窗口行为。
