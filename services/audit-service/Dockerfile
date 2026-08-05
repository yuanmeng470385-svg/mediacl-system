# build context = 仓库根目录（需要 COPY shared/）
#   docker build -f services/audit-service/Dockerfile -t medagent/audit-service .
FROM python:3.11-slim

WORKDIR /app

COPY services/audit-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# shared 必须先于 app 拷入：所有服务都 from shared.common.* import
COPY shared/ ./shared/
COPY services/audit-service/app/ ./app/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8005
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005", "--workers", "2"]
