# -*- coding: utf-8 -*-
"""Integration tests using the real bundled Tcl/Tk, with withdrawn test windows."""
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abaqus_rpy_monitor'))
from rpy_monitor_window import Monitor


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'abaqus.rpy.41'
        self.path.write_bytes(b'# coding: utf-8\nthis_session\n')
        stat = self.path.stat()
        self.config = dict(replay_path=str(self.path), kernel_pid=os.getpid(),
                           startup_dir=self.temp.name, session_label='Test only',
                           file_identity=[stat.st_dev, stat.st_ino])

    def monitor(self):
        root = tk.Tk()
        root.withdraw()
        monitor = Monitor(root, self.config)
        self.addCleanup(monitor.close)
        return monitor

    def value(self, monitor):
        return monitor.text.get('1.0', 'end-1c')

    def append(self, text):
        with self.path.open('ab') as stream:
            stream.write(text.encode('utf-8'))

    def test_updates_only_its_own_session_despite_newer_files(self):
        monitor = self.monitor()
        (self.path.parent / 'abaqus.rpy').write_text('OTHER SESSION', encoding='utf-8')
        self.append('新命令\n')
        monitor.poll()
        self.assertIn('新命令', self.value(monitor))
        self.assertNotIn('OTHER SESSION', self.value(monitor))
        self.assertEqual(str(monitor.text.cget('state')), 'disabled')
        before = self.value(monitor)
        monitor.poll()
        self.assertEqual(self.value(monitor), before)

    def test_pause_resume_and_clear_do_not_modify_source(self):
        monitor = self.monitor()
        monitor.toggle_pause()
        self.append('during_pause\n')
        monitor.poll()
        self.assertNotIn('during_pause', self.value(monitor))
        monitor.toggle_pause()
        monitor.poll()
        self.assertIn('during_pause', self.value(monitor))
        before = self.path.read_bytes()
        monitor.clear_display()
        monitor.poll()
        self.assertEqual(self.value(monitor), '')
        self.assertEqual(self.path.read_bytes(), before)
        self.append('after_clear\n')
        monitor.poll()
        self.assertEqual(self.value(monitor), 'after_clear\n')

    def test_launch_race_refuses_replacement_before_first_read(self):
        self.path.rename(self.path.with_name('original.rpy'))
        self.path.write_bytes(b'OTHER SESSION')
        monitor = self.monitor()
        self.assertTrue(monitor.reader.replaced)
        self.assertEqual(self.value(monitor), '')

    def test_encoding_change_cannot_rebind_replaced_file(self):
        monitor = self.monitor()
        self.path.rename(self.path.with_name('original.rpy'))
        self.path.write_bytes(b'OTHER SESSION')
        monitor.poll()
        monitor.encoding.set('UTF-8')
        monitor.change_encoding()
        self.assertTrue(monitor.reader.replaced)
        self.assertNotIn('OTHER SESSION', self.value(monitor))

    def test_close_cancels_timer_and_reader(self):
        monitor = self.monitor()
        self.assertIsNotNone(monitor._after_id)
        monitor.close()
        self.assertTrue(monitor.reader.closed)
        self.assertIsNone(monitor._after_id)
        monitor.poll()


if __name__ == '__main__':
    unittest.main()
