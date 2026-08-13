"""审计日志引擎单元测试"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.core.logger import AuditLogger


def _make_mock_db():
    """创建一个模拟的数据库 session，add/commit/refresh 行为正确"""
    mock_db = MagicMock()

    def refresh_side_effect(obj):
        # 模拟数据库自增 ID
        obj.id = 1

    mock_db.refresh.side_effect = refresh_side_effect
    return mock_db


class TestAuditLogger:
    """审计日志记录测试"""

    def setup_method(self):
        self.logger = AuditLogger()

    def test_log_success(self):
        """正常写入审计日志"""
        mock_db = _make_mock_db()
        log_id = self.logger.log(
            mock_db,
            service_name="test-service",
            user_id=1,
            action="test_action",
            resource_type="test",
            resource_id="123",
        )
        assert log_id == 1
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    def test_log_with_ai_data(self):
        """带 AI 数据的日志（prompt/response 只存 hash）"""
        mock_db = _make_mock_db()
        log_id = self.logger.log(
            mock_db,
            service_name="specialist-service",
            user_id=1,
            action="chat_response",
            ai_involved=True,
            ai_model="qwen-max",
            ai_prompt="患者的提问内容",
            ai_response="AI 的回答内容",
            request_id="test-uuid",
        )
        assert log_id == 1

    def test_log_failure_does_not_raise(self):
        """审计日志写入失败不应抛出异常"""
        mock_db = MagicMock()
        mock_db.add.side_effect = Exception("DB error")

        log_id = self.logger.log(
            mock_db,
            service_name="test-service",
            action="test_action",
        )
        assert log_id is None
        mock_db.rollback.assert_called()

    def test_log_ignores_unknown_keys(self):
        """回归：#3 未知键不再抛 TypeError（log(db, **request) 白名单吸收）"""
        mock_db = _make_mock_db()
        log_id = self.logger.log(
            mock_db,
            service_name="test-service",
            action="test_action",
            biz_ext_field="多余字段",
            extra_nested={"a": 1},
        )
        assert log_id == 1
        mock_db.add.assert_called_once()

    def test_log_with_compliance_result(self):
        """带合规审核结果的审计日志"""
        mock_db = _make_mock_db()
        log_id = self.logger.log(
            mock_db,
            service_name="specialist-service",
            user_id=1,
            action="chat_response",
            compliance_result={
                "blocked": False,
                "risk_level": "low",
                "violations": []
            },
        )
        assert log_id == 1

    def test_log超长字符串字段按列长截断(self):
        """A6 防静默丢：超长字符串按列长截断落库，保证至少落一条截断记录，
        而不是整条 INSERT 因 DataError 失败被 log() 的 except 吞掉（审计留痕
        静默丢失）。列长与 shared/models/audit_log.py / init_db.sql 对齐"""
        mock_db = _make_mock_db()
        log_id = self.logger.log(
            mock_db,
            service_name="x" * 80,
            action="a" * 200,
            resource_type="t" * 60,
            resource_id="r" * 150,
            ai_model="m" * 60,
            # risk_level 由 compliance_result 派生（非 log() 直接入参）
            compliance_result={"risk_level": "high" * 10},
            client_ip="1" * 60,
            request_id="z" * 300,
            user_agent="u" * 500,  # TEXT 列，不截断
        )
        assert log_id == 1
        entry = mock_db.add.call_args.args[0]
        assert len(entry.service_name) == 50
        assert len(entry.action) == 100
        assert len(entry.resource_type) == 50
        assert len(entry.resource_id) == 100
        assert len(entry.ai_model) == 50
        assert len(entry.risk_level) == 20
        assert len(entry.client_ip) == 50
        assert len(entry.request_id) == 100
        assert len(entry.user_agent) == 500
