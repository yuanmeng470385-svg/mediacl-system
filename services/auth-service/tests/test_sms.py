"""AliyunSmsSender 真实现测试（mock dysmsapi 客户端，不真发短信）"""
import pytest
from app.services.sms import AliyunSmsSender, SmsSendError


class FakeResponse:
    def __init__(self, code: str, message: str = ""):
        self.body = type("Body", (), {"code": code, "message": message})


class FakeClient:
    def __init__(self, code: str = "OK"):
        self.code = code
        self.last_req = None

    def send_sms(self, req):
        self.last_req = req
        return FakeResponse(self.code)


def test_aliyun_sender_缺配置抛错(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "")
    with pytest.raises(SmsSendError):
        AliyunSmsSender()


def test_aliyun_sender_签名缺失抛错(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "SMS_123")
    with pytest.raises(SmsSendError):
        AliyunSmsSender()


def test_aliyun_sender_发送成功(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "测试签名")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "SMS_123")
    fake = FakeClient()
    monkeypatch.setattr(AliyunSmsSender, "_make_client", lambda self: fake)
    sender = AliyunSmsSender()
    sender.send_code("13800138000", "123456")
    req = fake.last_req
    assert req.phone_numbers == "13800138000"
    assert req.sign_name == "测试签名"
    assert req.template_code == "SMS_123"
    assert req.template_param == '{"code": "123456"}'


def test_aliyun_sender_业务失败抛错(monkeypatch):
    monkeypatch.setattr("app.config.settings.SMS_SIGN_NAME", "测试签名")
    monkeypatch.setattr("app.config.settings.SMS_TEMPLATE_CODE", "SMS_123")
    fake = FakeClient(code="isv.MOBILE_NUMBER_ILLEGAL")
    monkeypatch.setattr(AliyunSmsSender, "_make_client", lambda self: fake)
    sender = AliyunSmsSender()
    with pytest.raises(SmsSendError):
        sender.send_code("13800138000", "123456")
