"""审计服务配置"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SERVICE_NAME = "audit-service"
    SERVICE_PORT = int(os.getenv("AUDIT_SERVICE_PORT", "8005"))

    # 审计服务用专用低权账号 medagent_audit（migrations/002_audit_immutable.sql），
    # 该账号对 audit_logs 只有 INSERT/SELECT —— "不可篡改"在 DB 层真正生效。
    DATABASE_URL = os.getenv("AUDIT_DATABASE_URL") or os.getenv(
        "DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent"
    )
    JWT_SECRET = os.getenv("JWT_SECRET", "")

    # 审计日志保留天数（默认 3 年）——由 cleanup 后台任务消费（2026-08-11 起生效，
    # 此前是死配置：只定义从未清理）
    AUDIT_LOG_RETENTION_DAYS = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "1095"))
    # 清理周期（小时，默认每天一次）
    AUDIT_LOG_CLEANUP_INTERVAL_HOURS = int(os.getenv("AUDIT_LOG_CLEANUP_INTERVAL_HOURS", "24"))
    # 清理专用连接：medagent_audit_cleanup 专职删除账号（见 migrations/005_audit_cleanup.sql，
    # 仅 SELECT+DELETE，保持不可篡改语义）。未配置时回退应用连接（medagent_audit 无
    # DELETE 权限，清理会记 error 日志提示配置，不会崩服务）。
    CLEANUP_DATABASE_URL = os.getenv("AUDIT_CLEANUP_DATABASE_URL") or os.getenv(
        "AUDIT_DATABASE_URL", "postgresql://medagent:medagent123@localhost:5432/medagent"
    )

    GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
