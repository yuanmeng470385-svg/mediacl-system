"""备案到期冻结测试（直接测同步扫描函数，不启动 lifespan 循环）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")

from datetime import date, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.models.base import Base
from shared.models.qualification import RepresentativeQualification
from shared.models.user import User

from app.core.filing_expiry import freeze_expired_qualifications


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kw):
    return "INTEGER"


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def _seed():
    db = TestSession()
    Base.metadata.drop_all(engine, tables=[User.__table__, RepresentativeQualification.__table__])
    Base.metadata.create_all(engine, tables=[User.__table__, RepresentativeQualification.__table__])
    db.add_all([
        User(id=1, username="rep01", full_name="张代表", phone="13800000001", role="rep",
             status="active"),
        User(id=2, username="admin", full_name="管理员", phone="13800000000", role="admin",
             status="active"),
        User(id=3, username="rep02", full_name="李代表", phone="13800000002", role="rep",
             status="active"),
        User(id=4, username="rep03", full_name="王代表", phone="13800000003", role="rep",
             status="active"),
    ])
    db.add_all([
        RepresentativeQualification(id=1, representative_id=1, education_cert="https://oss/e.pdf",
                                    filing_number="F-1", filing_expire_date=date.today() - timedelta(days=1)),
        RepresentativeQualification(id=2, representative_id=3, education_cert="https://oss/e.pdf",
                                    filing_number="F-2", filing_expire_date=date.today() + timedelta(days=30)),
        RepresentativeQualification(id=3, representative_id=4, education_cert="https://oss/e.pdf",
                                    filing_number="F-3", filing_expire_date=None),
    ])
    db.commit()
    db.close()


def test_freezes_only_expired_rep():
    _seed()
    db = TestSession()
    frozen = freeze_expired_qualifications(db)
    db.close()

    assert [u.id for u in frozen] == [1]

    db = TestSession()
    users = {u.id: u for u in db.query(User).all()}
    db.close()
    assert users[1].status == "disabled"
    assert users[2].status == "active"   # admin 不冻结
    assert users[3].status == "active"   # 未到期不冻结
    assert users[4].status == "active"   # 无到期日（有备案号无日期）不冻结


def test_second_run_is_idempotent():
    _seed()
    db = TestSession()
    freeze_expired_qualifications(db)
    frozen_again = freeze_expired_qualifications(db)
    db.close()
    assert frozen_again == []
