FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app

RUN useradd --create-home --uid 10001 gsp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

USER gsp
EXPOSE 8000
# Las migraciones corren antes de arrancar; si fallan, el contenedor no levanta.
CMD ["sh", "-c", "python -m app.db.migrar && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
