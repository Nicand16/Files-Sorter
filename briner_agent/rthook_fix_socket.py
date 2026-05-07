import sys
import os

# Ensure _MEIPASS is in sys.path before PyInstaller's multiprocessing hook runs.
# Fixes "No module named '_socket'" on Python 3.14 with PyInstaller 6.x.
if hasattr(sys, '_MEIPASS'):
    meipass = sys._MEIPASS
    if meipass not in sys.path:
        sys.path.insert(0, meipass)
    # Also ensure DLLs folder equivalent is accessible
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if exe_dir not in sys.path:
        sys.path.insert(0, exe_dir)
