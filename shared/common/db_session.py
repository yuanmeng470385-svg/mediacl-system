"""
数据库连接管理

每个微服务通过此模块获取数据库 session。
支持从环境变量 DATABASE_URL 读取连接配置。
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://medagent:medagent123@localhost:5432/medagent"
)

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
