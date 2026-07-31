"""API 网关配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SERVICE_NAME = "gateway"
    SERVICE_PORT = int(os.getenv("GATEWAY_PORT", "8000"))

    JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # 后端服务地址（Docker 内部网络用服务名，本地开发用 localhost）
    SPECIALIST_SERVICE_URL = os.getenv("SPECIALIST_SERVICE_URL", "http://localhost:8001")
    VISIT_SERVICE_URL = os.getenv("VISIT_SERVICE_URL", "http://localhost:8002")
    KNOWLEDGE_SERVICE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8003")
    COMPLIANCE_SERVICE_URL = os.getenv("COMPLIANCE_SERVICE_URL", "http://localhost:8004")
    AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://localhost:8005")
    HCP_SERVICE_URL = os.getenv("HCP_SERVICE_URL", "http://localhost:8006")

    # 限流配置
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))


settings = Settings()
