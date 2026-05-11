FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY amazon_recon ./amazon_recon
COPY web_app ./web_app
COPY data/review_app.sqlite3 ./data/review_app.sqlite3

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "web_app.app:app"]
