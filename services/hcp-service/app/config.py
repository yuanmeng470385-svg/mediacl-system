"""医生/专家管理服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SERVICE_NAME = "hcp-service"
    SERVICE_PORT = int(os.getenv("HCP_SERVICE_PORT", "8006"))

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
