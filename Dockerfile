FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIND_DADOS=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY prospector ./prospector
COPY nichos.json wsgi.py ./

RUN useradd --create-home find && mkdir -p /data && chown find /data
USER find
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=4)"

# 1 processo: as buscas em andamento vivem na memória dele; as threads atendem
# várias pessoas ao mesmo tempo. ponytail: fila no banco quando houver clientes pagantes.
CMD ["gunicorn", "--workers", "1", "--threads", "8", "--bind", "0.0.0.0:8000", \
     "--timeout", "120", "--access-logfile", "-", "wsgi:app"]
