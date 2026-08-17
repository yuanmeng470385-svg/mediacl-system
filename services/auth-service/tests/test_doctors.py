"""医生端端点测试（角色 / 认证 / 后续任务追加）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JWT_SECRET", "test-secret-not-a-default-value")


def test_valid_roles_includes_doctor():
    from app.api.users import VALID_ROLES
    assert "doctor" in VALID_ROLES
