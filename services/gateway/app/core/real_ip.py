"""信任代理网段解析（I2/B5 修复 2026-08-13；M10 限流接线 2026-08-21）

B5 修复无条件用 request.client.host 覆盖 X-Forwarded-For/X-Real-IP（防客户端
伪造是对的），但反代/LB 部署下对端是 LB 地址，把部署层注入的真实客户端 IP
也覆盖掉了 —— 审计 client_ip 会全记成 LB 地址。TRUSTED_PROXY_CIDRS（逗号
分隔 CIDR 列表，默认空）声明信任的代理网段：仅当对端命中信任网段时，才
采用请求里部署层注入的 X-Real-IP（取第一个）作为真实客户端 IP；未配置/
未命中时维持原有覆盖行为（不信任任意客户端自报 IP），默认行为与现状一致。

M10：限流器的 IP 键同样走这套解析（原先直接 client.host，反代后全站共享
一个限流窗口——一个坏用户 429 全站陪葬）。
"""
import ipaddress
import logging
import os

logger = logging.getLogger(__name__)

_trusted_proxy_cidrs = [
    c.strip() for c in os.getenv("TRUSTED_PROXY_CIDRS", "").split(",") if c.strip()
]


def _parse_trusted_proxy_cidrs() -> list:
    """解析 TRUSTED_PROXY_CIDRS 为 ipaddress 网段对象；非法项告警跳过（不影响启动）"""
    nets = []
    for cidr in _trusted_proxy_cidrs:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXY_CIDRS 含非法 CIDR，已忽略: %r", cidr)
    return nets


_trusted_proxy_nets = _parse_trusted_proxy_cidrs()


def trusted_proxy_real_ip(request, headers: dict):
    """对端命中信任代理网段时，返回部署层注入的真实客户端 IP（X-Real-IP 首值）。

    否则返回 None —— 调用方维持原有覆盖行为（用 request.client.host）。
    """
    if not _trusted_proxy_nets or not request.client:
        return None
    try:
        peer = ipaddress.ip_address(request.client.host)
    except ValueError:
        return None
    if not any(peer in net for net in _trusted_proxy_nets):
        return None
    injected = headers.get("x-real-ip", "").strip()
    if injected:
        return injected.split(",")[0].strip()
    return None
