"""Regression tests for the standalone replay-file reader."""

import codecs
import importlib.util
from pathlib import Path
import tempfile
import unittest


# Load directly: the deployed plugin package may import Abaqus GUI modules.
MODULE_PATH = Path(__file__).resolve().parents[1] / "abaqus_rpy_monitor" / "rpy_tail.py"
SPEC = importlib.util.spec_from_file_location("rpy_tail_under_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TailReader = MODULE.TailReader


class TailReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "abaqus.rpy"

    def reader(self, **kwargs):
        reader = TailReader(self.path, **kwargs)
        self.addCleanup(reader.close)
        return reader

    def append(self, data):
        with self.path.open("ab") as stream:
            stream.write(data)

    def test_initial_append_and_unchanged_do_not_duplicate(self):
        self.path.write_bytes(b"first\n")
        reader = self.reader(encoding="utf-8")
        self.assertEqual(reader.read(), ("first\n", True))
        identity = reader.file_identity
        self.assertEqual(reader.read(), ("", False))
        self.append(b"second\n")
        self.assertEqual(reader.read(), ("second\n", False))
        self.assertEqual(reader.file_identity, identity)
        self.assertEqual(reader.read(), ("", False))

    def test_truncation_resets_display_and_decoder(self):
        self.path.write_bytes(b"an earlier command\n\xe4")
        reader = self.reader(encoding="utf-8")
        self.assertEqual(reader.read(), ("an earlier command\n", True))
        self.path.write_bytes("新\n".encode("utf-8"))
        self.assertEqual(reader.read(), ("新\n", True))
        self.append(b"next\n")
        self.assertEqual(reader.read(), ("next\n", False))

    def test_truncation_and_regrowth_between_reads(self):
        self.path.write_bytes(b"old command\n")
        reader = self.reader(encoding="utf-8")
        reader.read()
        self.path.write_bytes(b"new command, now longer\n")
        self.assertEqual(reader.read(), ("new command, now longer\n", True))

    def test_same_size_rewrite_resets(self):
        self.path.write_bytes(b"old\n")
        reader = self.reader(encoding="utf-8")
        reader.read()
        self.path.write_bytes(b"new\n")
        self.assertEqual(reader.read(), ("new\n", True))

    def test_replacement_is_refused_and_original_can_resume(self):
        self.path.write_bytes(b"our session\n")
        reader = self.reader(encoding="utf-8")
        reader.read()
        identity = reader.file_identity
        old_path = self.path.with_suffix(".old")
        self.path.rename(old_path)
        self.path.write_bytes(b"ANOTHER SESSION\n")
        self.assertEqual(reader.read(), ("", False))
        self.assertTrue(reader.replaced)
        self.assertFalse(reader.missing)
        self.assertEqual(reader.file_identity, identity)
        self.path.unlink()
        old_path.rename(self.path)
        self.append(b"our next command\n")
        self.assertEqual(reader.read(), ("our next command\n", False))
        self.assertFalse(reader.replaced)

    def test_missing_before_creation_and_temporary_absence(self):
        reader = self.reader(encoding="utf-8")
        self.assertEqual(reader.read(), ("", False))
        self.assertTrue(reader.missing)
        self.assertIsNone(reader.file_identity)
        self.path.write_bytes(b"ours\n")
        self.assertEqual(reader.read(), ("ours\n", True))
        old_path = self.path.with_suffix(".old")
        self.path.rename(old_path)
        self.assertEqual(reader.read(), ("", False))
        self.assertTrue(reader.missing)
        old_path.rename(self.path)
        self.append(b"more\n")
        self.assertEqual(reader.read(), ("more\n", False))
        self.assertFalse(reader.missing)

    def test_multibyte_characters_split_across_updates(self):
        for encoding in ("utf-8", "gbk"):
            with self.subTest(encoding=encoding):
                self.path.write_bytes(b"start\n")
                reader = self.reader(encoding=encoding)
                reader.read()
                encoded = "命令".encode(encoding)
                output = []
                for byte in encoded:
                    self.append(bytes([byte]))
                    text, reset = reader.read()
                    self.assertFalse(reset)
                    output.append(text)
                self.assertEqual("".join(output), "命令")
                self.assertEqual(reader.read(), ("", False))

    def test_coding_declaration_selects_gbk(self):
        content = "# -*- coding: gbk -*-\n# 命令\n"
        self.path.write_bytes(content.encode("gbk"))
        reader = self.reader()
        self.assertEqual(reader.read(), (content, True))
        self.assertEqual(reader.encoding, "gbk")

    def test_utf8_bom_is_not_displayed(self):
        self.path.write_bytes(codecs.BOM_UTF8 + "命令\n".encode("utf-8"))
        self.assertEqual(self.reader().read(), ("命令\n", True))

    def test_initial_preview_omits_leading_partial_line(self):
        self.path.write_bytes(b"line 1\nline 2\nline 3\n")
        reader = self.reader(max_bytes=12, encoding="utf-8")
        self.assertEqual(reader.read(), ("line 3\n", True))
        self.assertEqual(reader.read(), ("", False))
        self.append(b"line 4\n")
        self.assertEqual(reader.read(), ("line 4\n", False))

    def test_large_append_is_bounded_and_resets_display(self):
        self.path.write_bytes(b"start\n")
        reader = self.reader(max_bytes=10, encoding="utf-8")
        reader.read()
        self.append(b"discarded\nlast\n")
        self.assertEqual(reader.read(), ("last\n", True))

    def test_preview_keeps_first_line_when_start_is_line_boundary(self):
        self.path.write_bytes(b"line 1\nline 2\nline 3\n")
        reader = self.reader(max_bytes=14, encoding="utf-8")
        self.assertEqual(reader.read(), ("line 2\nline 3\n", True))

    def test_no_newline_preview_is_still_bounded(self):
        self.path.write_bytes(b"a" * 1000)
        self.assertEqual(self.reader(max_bytes=32).read(), ("a" * 32, True))

    def test_empty_file_then_append(self):
        self.path.write_bytes(b"")
        reader = self.reader(encoding="utf-8")
        self.assertEqual(reader.read(), ("", True))
        self.append(b"command\n")
        self.assertEqual(reader.read(), ("command\n", False))

    def test_close_and_context_manager(self):
        self.path.write_bytes(b"command\n")
        with TailReader(self.path) as reader:
            reader.read()
        self.assertTrue(reader.closed)
        reader.close()
        with self.assertRaises(ValueError):
            reader.read()
        # No open handle prevents renaming or deleting on Windows.
        self.path.rename(self.path.with_suffix(".closed"))

    def test_limit_validation(self):
        for limit in (0, -1):
            with self.assertRaises(ValueError):
                self.reader(max_bytes=limit)
        for limit in (True, 1.5):
            with self.assertRaises(TypeError):
                self.reader(max_bytes=limit)


if __name__ == "__main__":
    unittest.main()
