# 表对比工具(Table Diff)- 容器镜像
# 构建: docker build -t table-diff .
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    TABLE_DIFF_HOST=0.0.0.0 \
    TABLE_DIFF_PORT=8000 \
    TABLE_DIFF_DATA_DIR=/app/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/entry.py .

VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "entry.py"]
