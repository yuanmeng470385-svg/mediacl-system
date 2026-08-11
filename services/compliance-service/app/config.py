"""合规审核服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SERVICE_NAME = "compliance-service"
    SERVICE_PORT = int(os.getenv("COMPLIANCE_SERVICE_PORT", "8004"))

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    JWT_SECRET = os.getenv("JWT_SECRET", "")

    # AI
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    QWEN_TURBO_MODEL = os.getenv("QWEN_TURBO_MODEL", "qwen-turbo")

    # 合规规则文件路径
    RULES_YAML_PATH = os.getenv(
        "RULES_YAML_PATH",
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared", "compliance-rules", "rules.yaml")
    )

    # 规则热更新 TTL（秒）：超过该时间自动从数据库重载
    RULES_RELOAD_TTL = float(os.getenv("RULES_RELOAD_TTL", "60"))

    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
