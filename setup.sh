#!/bin/bash
rm -rf venv
virtualenv -p python3.5 venv
venv/bin/pip install -U pip
venv/bin/pip install -U setuptools
venv/bin/python setup.py install
bash ./coverage.sh
