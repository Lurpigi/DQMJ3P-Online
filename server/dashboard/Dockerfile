# Statistics portal backend (docs/dashboard.md). The SIL code and data are mounted read-only.
FROM python:3.13-alpine3.22

RUN addgroup -S portal && adduser -S -G portal portal
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt
COPY dashboard ./dashboard
COPY migrations ./migrations
COPY data ./data

USER portal
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/api/v1/health', timeout=4)"
CMD ["python", "-m", "dashboard", "serve", "--host", "0.0.0.0", "--port", "8090"]
