FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src

RUN pip install --no-cache-dir .

RUN mkdir -p /data/runtime /data/library /mnt/endless /config

EXPOSE 8080

CMD ["python", "-m", "endless_loader.main"]

