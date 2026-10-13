# -*- coding: utf-8 -*-
"""Install via normal Python or Abaqus File > Run Script. Other plugins are untouched."""
import os
import shutil
import time


def install():
    source = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'abaqus_rpy_monitor')
    destination = os.path.join(os.path.expanduser('~'), 'abaqus_plugins', 'rpy_monitor')
    files = ('__init__.py', 'rpy_monitor_plugin.py', 'rpy_monitor_kernel.py',
             'rpy_monitor_window.py', 'rpy_tail.py')
    for name in files:
        if not os.path.isfile(os.path.join(source, name)):
            raise RuntimeError('Missing package file: ' + name)
    backup = None
    if os.path.isdir(destination):
        backup = destination + '.backup_' + time.strftime('%Y%m%d_%H%M%S')
        # Keep backups outside abaqus_plugins so Abaqus cannot register them twice.
        backup = os.path.join(os.path.expanduser('~'), 'abaqus_plugin_backups',
                              os.path.basename(backup))
        if os.path.exists(backup):
            backup += '_%s' % os.getpid()
        os.makedirs(os.path.dirname(backup), exist_ok=True)
        shutil.copytree(destination, backup)
    os.makedirs(destination, exist_ok=True)
    for name in files:
        shutil.copy2(os.path.join(source, name), os.path.join(destination, name))
    print('Installed RPY Monitor: ' + destination)
    if backup:
        print('Previous version backup: ' + backup)
    print('Restart CAE/Viewer, then Plug-ins > RPY Monitor > Open Current Session.')
    print('For already-open sessions, run open_rpy_monitor.py from the unpacked package.')
    return destination


if __name__ == '__main__':
    install()
