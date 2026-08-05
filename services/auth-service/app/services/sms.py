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
    """
    阿里云短信（dysmsapi）—— 尚未接入。

    接入前需要在阿里云控制台申请并补齐三项配置：
        AUTH_SMS_SIGN_NAME     短信签名
        AUTH_SMS_TEMPLATE_CODE 模板 CODE（形如 SMS_123456789）
        复用现有 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET

    这里故意抛错而不是静默降级到日志 —— 配成 aliyun 却发不出去时，
    必须让调用方看到失败，否则用户会一直等一条永远不到的短信。
    """

    def send_code(self, phone: str, code: str) -> None:
        raise SmsSendError(
            "阿里云短信通道尚未接入：缺少短信签名与模板 CODE。"
            "请先补齐 AUTH_SMS_SIGN_NAME / AUTH_SMS_TEMPLATE_CODE，"
            "或把 AUTH_SMS_PROVIDER 设回 console。"
        )


def get_sms_sender(provider: str) -> SmsSender:
    """按配置返回发送器"""
    normalized = (provider or "console").strip().lower()
    if normalized == "aliyun":
        return AliyunSmsSender()
    if normalized != "console":
        logger.warning("未知的 AUTH_SMS_PROVIDER=%s，回退到 console", provider)
    return ConsoleSender()
