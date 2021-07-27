@ECHO off
pip install pyelftools --upgrade
pip install dolreader --upgrade
pip install geckolibs --upgrade
python setup.py install
RMDIR /S /Q "dol_c_kit.egg-info"
RMDIR /S /Q "dol_c_kit\__pycache__"
RMDIR /S /Q "dist"
RMDIR /S /Q "build"
PAUSE
