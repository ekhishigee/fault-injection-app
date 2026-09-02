FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/demo-target

WORKDIR /opt/demo-target

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        stress-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY deploy/bin ./deploy/bin
RUN chmod 755 /opt/demo-target/deploy/bin/demo-fault-ctl \
              /opt/demo-target/deploy/bin/demo-probe.sh

EXPOSE 8080 8081
