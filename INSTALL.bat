@echo off

python setup.py install
RMDIR /S /Q "dol_c_kit.egg-info"
RMDIR /S /Q "dol_c_kit\__pycache__"
RMDIR /S /Q "dist"
RMDIR /S /Q "build"
