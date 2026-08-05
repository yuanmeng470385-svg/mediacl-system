# build context = 仓库根目录（需要 COPY shared/）
#   docker build -f services/specialist-service/Dockerfile -t medagent/specialist-service .
FROM python:3.11-slim

WORKDIR /app

COPY services/specialist-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# shared 必须先于 app 拷入：所有服务都 from shared.common.* import
COPY shared/ ./shared/
COPY services/specialist-service/app/ ./app/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
