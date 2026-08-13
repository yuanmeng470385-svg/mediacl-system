"""
短信发送器（可插拔）

.env 里目前没有任何短信凭证（缺签名和模板 CODE），所以默认走 ConsoleSender：
验证码只写进服务日志，不外发。等凭证到位后把 AliyunSmsSender 填上、
把 AUTH_SMS_PROVIDER 改成 aliyun 即可，调用方无需改动。
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SmsSendError(RuntimeError):
    pass


class SmsSender(ABC):
    @abstractmethod
    def send_code(self, phone: str, code: str) -> None:
        """发送验证码。失败必须抛 SmsSendError（不能静默成功）。"""


class ConsoleSender(SmsSender):
    """默认实现：写日志。本地开发和 CI 用这个。"""

    def send_code(self, phone: str, code: str) -> None:
        # 只脱敏打印手机号，验证码在开发环境需要可见
        masked = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else phone
        logger.info("[ConsoleSender] 验证码已生成 phone=%s code=%s（未真实外发）", masked, code)


class AliyunSmsSender(SmsSender):
    """阿里云短信（dysmsapi）——真实通道。

    前置配置（缺一个都不能发，构造时即抛错，fail-fast）：
        AUTH_SMS_SIGN_NAME     短信签名
        AUTH_SMS_TEMPLATE_CODE 模板 CODE（形如 SMS_123456789）
        复用现有 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET
    模板变量固定为 {"code": "..."}——申请模板时变量名请命名为 code。
    """

    def __init__(self):
        from app.config import settings
        sign_name = settings.SMS_SIGN_NAME.strip()
        template_code = settings.SMS_TEMPLATE_CODE.strip()
        missing = []
        if not sign_name:
            missing.append("AUTH_SMS_SIGN_NAME")
        if not template_code:
            missing.append("AUTH_SMS_TEMPLATE_CODE")
        if missing:
            raise SmsSendError(
                f"阿里云短信通道配置缺失: {' / '.join(missing)}。"
                "补齐后重试，或把 AUTH_SMS_PROVIDER 设回 console。"
            )
        self._sign_name = sign_name
        self._template_code = template_code
        self._client = self._make_client()

    def _make_client(self):
        """创建 dysmsapi 客户端。独立方法便于测试注入。"""
        import os
        from alibabacloud_dysmsapi20170525.client import Client
        from alibabacloud_tea_openapi import models as open_api_models

        access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
        access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
        if not access_key_id or not access_key_secret:
            raise SmsSendError(
                "阿里云短信通道缺少 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET"
            )
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
            region_id="cn-hangzhou",  # dysmsapi 固定接入地域
        )
        return Client(config)

    def send_code(self, phone: str, code: str) -> None:
        import json
        from alibabacloud_dysmsapi20170525 import models as dysmsapi_models

        request = dysmsapi_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=self._sign_name,
            template_code=self._template_code,
            template_param=json.dumps({"code": code}, ensure_ascii=False),
        )
        try:
            response = self._client.send_sms(request)
        except Exception as e:  # SDK 网络/签名错误
            raise SmsSendError(f"阿里云短信发送失败: {e}") from e
        if response.body.code != "OK":
            raise SmsSendError(
                f"阿里云短信发送失败 [{response.body.code}]: {response.body.message}"
            )


def get_sms_sender(provider: str) -> SmsSender:
    """按配置返回发送器

    B5 修复（2026-08-12）：生产环境禁止 console 通道 —— ConsoleSender 会把验证码
    明文写进服务日志，是可被日志采集链路泄露的敏感信息。非 DEV_MODE 下
    provider 不是 aliyun 一律 fail-fast（请求 5xx，绝不静默放行）。
    """
    from app.config import settings
    normalized = (provider or "console").strip().lower()
    if normalized == "aliyun":
        return AliyunSmsSender()
    if not settings.DEV_MODE:
        raise SmsSendError(
            "生产环境禁止 console 短信通道（验证码会写入服务日志）。"
            "请配置 AUTH_SMS_PROVIDER=aliyun 及 AUTH_SMS_SIGN_NAME/AUTH_SMS_TEMPLATE_CODE"
        )
    if normalized != "console":
        logger.warning("未知的 AUTH_SMS_PROVIDER=%s，回退到 console", provider)
    return ConsoleSender()
