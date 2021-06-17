flake8:
	flake8 tests/ flask_restless/

isort:
	isort tests/ flask_restless/

mypy:
	mypy flask_restless/

check: isort flake8 mypy