FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install poetry && poetry install --no-root

COPY . .

CMD ["poetry", "run", "uvicorn", "src.hrbot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]