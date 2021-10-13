@ECHO off
CHDIR /D "%~d0%~p0"
pip install pyelftools --upgrade
pip install dolreader --upgrade
pip install geckolibs --upgrade
pip install colorama --upgrade
python setup.py install
RMDIR /S /Q "freighter.egg-info"
RMDIR /S /Q "freighter\__pycache__"
RMDIR /S /Q "dist"
RMDIR /S /Q "build"
PAUSE
