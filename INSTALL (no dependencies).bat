@ECHO off
CHDIR /D "%~d0%~p0"
python setup.py install
RMDIR /S /Q "dol_c_kit.egg-info"
RMDIR /S /Q "dol_c_kit\__pycache__"
RMDIR /S /Q "dist"
RMDIR /S /Q "build"
PAUSE
