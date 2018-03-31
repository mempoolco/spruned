#!/bin/bash
rm -rf venv
virtualenv -p python3.6 venv
venv/bin/pip install -r requirements.txt
bash ./coverage.sh
