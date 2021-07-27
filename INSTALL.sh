#!/bin/sh
pip install pyelftools --upgrade
pip install dolreader --upgrade
pip install geckolibs --upgrade
sudo python setup.py install
sudo rm -r -d "./dol_c_kit.egg-info"
sudo rm -r -d "./dol_c_kit/__pycache__"
sudo rm -r -d "./dist"
sudo rm -r -d "./build"
read -rsn1 -p"Press any key to continue . . .";echo;echo
