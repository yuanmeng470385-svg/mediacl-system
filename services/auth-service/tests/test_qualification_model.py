"""备案资质模型派生字段测试（filing_status / days_until_expiry 计算口径）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")

from datetime import date, timedelta

from shared.models.qualification import RepresentativeQualification


def _mk_qual(**kw):
    defaults = dict(
        id=1, representative_id=1, education_cert="https://oss/edu.pdf",
        audit_status="pending",
    )
    defaults.update(kw)
    return RepresentativeQualification(**defaults)


def test_status_not_filed_without_number():
    q = _mk_qual(filing_number=None)
    assert q.to_dict()["filing_status"] == "not_filed"


def test_status_expired_when_date_passed():
    q = _mk_qual(filing_number="F123", filing_expire_date=date.today() - timedelta(days=1))
    assert q.to_dict()["filing_status"] == "expired"


def test_status_valid_future_date_and_days_count():
    q = _mk_qual(filing_number="F123", filing_expire_date=date.today() + timedelta(days=30))
    assert q.to_dict()["filing_status"] == "valid"
    assert q.to_dict()["days_until_expiry"] == 30


def test_status_valid_when_number_without_date():
    q = _mk_qual(filing_number="F123", filing_expire_date=None)
    assert q.to_dict()["filing_status"] == "valid"
    assert q.to_dict()["days_until_expiry"] is None


def test_empty_number_string_counts_as_not_filed():
    q = _mk_qual(filing_number="  ")
    assert q.to_dict()["filing_status"] == "not_filed"
