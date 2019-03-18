#!/bin/bash
rm -rf venv3.6
virtualenv -p python3.6 venv3.6
venv3.6/bin/python setup.py install
venv3.6/bin/pip install coverage==4.5.1
bash ./coverage.sh
