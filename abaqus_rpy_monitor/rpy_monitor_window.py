# -*- coding: utf-8 -*-
"""Independent, read-only Tk window for one Abaqus session's replay file.

Run with the Abaqus Python 3.10 interpreter and ``--config <json path>``.
No Abaqus GUI modules or third-party Python packages are needed here.
"""

import argparse
import ctypes
import json
import logging
import os
import subprocess
import time
import tkinter as tk
from tkinter import ttk

from rpy_tail import TailReader


POLL_MS = 500
MAX_DISPLAY_CHARS = 500000
ENCODINGS = {"自动": None, "UTF-8": "utf-8", "GB18030": "gb18030"}
LOG = logging.getLogger("abaqus_rpy_monitor")


class _ProcessWatch:
    """Hold a Windows process handle so PID reuse cannot change the session."""

    def __init__(self, pid):
        self.handle = None
        self.api = None
        self.available = False
        self._already_exited = False
        if os.name != "nt" or not pid:
            return
        try:
            from ctypes import wintypes
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            api.OpenProcess.restype = wintypes.HANDLE
            api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            api.WaitForSingleObject.restype = wintypes.DWORD
            api.CloseHandle.argtypes = [wintypes.HANDLE]
            api.CloseHandle.restype = wintypes.BOOL
            self.api = api
            self.handle = api.OpenProcess(0x00100000, False, int(pid))
            if self.handle:
                self.available = True
            else:
                error = ctypes.get_last_error()
                # ERROR_INVALID_PARAMETER: this positive PID no longer exists.
                # A kernel can exit between launching Python and opening its handle.
                if error == 87:
                    self._already_exited = True
                    self.available = True
                else:
                    LOG.warning("Kernel process state unavailable (Windows error %s)", error)
        except (OSError, ValueError):
            LOG.exception("Cannot watch the Abaqus kernel process")

    def exited(self):
        if self._already_exited:
            return True
        if not self.handle or not self.available:
            return False
        result = self.api.WaitForSingleObject(self.handle, 0)
        if result == 0xFFFFFFFF:
            self.available = False
            LOG.warning("Kernel process wait failed (Windows error %s)", ctypes.get_last_error())
        return result == 0

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


class Monitor:
    """Modeless monitor with a testable ``reader`` and read-only ``text``."""

    def __init__(self, root, config):
        self.root = root
        self.config = dict(config)
        self.replay_path = os.path.abspath(os.fspath(config["replay_path"]))
        self.kernel_pid = int(config.get("kernel_pid") or 0)
        self.focus_request = config.get("focus_request")
        self.reader = TailReader(self.replay_path, max_bytes=524288)
        expected_identity = config.get("file_identity", config.get("replay_identity"))
        if expected_identity is not None:
            self.reader.file_identity = tuple(expected_identity)
        self._watch = _ProcessWatch(self.kernel_pid)
        self._closed = False
        self._after_id = None
        self._kernel_exited = False
        self._exit_catchup_pending = False
        self._last_error = None
        self._last_update = None
        self._notice = ""
        self._notice_until = 0.0
        self._focus_stamp = self._get_focus_stamp()
        self.paused = tk.BooleanVar(master=root, value=False)
        self.follow = tk.BooleanVar(master=root, value=True)
        self.topmost = tk.BooleanVar(master=root, value=False)
        self.encoding = tk.StringVar(master=root, value="自动")
        self.status = tk.StringVar(master=root)
        self.path_var = tk.StringVar(master=root, value=self.replay_path)
        self._build_window()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll()

    def _build_window(self):
        root = self.root
        basename = os.path.basename(self.replay_path)
        root.title("RPY 实时监控 · PID %s · %s" % (self.kernel_pid or "?", basename))
        root.geometry("1120x700")
        root.minsize(780, 440)
        root.configure(background="#f1f4f7")
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Monitor.TFrame", background="#f1f4f7")
        style.configure("Monitor.TLabel", background="#f1f4f7", font=("Microsoft YaHei UI", 9))
        outer = ttk.Frame(root, padding=12, style="Monitor.TFrame")
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)

        title = ttk.Frame(outer, style="Monitor.TFrame")
        title.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        ttk.Label(title, text="当前会话 · 命令监控", style="Monitor.TLabel",
                  font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        ttk.Label(title, text="500 ms 刷新  /  只读", style="Monitor.TLabel").pack(side="right")

        source = ttk.Frame(outer, style="Monitor.TFrame")
        source.grid(row=1, column=0, sticky="ew")
        source.columnconfigure(1, weight=1)
        ttk.Label(source, text="RPY 文件", style="Monitor.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.path_entry = ttk.Entry(source, textvariable=self.path_var, state="readonly")
        self.path_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(source, text="复制路径", command=self.copy_path).grid(row=0, column=2, padx=(8, 0))

        label = self.config.get("session_label") or "Abaqus 会话"
        info = "%s  |  内核 PID %s" % (label, self.kernel_pid or "未知")
        startup = self.config.get("startup_dir")
        if startup:
            info += "  |  启动目录：" + str(startup)
        self.session_label = ttk.Label(outer, text=info, style="Monitor.TLabel", wraplength=1050)
        self.session_label.grid(row=2, column=0, sticky="w", pady=(7, 9))
        root.bind("<Configure>", self._resize_label, add="+")

        toolbar = ttk.Frame(outer, style="Monitor.TFrame")
        toolbar.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self.pause_button = ttk.Button(toolbar, text="暂停", width=7, command=self.toggle_pause)
        self.pause_button.pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="清空显示", command=self.clear_display).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="复制选中", command=self.copy_selected).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="复制全部", command=self.copy_all).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="记事本打开", command=self.open_editor).pack(side="left", padx=(0, 5))
        ttk.Button(toolbar, text="打开文件夹", command=self.open_folder).pack(side="left")

        body = ttk.Frame(outer)
        body.grid(row=4, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.text = tk.Text(body, wrap="none", state="disabled", undo=False,
                            font=("Consolas", 10), background="#15202e", foreground="#e2ebf3",
                            selectbackground="#365b83", selectforeground="#ffffff",
                            insertbackground="#e2ebf3", relief="flat", padx=12, pady=10,
                            exportselection=False, borderwidth=0)
        self.text.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.text.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.text.bind("<Control-a>", self._select_all)
        self.text.bind("<Control-A>", self._select_all)
        self.text.bind("<Control-c>", self._copy_event)
        self.text.bind("<Control-C>", self._copy_event)
        self.text.bind("<Button-3>", self._context_menu)
        self.context_menu = tk.Menu(root, tearoff=False)
        self.context_menu.add_command(label="复制选中", command=self.copy_selected)
        self.context_menu.add_command(label="复制全部", command=self.copy_all)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="全选", command=self._select_all)

        options = ttk.Frame(outer, style="Monitor.TFrame")
        options.grid(row=5, column=0, sticky="ew", pady=(9, 5))
        ttk.Checkbutton(options, text="跟随最新命令", variable=self.follow,
                        command=self._follow_changed).pack(side="left", padx=(0, 15))
        ttk.Checkbutton(options, text="窗口置顶", variable=self.topmost,
                        command=self._topmost_changed).pack(side="left", padx=(0, 18))
        ttk.Label(options, text="编码", style="Monitor.TLabel").pack(side="left", padx=(0, 5))
        encoding_box = ttk.Combobox(options, state="readonly", width=10,
                                    textvariable=self.encoding, values=list(ENCODINGS))
        encoding_box.pack(side="left")
        encoding_box.bind("<<ComboboxSelected>>", self.change_encoding)
        ttk.Label(options, text="最多保留 500,000 字符；清空仅影响显示。",
                  style="Monitor.TLabel").pack(side="right")
        ttk.Label(outer, textvariable=self.status, style="Monitor.TLabel",
                  anchor="w").grid(row=6, column=0, sticky="ew")

    def _resize_label(self, event):
        if event.widget is self.root:
            self.session_label.configure(wraplength=max(700, event.width - 30))

    def _select_all(self, event=None):
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.focus_set()
        return "break"

    def _copy_event(self, event=None):
        self.copy_selected()
        return "break"

    def _context_menu(self, event):
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _follow_changed(self):
        if self.follow.get():
            self.text.see("end")

    def _topmost_changed(self):
        self.root.attributes("-topmost", self.topmost.get())

    def _notify(self, text):
        self._notice = text
        self._notice_until = time.monotonic() + 4
        self._update_status()

    def _copy(self, value, notice):
        self.root.clipboard_clear()
        self.root.clipboard_append(value)
        self._notify(notice)

    def copy_path(self):
        self._copy(self.replay_path, "已复制完整文件路径。")

    def copy_selected(self):
        try:
            value = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            self._notify("请先选择需要复制的命令。")
            return
        self._copy(value, "已复制选中的命令。")

    def copy_all(self):
        self._copy(self.text.get("1.0", "end-1c"), "已复制当前显示的全部命令。")

    def clear_display(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
        self._notify("已清空显示；原始 RPY 文件未修改。")

    def toggle_pause(self):
        self.paused.set(not self.paused.get())
        self.pause_button.configure(text="继续" if self.paused.get() else "暂停")
        self._update_status()

    def change_encoding(self, event=None):
        old_reader = self.reader
        reader = TailReader(self.replay_path, max_bytes=524288,
                            encoding=ENCODINGS[self.encoding.get()])
        # A user changing the decoder must never authorize a different file.
        reader.file_identity = old_reader.file_identity
        self.reader = reader
        old_reader.close()
        self._read_once()
        self._update_status()

    def _safe_source_exists(self):
        try:
            info = os.stat(self.replay_path)
        except OSError as exc:
            self._notify("无法打开原始文件：%s" % exc)
            return False
        if self.reader.file_identity is not None and (info.st_dev, info.st_ino) != self.reader.file_identity:
            self._notify("文件已被替换。请在对应 Abaqus 窗口重新启动监控。")
            return False
        return True

    def open_editor(self):
        if not self._safe_source_exists():
            return
        try:
            # Never use os.startfile on .rpy: its association may execute it.
            subprocess.Popen(["notepad.exe", self.replay_path])
        except OSError as exc:
            self._notify("记事本启动失败：%s" % exc)

    def open_folder(self):
        try:
            subprocess.Popen(["explorer.exe", os.path.dirname(self.replay_path)])
        except OSError as exc:
            self._notify("文件夹打开失败：%s" % exc)

    def _get_focus_stamp(self):
        if not self.focus_request:
            return None
        try:
            stat = os.stat(self.focus_request)
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return None

    def _check_focus(self):
        stamp = self._get_focus_stamp()
        if stamp is not None and stamp != self._focus_stamp:
            self.root.deiconify()
            self.root.lift()
        self._focus_stamp = stamp

    def _read_once(self):
        try:
            content, reset = self.reader.read()
            self._last_error = None
        except (OSError, LookupError, UnicodeError) as exc:
            error = str(exc)
            if error != self._last_error:
                LOG.warning("Reading replay failed: %s", error)
            self._last_error = error
            return
        if not content and not reset:
            return
        old_view = self.text.yview()
        self.text.configure(state="normal")
        if reset:
            self.text.delete("1.0", "end")
        if content:
            self.text.insert("end", content)
        count = self.text.count("1.0", "end-1c", "chars")
        count = count[0] if count else 0
        if count > MAX_DISPLAY_CHARS:
            self.text.delete("1.0", "1.0 + %d chars" % (count - MAX_DISPLAY_CHARS))
        self.text.configure(state="disabled")
        if self.follow.get():
            self.text.see("end")
        else:
            self.text.yview_moveto(old_view[0])
        self._last_update = time.strftime("%H:%M:%S")

    def _update_status(self):
        if self.reader.replaced:
            state = "已停止读取：路径已指向其他文件。请在对应 Abaqus 窗口重新启动监控。"
        elif self._kernel_exited:
            if self._exit_catchup_pending and self.paused.get():
                state = "Abaqus 会话已结束；点击“继续”读取暂停期间的最后命令。"
            elif self._exit_catchup_pending:
                state = "Abaqus 会话已结束；正在重试读取最后命令。"
            else:
                state = "Abaqus 会话已结束；保留最后显示的命令。"
        elif self.reader.missing:
            state = "原始 RPY 文件暂不可用或已移动；不会猜测其他文件。可在对应 Abaqus 窗口重新启动监控。"
        elif self._last_error:
            state = "读取失败，将自动重试：" + self._last_error
        elif self.paused.get():
            state = "已暂停刷新；继续后显示最近新增的命令。"
        else:
            state = "正在监控此会话"
            if self.reader.encoding:
                state += "  |  " + self.reader.encoding.upper()
            if self._last_update:
                state += "  |  最近更新 " + self._last_update
        if not self._watch.available and not self._kernel_exited:
            state += "  |  会话进程状态未知"
        if self._notice and time.monotonic() < self._notice_until:
            state = self._notice + "   " + state
        self.status.set(state)

    def _poll(self):
        if self._closed:
            return
        self._after_id = None
        try:
            self._check_focus()
            if not self._kernel_exited:
                just_exited = self._watch.exited()
                if not self.paused.get():
                    self._read_once()
                    if just_exited:
                        self._exit_catchup_pending = bool(self._last_error or self.reader.missing)
                elif just_exited:
                    self._exit_catchup_pending = True
                self._kernel_exited = just_exited
            elif self._exit_catchup_pending and not self.paused.get():
                self._read_once()
                self._exit_catchup_pending = bool(self._last_error or self.reader.missing)
            self._update_status()
        except Exception:
            # Keep the monitor recoverable when a transient GUI/file error occurs.
            LOG.exception("Monitor update failed")
            self.status.set("刷新异常；稍后自动重试。")
        finally:
            if not self._closed:
                self._after_id = self.root.after(POLL_MS, self._poll)

    def poll(self):
        """Refresh immediately without creating a second scheduled timer."""
        if self._closed:
            return
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self._poll()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.reader.close()
        self._watch.close()
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Abaqus current-session RPY monitor")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    with open(args.config, "r", encoding="utf-8-sig") as stream:
        config = json.load(stream)
    log_path = config.get("window_log")
    logging.basicConfig(filename=log_path, encoding="utf-8" if log_path else None,
                        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = tk.Tk()
    try:
        Monitor(root, config)
        root.mainloop()
    except Exception:
        LOG.exception("Monitor window failed")
        raise


if __name__ == "__main__":
    main()
