"""认证服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class Settings:
    SERVICE_NAME = "auth-service"
    SERVICE_PORT = int(os.getenv("AUTH_SERVICE_PORT", "8007"))

    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    JWT_SECRET = os.getenv("JWT_SECRET", "")

    # --- 验证码策略 ---
    CODE_LENGTH = int(os.getenv("AUTH_CODE_LENGTH", "6"))
    CODE_TTL_SECONDS = int(os.getenv("AUTH_CODE_TTL_SECONDS", "300"))      # 验证码有效期 5 分钟
    CODE_RESEND_SECONDS = int(os.getenv("AUTH_CODE_RESEND_SECONDS", "60")) # 重发冷却 60 秒
    CODE_MAX_ATTEMPTS = int(os.getenv("AUTH_CODE_MAX_ATTEMPTS", "5"))      # 单个验证码最多试 5 次

    # --- 短信通道 ---
    # console（默认，只写日志）/ aliyun（需签名与模板 CODE）
    SMS_PROVIDER = os.getenv("AUTH_SMS_PROVIDER", "console")
    SMS_SIGN_NAME = os.getenv("AUTH_SMS_SIGN_NAME", "")
    SMS_TEMPLATE_CODE = os.getenv("AUTH_SMS_TEMPLATE_CODE", "")

    # --- 开发模式 ---
    # 打开后 send-code 会在响应体里回传验证码，方便本地联调。生产必须为 false。
    DEV_MODE = _as_bool(os.getenv("AUTH_DEV_MODE", "false"))

    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")

    # --- OSS（资质证书文件；与 knowledge-service 共用 .env 键名）---
    OSS_ACCESS_KEY_ID = os.getenv("OSS_ACCESS_KEY_ID", "")
    OSS_ACCESS_KEY_SECRET = os.getenv("OSS_ACCESS_KEY_SECRET", "")
    OSS_ENDPOINT = os.getenv("OSS_ENDPOINT", "")
    OSS_BUCKET = os.getenv("OSS_BUCKET", "")

    # --- 备案到期扫描 ---
    QUALIFICATION_CHECK_INTERVAL_HOURS = int(os.getenv("QUALIFICATION_CHECK_INTERVAL_HOURS", "24"))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
