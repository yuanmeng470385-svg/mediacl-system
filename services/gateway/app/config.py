"""API 网关配置"""
import os
from dotenv import load_dotenv

load_dotenv()

# 网关用 JWT_SECRET 验证所有请求的 token（密钥由 auth-service 签发 token 时使用）。
# 与 auth-service 相同的 fail-fast 模式：未配置 / 代码默认值 / .env.example 模板占位值
# → 拒绝启动。此前这里是 os.getenv("JWT_SECRET", "dev-secret-change-me") —— 可用的默认
# 回退意味着漏配时任何人可用公开默认密钥伪造任意角色 token 通过网关（C21）。
WEAK_JWT_SECRETS = {"", "dev-secret-change-me", "change_me_to_a_random_secret_string"}


def validate_jwt_secret(secret: str) -> str:
    """校验 JWT_SECRET；未配置或为弱值直接抛 RuntimeError（fail-fast）。"""
    if secret in WEAK_JWT_SECRETS:
        raise RuntimeError(
            "JWT_SECRET 未配置或仍是默认值，gateway 拒绝启动。"
            "请在 .env 中设置一个足够随机的 JWT_SECRET（例：openssl rand -hex 32）。"
        )
    return secret


class Settings:
    SERVICE_NAME = "gateway"
    SERVICE_PORT = int(os.getenv("GATEWAY_PORT", "8000"))

    # 注意：没有默认回退值 —— 漏配时守卫拒绝启动，而不是静默用公开默认密钥
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # 后端服务地址（Docker 内部网络用服务名，本地开发用 localhost）
    AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8007")
    SPECIALIST_SERVICE_URL = os.getenv("SPECIALIST_SERVICE_URL", "http://localhost:8001")
    VISIT_SERVICE_URL = os.getenv("VISIT_SERVICE_URL", "http://localhost:8002")
    KNOWLEDGE_SERVICE_URL = os.getenv("KNOWLEDGE_SERVICE_URL", "http://localhost:8003")
    COMPLIANCE_SERVICE_URL = os.getenv("COMPLIANCE_SERVICE_URL", "http://localhost:8004")
    AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://localhost:8005")
    HCP_SERVICE_URL = os.getenv("HCP_SERVICE_URL", "http://localhost:8006")

    # 限流配置（2026-09-15 应管理员端反馈 60→600：常驻轮询+页面高频刷新下 429 频发）
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "600"))


settings = Settings()
# 模块级显式校验：无论从哪个入口（uvicorn / 测试 / 工具脚本）导入本模块，
# 弱 JWT_SECRET 都会在启动阶段被拦下，而不是在第一个请求时才暴露
validate_jwt_secret(settings.JWT_SECRET)
