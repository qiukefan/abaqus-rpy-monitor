"""Exercise replay binding and launcher behavior without importing Abaqus."""

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


MODULE_PATH = (Path(__file__).resolve().parents[1] / "abaqus_rpy_monitor"
               / "rpy_monitor_kernel.py")


def load_kernel():
    spec = importlib.util.spec_from_file_location("rpy_kernel_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SessionInfoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.startup = Path(self.temp.name) / "startup"
        self.startup.mkdir()
        self.other = Path(self.temp.name) / "different_work_directory"
        self.other.mkdir()
        self.own = self.startup / "abaqus.rpy.41"
        self.own.write_bytes(b"our commands\n")
        self.abaqus = types.ModuleType("abaqus")
        self.abaqus.getReplayFileName = lambda: "abaqus.rpy.41"
        self.abaqus.getStartupDir = lambda: str(self.startup)
        self.abaqus.session = types.SimpleNamespace(
            currentViewportName="Viewport: 1",
            viewports={"Viewport: 1": types.SimpleNamespace(
                displayedObject=types.SimpleNamespace(path="C:/models/result.odb"))},
        )
        self.abaqus.mdb = types.SimpleNamespace(pathName="C:/models/model.cae")
        self.modules = mock.patch.dict(sys.modules, {"abaqus": self.abaqus})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.kernel = load_kernel()

    def test_relative_replay_name_uses_startup_not_current_work_directory(self):
        wrong = self.other / self.own.name
        wrong.write_bytes(b"other session\n")
        original_cwd = os.getcwd()
        try:
            os.chdir(self.other)
            info = self.kernel.session_info()
        finally:
            os.chdir(original_cwd)
        self.assertEqual(info["replay_path"], str(self.own))
        self.assertEqual(info["startup_dir"], str(self.startup))
        self.assertEqual(info["kernel_pid"], os.getpid())
        stat = self.own.stat()
        self.assertEqual(info["file_identity"], [stat.st_dev, stat.st_ino])
        self.assertEqual(info["session_label"], "C:/models/result.odb")

    def test_newer_similarly_named_files_never_override_reported_path(self):
        newest = self.startup / "abaqus.rpy.99"
        newest.write_bytes(b"another session\n")
        os.utime(self.own, (1, 1))
        self.assertGreater(newest.stat().st_mtime, self.own.stat().st_mtime)
        self.assertEqual(self.kernel.session_info()["replay_path"], str(self.own))

    def test_missing_reported_file_does_not_guess_a_fallback(self):
        self.own.unlink()
        (self.startup / "abaqus.rpy").write_bytes(b"not ours\n")
        with self.assertRaisesRegex(RuntimeError, "No other replay file was selected"):
            self.kernel.session_info()

    def test_absolute_reported_path_is_preserved(self):
        absolute = self.other / "session.rpy"
        absolute.write_bytes(b"ours\n")
        self.abaqus.getReplayFileName = lambda: str(absolute)
        self.assertEqual(self.kernel.session_info()["replay_path"], str(absolute))

    def test_empty_replay_name_fails_without_searching(self):
        self.abaqus.getReplayFileName = lambda: ""
        with self.assertRaisesRegex(RuntimeError, "no active replay file"):
            self.kernel.session_info()

    def test_missing_api_fails_with_version_guidance(self):
        del self.abaqus.getReplayFileName
        with self.assertRaisesRegex(RuntimeError, "getReplayFileName"):
            self.kernel.session_info()

    def test_label_falls_back_to_cae_when_viewport_is_unavailable(self):
        del self.abaqus.session
        self.assertEqual(self.kernel.session_info()["session_label"], "C:/models/model.cae")


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.kernel = load_kernel()
        self.info = dict(
            replay_path=str(self.folder / "abaqus.rpy.41"),
            kernel_pid=os.getpid(), session_label="含中文的结果.odb",
            startup_dir=str(self.folder),
            # Windows file indices can exceed IEEE-754's exact integer range.
            file_identity=[817273, 19590658379061771],
        )
        self.process = mock.Mock()
        self.process.poll.return_value = None
        self.bind = mock.patch.object(self.kernel, "session_info", side_effect=lambda: dict(self.info))
        self.runtime = mock.patch.object(self.kernel, "_python_executable", return_value="SMAPython.exe")
        self.popen = mock.patch.object(self.kernel.subprocess, "Popen", return_value=self.process)
        self.tempdir = mock.patch.object(self.kernel.tempfile, "mkdtemp", return_value=str(self.folder))
        self.printing = mock.patch("builtins.print")
        for patcher in (self.bind, self.runtime, self.popen, self.tempdir, self.printing):
            result = patcher.start()
            self.addCleanup(patcher.stop)
            if patcher is self.popen:
                self.popen_mock = result
            elif patcher is self.runtime:
                self.runtime_mock = result

    def test_launch_serializes_exact_identity_and_absolute_script_path(self):
        self.assertEqual(self.kernel.launch(), self.info["replay_path"])
        config_path = self.folder / "config.json"
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["file_identity"], self.info["file_identity"])
        self.assertIsInstance(saved["file_identity"][1], int)
        self.assertEqual(saved["session_label"], self.info["session_label"])
        self.assertEqual(saved["replay_path"], self.info["replay_path"])
        args, kwargs = self.popen_mock.call_args
        self.assertEqual(args[0], ["SMAPython.exe", str(MODULE_PATH.with_name("rpy_monitor_window.py")),
                                   "--config", str(config_path)])
        self.assertEqual(kwargs["cwd"], str(self.folder))
        self.assertEqual(kwargs["stdin"], self.kernel.subprocess.DEVNULL)
        self.assertFalse(kwargs.get("shell", False))

    def test_second_launch_focuses_same_live_monitor_without_spawning(self):
        self.kernel.launch()
        with mock.patch.object(self.kernel.time, "time_ns", return_value=123456789):
            self.assertEqual(self.kernel.launch(), self.info["replay_path"])
        self.assertEqual(self.popen_mock.call_count, 1)
        self.assertEqual(self.runtime_mock.call_count, 1)
        self.assertEqual((self.folder / "focus.txt").read_text(), "123456789")

    def test_dead_monitor_is_launched_again(self):
        self.kernel.launch()
        self.process.poll.return_value = 0
        self.kernel.launch()
        self.assertEqual(self.popen_mock.call_count, 2)

    def test_changed_identity_does_not_focus_old_monitor(self):
        self.kernel.launch()
        self.info["file_identity"] = [817273, 19590658379061772]
        self.kernel.launch()
        self.assertEqual(self.popen_mock.call_count, 2)
        self.assertFalse((self.folder / "focus.txt").exists())
        saved = json.loads((self.folder / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["file_identity"], self.info["file_identity"])


if __name__ == "__main__":
    unittest.main()
