"""
INTERNAL_API_KEY 密钥守卫测试（C8 修复）

守卫要求：未配置 / 代码默认值 "change-me-internal-key" / .env.example 模板占位值
"change_me_to_a_random_secret_string" → get_internal_api_key 抛 RuntimeError 拒绝启动。
否则照抄模板部署时守卫不触发，攻击者可伪造 X-Internal-Key 调 /api/v1/compliance/check
（触发付费 LLM）与 /api/v1/audit/log（伪造审计记录）。

注意：守卫是惰性的（首次调用时校验），且结果有模块级缓存 —— 每个用例前后必须清缓存。
"""
import pytest

import shared.common.internal_auth as internal_auth


@pytest.fixture(autouse=True)
def _reset_key_cache():
    """每个用例前后清掉模块级缓存，避免上个用例的值被复用"""
    internal_auth._INTERNAL_KEY = None
    yield
    internal_auth._INTERNAL_KEY = None


def test_rejects_unset(monkeypatch):
    """未配置 INTERNAL_API_KEY → RuntimeError"""
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        internal_auth.get_internal_api_key()


def test_rejects_code_default(monkeypatch):
    """等于代码默认值 change-me-internal-key → RuntimeError"""
    monkeypatch.setenv("INTERNAL_API_KEY", internal_auth.DEFAULT_INTERNAL_API_KEY)
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        internal_auth.get_internal_api_key()


def test_rejects_template_placeholder(monkeypatch):
    """等于 .env.example 模板占位值 change_me_to_a_random_secret_string → RuntimeError"""
    monkeypatch.setenv("INTERNAL_API_KEY", internal_auth.TEMPLATE_INTERNAL_API_KEY)
    with pytest.raises(RuntimeError, match="INTERNAL_API_KEY"):
        internal_auth.get_internal_api_key()


def test_accepts_strong_key(monkeypatch):
    """配置强随机值 → 正常返回"""
    monkeypatch.setenv("INTERNAL_API_KEY", "strong-test-internal-key-456")
    assert internal_auth.get_internal_api_key() == "strong-test-internal-key-456"


def test_internal_headers_carry_key(monkeypatch):
    """internal_headers 携带配置的密钥 + 链路 X-Request-ID（守卫通过后）"""
    monkeypatch.setenv("INTERNAL_API_KEY", "strong-test-internal-key-456")
    headers = internal_auth.internal_headers()
    assert headers["X-Internal-Key"] == "strong-test-internal-key-456"
    # 链路追踪（需求 7.1）：context 为空时生成合法 UUID 并写入 context
    import uuid
    assert uuid.UUID(headers["X-Request-ID"])
    assert internal_auth.get_request_id() == headers["X-Request-ID"]


def test_internal_headers_reuse_context_request_id(monkeypatch):
    """context 已有 request_id（网关透传后中间件 set）→ 内部调用同链传递"""
    monkeypatch.setenv("INTERNAL_API_KEY", "strong-test-internal-key-456")
    internal_auth.set_request_id("chain-rid-abc")
    headers = internal_auth.internal_headers()
    assert headers["X-Request-ID"] == "chain-rid-abc"
