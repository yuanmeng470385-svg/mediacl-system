"""审计服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SERVICE_NAME = "audit-service"
    SERVICE_PORT = int(os.getenv("AUDIT_SERVICE_PORT", "8005"))

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

    # 审计日志保留天数（默认 3 年）
    AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "1095"))

    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
