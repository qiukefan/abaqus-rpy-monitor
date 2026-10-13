# -*- coding: utf-8 -*-
"""Abaqus GUI menu registration; opening the monitor is not replayed."""
import os
from abaqusGui import (AFXForm, AFXMode, FXMAPFUNC, SEL_COMMAND, getAFXApp,
                       sendCommand, showAFXErrorDialog)


class RpyMonitorAction(AFXForm):
    def __init__(self, owner):
        AFXForm.__init__(self, owner)
        FXMAPFUNC(self, SEL_COMMAND, AFXMode.ID_ACTIVATE, RpyMonitorAction.onActivate)

    def onActivate(self, sender, selector, pointer):
        folder = os.path.dirname(os.path.abspath(__file__))
        command = ('import sys; '
                   'sys.path.insert(0, %r) if %r not in sys.path else None; '
                   'import rpy_monitor_kernel; rpy_monitor_kernel.launch()') % (folder, folder)
        try:
            sendCommand(command, False, False)
        except Exception as exc:
            showAFXErrorDialog(getAFXApp().getAFXMainWindow(), str(exc))
        return 1


_toolset = getAFXApp().getAFXMainWindow().getPluginToolset()
_rpy_action = RpyMonitorAction(_toolset)
_toolset.registerGuiMenuButton(
    buttonText='RPY Monitor|Open Current Session',
    object=_rpy_action, messageId=AFXMode.ID_ACTIVATE,
    version='1.0.0', author='RPY Monitor',
    description='Live replay commands for this CAE/Viewer session (Windows 2024).',
)
