rm .coverage
rm -rf htmlcov
TESTING=1 venv/bin/coverage run --source=spruned -m unittest discover
coverage report
venv/bin/coverage html
