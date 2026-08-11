"""审计日志保留天数清理测试（AUDIT_LOG_RETENTION_DAYS 生效实现，2026-08-11）

覆盖：
- cleanup_expired_logs 分批删除：按 cutoff 过滤、小批时一轮终止、满批时多轮
- cutoff 计算正确（naive UTC：timestamp < utcnow - retention_days）
- run_cleanup_once 权限不足时抛异常（由 lifespan 任务记 error 日志，不静默）
"""
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest

from app.core.cleanup import cleanup_expired_logs


def _make_db(rowcounts):
    """fake session：execute 依次返回 rowcount 序列，记录调用参数"""
    db = MagicMock()
    results = [MagicMock(rowcount=n) for n in rowcounts]

    def _execute(sql, params=None):
        db.calls.append((str(sql), params))
        return results[min(len(db.calls) - 1, len(results) - 1)]

    db.calls = []
    db.execute.side_effect = _execute
    return db


class TestCleanupExpiredLogs:
    def test_single_small_batch_stops(self):
        """删除数 < batch 时一轮终止"""
        db = _make_db([3])
        result = cleanup_expired_logs(db, retention_days=1095, batch=5000)
        assert result["deleted"] == 3
        assert result["batches"] == 1
        assert len(db.calls) == 1

    def test_multiple_full_batches_loop(self):
        """每轮都删满 batch → 继续，直到不足一批"""
        db = _make_db([5000, 5000, 200])
        result = cleanup_expired_logs(db, retention_days=365, batch=5000)
        assert result["deleted"] == 10200
        assert result["batches"] == 3
        assert len(db.calls) == 3

    def test_cutoff_is_utcnow_minus_days(self):
        """cutoff = utcnow - retention_days（naive UTC，与 timestamp 列约定一致）"""
        db = _make_db([0])
        from datetime import datetime, timedelta
        cleanup_expired_logs(db, retention_days=1095, batch=5000)
        sql, params = db.calls[0]
        assert "timestamp < :cutoff" in sql
        expected = datetime.utcnow() - timedelta(days=1095)
        assert (expected - params["cutoff"]).total_seconds() < 60

    def test_zero_deleted_stops(self):
        """无过期数据 → 一轮终止（删除 0 行）"""
        db = _make_db([0])
        result = cleanup_expired_logs(db, retention_days=30, batch=5000)
        assert result["deleted"] == 0
        assert result["batches"] == 1


class TestRunCleanupOnce:
    def test_permission_failure_raises_not_silent(self, monkeypatch):
        """权限不足（应用账号无 DELETE）→ 抛异常，由 lifespan 任务记 error 日志（不静默）"""
        from app.core import cleanup as cleanup_mod

        def _denied(db, retention_days):
            raise PermissionError("permission denied for table audit_logs")

        monkeypatch.setattr(cleanup_mod, "cleanup_expired_logs", _denied)
        with pytest.raises(PermissionError):
            cleanup_mod.run_cleanup_once()
