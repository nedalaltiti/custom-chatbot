run:
	poetry run uvicorn src.hrbot.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest