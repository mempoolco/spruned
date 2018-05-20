#!/bin/bash
rm -rf venv
virtualenv -p python3.6 venv
venv/bin/python setup.py install
venv/bin/pip install coverage==4.5.1
bash ./coverage.sh
