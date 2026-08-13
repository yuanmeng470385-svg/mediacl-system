"""
数据库连接管理

每个微服务通过此模块获取数据库 session。
支持从环境变量 DATABASE_URL 读取连接配置。
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# 守卫需要读 .env 的 dev 标志 —— 本模块可能先于各服务 config.py 被 import
# （模型链 shared.models.* → db_session），主动向上查找仓库根 .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DEFAULT_DB_URL = "postgresql://medagent:medagent123@localhost:5432/medagent"
DEFAULT_DB_PASSWORD = "medagent123"


def _resolve_db_url() -> str:
    """读 DATABASE_URL，生产环境对默认数据库凭据 fail-fast（B5 修复 2026-08-12）。

    默认密码 medagent123 意味着任何能触达 DB 端口的攻击者可直接登录 ——
    仅当显式 dev 标志（DEV_MODE / AUTH_DEV_MODE 任一为 true）时才豁免
    （本地开发/测试用默认本地库）。
    """
    url = os.getenv("DATABASE_URL", DEFAULT_DB_URL)
    is_dev = (
        os.getenv("DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        or os.getenv("AUTH_DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")
    )
    if not is_dev and DEFAULT_DB_PASSWORD in url:
        raise RuntimeError(
            "生产环境禁止使用默认数据库密码 medagent123，请在 .env 配置 DATABASE_URL"
            "（本地开发设置 DEV_MODE=true 豁免）"
        )
    return url


DATABASE_URL = _resolve_db_url()

# 连接池配置
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,       # 连接前检测可用性
    echo=False,               # 生产环境关闭 SQL 日志
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖注入：获取数据库 session，请求结束后自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """根据所有 ORM 模型自动建表（仅开发环境使用，生产用 migration）"""
    # 延迟导入避免循环依赖
    from shared.models.base import Base
    Base.metadata.create_all(bind=engine)
