"""知识库服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SERVICE_NAME = "knowledge-service"
    SERVICE_PORT = int(os.getenv("KNOWLEDGE_SERVICE_PORT", "8003"))

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    JWT_SECRET = os.getenv("JWT_SECRET", "")

    # 阿里云 & AI
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    DASHVECTOR_API_KEY = os.getenv("DASHVECTOR_API_KEY", "")
    DASHVECTOR_ENDPOINT = os.getenv("DASHVECTOR_ENDPOINT", "")

    # 百炼 WebSocket（管理 App 知识库）
    BAILIAN_API_KEY = os.getenv("BAILIAN_API_KEY", "")
    BAILIAN_WS_URL = os.getenv("BAILIAN_WS_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")
    BAILIAN_WORKSPACE_ID = os.getenv("BAILIAN_WORKSPACE_ID", "")
    BAILIAN_KB_ID = os.getenv("BAILIAN_KB_ID", "")
    BAILIAN_INDEX_ID = os.getenv("BAILIAN_INDEX_ID", "")
    BAILIAN_APP_ID = os.getenv("BAILIAN_APP_ID", "")
    BAILIAN_API_BASE = os.getenv("BAILIAN_API_BASE", "https://bailian.aliyuncs.com/v2")
    ALIBABA_CLOUD_ACCESS_KEY_ID = os.getenv(
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        os.getenv("ALIYUN_ACCESS_KEY_ID", ""),
    )
    ALIBABA_CLOUD_ACCESS_KEY_SECRET = os.getenv(
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        os.getenv("ALIYUN_ACCESS_KEY_SECRET", ""),
    )

    # OSS
    OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
    OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
    OSS_BUCKET = os.getenv("OSS_BUCKET", "medagent-files")
    OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "oss-cn-hangzhou.aliyuncs.com")

    # 网关
    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
