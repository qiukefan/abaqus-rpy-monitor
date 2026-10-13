"""Bounded, incremental replay-file reader with no Abaqus dependencies.

The reader binds to a file identity, not just a filename.  An unrelated CAE
session may reuse ``abaqus.rpy``; silently following that replacement would
show the wrong session's commands.  Create a new reader only after resolving
the new path against the intended session again.
"""

import codecs
import locale
import os
import re


_CODING_RE = re.compile(br"coding[=:]\s*([-\w.]+)")
_CHECKPOINT_BYTES = 128


class TailReader:
    """Read appended text while remembering an offset and decoder state.

    ``read()`` returns ``(text, reset)``.  When ``reset`` is true, replace the
    displayed text; otherwise append it.  The first successful read, a file
    truncation/rewrite, or a burst exceeding ``max_bytes`` returns a bounded
    preview of the newest bytes with ``reset=True``.  A leading partial line
    is omitted when that preview contains a newline.  An incomplete final
    multibyte character is held until the next read, never prematurely
    replaced.  Invalid byte sequences use the Unicode replacement character.

    Encoding is explicit when supplied.  Otherwise a UTF-8 BOM or a Python
    coding declaration in the first two lines takes precedence over the
    platform's preferred encoding.  The selected encoding is available as
    ``encoding`` after the first successful read.

    ``file_identity`` is the bound ``(st_dev, st_ino)`` tuple, initially None.
    A different identity at the same path sets ``replaced=True`` and returns
    no text: this reader NEVER binds to that replacement.  Temporary absence
    sets ``missing=True`` and also returns no text, preserving the offset so
    the original file can resume if restored.  Other I/O errors propagate.

    No file handle stays open between calls.  ``close()`` is idempotent and
    prevents further reads.  Call from one thread only.  Identity protection
    assumes the filesystem provides stable device/inode identifiers.
    """

    def __init__(self, path, max_bytes=524288, encoding=None):
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be a positive integer")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if encoding is not None:
            codecs.lookup(encoding)
        self.path = os.path.abspath(os.fspath(path))
        self.max_bytes = max_bytes
        self.encoding = encoding
        self.file_identity = None
        self.replaced = False
        self.missing = False
        self.closed = False
        self._requested_encoding = encoding
        self._offset = 0
        self._checkpoint = b""
        self._decoder = None
        self._started = False

    def _make_decoder(self, stream):
        encoding = self._requested_encoding
        if encoding is None:
            stream.seek(0)
            header = stream.read(512)
            if header.startswith(codecs.BOM_UTF8):
                encoding = "utf-8-sig"
            else:
                for line in header.splitlines()[:2]:
                    match = _CODING_RE.search(line)
                    if match:
                        encoding = match.group(1).decode("ascii")
                        break
            if encoding is None:
                encoding = locale.getpreferredencoding(False)
        self.encoding = codecs.lookup(encoding).name
        self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")

    def read(self):
        """Return newly decoded text and whether the display must be reset."""
        if self.closed:
            raise ValueError("read from closed TailReader")
        try:
            stream = open(self.path, "rb")
        except FileNotFoundError:
            self.missing = True
            self.replaced = False
            return "", False

        with stream:
            stat = os.fstat(stream.fileno())
            identity = (stat.st_dev, stat.st_ino)
            self.missing = False
            if self.file_identity is not None and identity != self.file_identity:
                self.replaced = True
                return "", False
            self.replaced = False
            self.file_identity = identity

            size = stat.st_size
            reset = not self._started or size < self._offset
            if not reset and self._checkpoint:
                # Also catch truncate-and-regrow between timer ticks, even
                # when the new size equals or exceeds the previous offset.
                stream.seek(self._offset - len(self._checkpoint))
                reset = stream.read(len(self._checkpoint)) != self._checkpoint

            if not reset and size - self._offset > self.max_bytes:
                reset = True
            if not reset and size == self._offset:
                return "", False

            start = max(0, size - self.max_bytes) if reset else self._offset
            if reset:
                self._make_decoder(stream)
            partial_first_line = False
            if reset and start:
                stream.seek(start - 1)
                partial_first_line = stream.read(1) != b"\n"
            stream.seek(start)
            # Read only up to the size observed above.  Bytes appended while
            # this call runs belong to the next update.
            data = stream.read(max(0, size - start))
            self._offset = start + len(data)
            if partial_first_line:
                newline = data.find(b"\n")
                if newline >= 0:
                    data = data[newline + 1:]

            checkpoint_start = max(0, self._offset - _CHECKPOINT_BYTES)
            stream.seek(checkpoint_start)
            self._checkpoint = stream.read(self._offset - checkpoint_start)
            self._started = True
            return self._decoder.decode(data, final=False), reset

    def close(self):
        """Discard decoder state and permanently close this reader."""
        self._decoder = None
        self._checkpoint = b""
        self.closed = True

    def __enter__(self):
        if self.closed:
            raise ValueError("enter closed TailReader")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
