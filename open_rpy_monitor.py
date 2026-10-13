# -*- coding: utf-8 -*-
"""Use Abaqus File > Run Script on this file; no restart or installation needed."""
import os
import sys

_monitor_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'abaqus_rpy_monitor')
if _monitor_folder not in sys.path:
    sys.path.insert(0, _monitor_folder)
import rpy_monitor_kernel
rpy_monitor_kernel.launch()
