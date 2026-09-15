"""App 版本检查与更新提示（2026-09-15 挂账落地）

一行一个平台（rep 代表端 / doctor 医生端），platform 即主键 —— 不套 TimestampMixin
（那会带来自增 id + created_at，对本表是噪音，只需 updated_at 供管理端展示）。
"""
from sqlalchemy import BigInteger, Column, DateTime, String, Text, func

from shared.models.base import Base


class AppVersion(Base):
    __tablename__ = "app_versions"

    platform = Column(String(20), primary_key=True)  # rep / doctor
    latest_version = Column(String(20), nullable=False)  # 高于本机版本即提示更新
    min_version = Column(String(20), nullable=False)  # 本机低于它则强制更新
    download_url = Column(Text, nullable=False)  # 绝对地址或 /apk/xxx.apk 相对路径
    release_notes = Column(Text)  # 更新说明（多行文本，App 弹窗原文展示）
    updated_by = Column(BigInteger)  # 最后修改人（users.id）
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
