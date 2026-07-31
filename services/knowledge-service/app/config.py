"""知识库服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SERVICE_NAME = "knowledge-service"
    SERVICE_PORT = int(os.getenv("KNOWLEDGE_SERVICE_PORT", "8003"))

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

    # 阿里云 & AI
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    DASHVECTOR_API_KEY = os.getenv("DASHVECTOR_API_KEY", "")
    DASHVECTOR_ENDPOINT = os.getenv("DASHVECTOR_ENDPOINT", "")

    # OSS
    OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
    OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
    OSS_BUCKET = os.getenv("OSS_BUCKET", "medagent-files")
    OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")

    # 网关
    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
