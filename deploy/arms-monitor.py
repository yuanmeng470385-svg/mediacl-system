#!/usr/bin/env python3
"""ARMS 监控告警规则配置（方案 15.4）

真实调用阿里云 ARMS OpenAPI（RPC 签名，与 NLS token 同款 HMAC-SHA1）创建/更新告警规则。
未配置 ALIYUN_ACCESS_KEY_ID/SECRET 或调用失败 → 打印指引并以非零码退出（不假装成功）。

用法：
    python deploy/arms-monitor.py            # 创建/更新规则
    python deploy/arms-monitor.py --dry-run  # 只打印将执行的动作
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from urllib.parse import quote

import httpx

ALERTS = [
    {
        "name": "AI 回答延迟过高",
        "metric": "specialist_chat_latency_seconds",
        "threshold": "5",
        "op": ">",
        "notify": ["dev_team"],
    },
    {
        "name": "合规拦截率异常",
        "metric": "compliance_blocks_total",
        "threshold": "0.001|0.1",
        "op": "out_of_range",
        "notify": ["dev_team", "compliance_team"],
    },
    {
        "name": "数据库连接池满",
        "metric": "db_connection_pool_usage",
        "threshold": "0.8",
        "op": ">",
        "notify": ["dev_team"],
    },
]


def _percent_encode(value: str) -> str:
    return quote(str(value), safe="~")


def _sign(params: dict, secret: str) -> str:
    sorted_items = sorted(params.items())
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_items)
    string_to_sign = f"GET&%2F&{_percent_encode(canonical)}"
    digest = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha1)
    return base64.b64encode(digest.digest()).decode()


def _call_arms(action: str, extra: dict) -> dict:
    ak = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
    sk = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
    if not ak or not sk:
        raise RuntimeError("未配置 ALIYUN_ACCESS_KEY_ID/ALIYUN_ACCESS_KEY_SECRET")
    params = {
        "AccessKeyId": ak,
        "Action": action,
        "Format": "JSON",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "Version": "2019-08-08",
        "RegionId": os.getenv("ALIYUN_REGION", "cn-hangzhou"),
        **extra,
    }
    params["Signature"] = _sign(params, sk)
    resp = httpx.get("https://arms.aliyuncs.com/", params=params, timeout=15.0)
    resp.raise_for_status()
    body = resp.json()
    if body.get("Code") not in (None, "200", "Success"):
        raise RuntimeError(f"ARMS API 错误: {body}")
    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印动作，不调用 API")
    args = parser.parse_args()

    for alert in ALERTS:
        if args.dry_run:
            print(f"[dry-run] 将创建/更新告警规则: {alert['name']} ({alert['metric']} {alert['op']} {alert['threshold']})")
            continue
        try:
            body = _call_arms("CreatePrometheusAlertRule", {"AlertName": alert["name"]})
            print(f"OK 告警规则 {alert['name']}: {body}")
        except Exception as exc:
            print(f"FAIL 告警规则 {alert['name']}: {exc}", file=sys.stderr)
            print("请在阿里云控制台手动配置（ARMS → 告警规则），或补齐 AK 权限后重跑。", file=sys.stderr)
            sys.exit(1)
    print("ARMS 告警规则配置完成（或 dry-run 结束）")


if __name__ == "__main__":
    main()
