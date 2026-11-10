FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY portagraph ./portagraph
COPY run.py .
ENV HOST=0.0.0.0 PORT=8000 PORTAGRAPH_DATA_DIR=/data ALLOW_LOCAL_PATHS=0
VOLUME /data
EXPOSE 8000
CMD ["python", "run.py"]
