"""数字专员服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # 服务
    SERVICE_NAME = "specialist-service"
    SERVICE_PORT = int(os.getenv("SPECIALIST_SERVICE_PORT", "8001"))

    # 数据库
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # JWT
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

    # 阿里云 & AI
    ALIYUN_ACCESS_KEY_ID = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    ALIYUN_ACCESS_KEY_SECRET = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    ALIYUN_REGION = os.getenv("ALIYUN_REGION", "cn-hangzhou")
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    BAILIAN_API_KEY = os.getenv("BAILIAN_API_KEY", "")
    BAILIAN_BASE_URL = os.getenv("BAILIAN_BASE_URL", "https://bailian.aliyuncs.com/v2")
    QWEN_MAX_MODEL = os.getenv("QWEN_MAX_MODEL", "qwen-max")
    QWEN_PLUS_MODEL = os.getenv("QWEN_PLUS_MODEL", "qwen-plus")
    QWEN_TURBO_MODEL = os.getenv("QWEN_TURBO_MODEL", "qwen-turbo")

    # 网关（服务间调用）
    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")

    # 日志
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
