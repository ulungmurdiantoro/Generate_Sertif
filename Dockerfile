FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app

# fonts-dejavu-core = font fallback bawaan bila template belum upload font.
# gosu           = untuk turun hak akses ke user non-root setelah perbaiki izin volume.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY generate_sertifikat.py ./generate_sertifikat.py
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --create-home appuser \
    && mkdir -p /data && chown -R appuser /app /data

EXPOSE 8000

# Entrypoint jalan sebagai root: benahi izin /data (volume bind-mount di VPS
# sering ter-create sebagai root), lalu turun ke user "appuser".
ENTRYPOINT ["docker-entrypoint.sh"]

# 1 worker: state job disimpan di memori proses. Paralelisme render diatur
# lewat RENDER_WORKERS (thread) di dalam worker ini.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "1", \
     "-b", "0.0.0.0:8000", "--timeout", "600", "app.main:app"]
