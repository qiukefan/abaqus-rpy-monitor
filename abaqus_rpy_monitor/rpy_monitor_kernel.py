# -*- coding: utf-8 -*-
"""Resolve the current Abaqus session's replay file and launch its monitor.

No directory guessing, timestamp matching, or changes to replay settings.
The optional UI runs in a separate process to keep CAE responsive.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

_viewer = None
_config = None


def session_info():
    import abaqus

    if not hasattr(abaqus, 'getReplayFileName'):
        raise RuntimeError('This Abaqus version does not expose getReplayFileName(). '
                           'RPY Monitor has been verified with Abaqus 2024.')
    name = abaqus.getReplayFileName()
    if not name:
        raise RuntimeError('This Abaqus session has no active replay file.')
    # The replay name remains relative to startup even after File > Set Work Directory.
    startup = abaqus.getStartupDir()
    path = os.path.normpath(name if os.path.isabs(name) else os.path.join(startup, name))
    if not os.path.isfile(path):
        raise RuntimeError('The current session reports a replay file that cannot be read: '
                           + path + '\nNo other replay file was selected.')
    with open(path, 'rb') as stream:
        stat = os.fstat(stream.fileno())
    label = ''
    try:
        viewport = abaqus.session.viewports[abaqus.session.currentViewportName]
        displayed = viewport.displayedObject
        label = getattr(displayed, 'path', '') or getattr(displayed, 'name', '')
    except Exception:
        pass
    if not label:
        try:
            label = abaqus.mdb.pathName
        except Exception:
            pass
    return dict(replay_path=path, kernel_pid=os.getpid(), session_label=label,
                startup_dir=startup, file_identity=[stat.st_dev, stat.st_ino])


def _python_executable():
    # In CAE sys.executable is ABQcaeK.exe/ABQvwrK.exe, not a Python interpreter.
    runtime = os.path.join(os.path.dirname(sys.executable), 'SMAPython.exe')
    if os.name == 'nt' and os.path.isfile(runtime):
        return runtime
    raise RuntimeError('Abaqus bundled SMAPython.exe was not found. '
                       'This release supports Windows Abaqus 2024.')


def launch():
    """Open/raise one monitor per calling CAE or Viewer kernel."""
    global _viewer, _config
    info = session_info()
    if (_viewer is not None and _viewer.poll() is None and _config is not None
            and _config['replay_path'] == info['replay_path']
            and _config['file_identity'] == info['file_identity']):
        with open(_config['focus_request'], 'w') as stream:
            stream.write(str(time.time_ns()))
        return info['replay_path']

    runtime = _python_executable()
    folder = tempfile.mkdtemp(prefix='abaqus_rpy_monitor_%s_' % os.getpid())
    info.update(focus_request=os.path.join(folder, 'focus.txt'),
                window_log=os.path.join(folder, 'window.log'))
    config_path = os.path.join(folder, 'config.json')
    with open(config_path, 'w', encoding='utf-8') as stream:
        json.dump(info, stream, ensure_ascii=False, indent=2)
    window_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'rpy_monitor_window.py')
    with open(info['window_log'], 'ab') as log:
        _viewer = subprocess.Popen(
            [runtime, window_script, '--config', config_path],
            cwd=folder, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    _config = info
    print('RPY Monitor: %s\nSession PID: %s\nDiagnostic log: %s' %
          (info['replay_path'], info['kernel_pid'], info['window_log']))
    return info['replay_path']
