#!/usr/bin/env python3
"""ARMS 监控告警规则配置（方案 15.4）

真实调用阿里云 ARMS OpenAPI（RPC 签名，与 NLS token 同款 HMAC-SHA1）创建/更新告警规则。
未配置 ALIYUN_ACCESS_KEY_ID/SECRET 或 ARMS_CLUSTER_ID 或调用失败 → 打印指引并以非零码退出
（不假装成功）。

用法：
    python deploy/arms-monitor.py            # 按 ALERTS 清单创建/更新规则（幂等：先查后建/更新）
    python deploy/arms-monitor.py --dry-run  # 只打印将发送的完整 payload

幂等策略（2026-08-13 修复）：每条规则先 ListPrometheusAlertRules 按名称查询，
已有同名规则则 UpdatePrometheusAlertRule（AlertId=查询结果），不存在才 Create——
重跑不会重复建规则。注意旧版 API 允许重名，同名多条时全部更新并提示去重。

API 参考（ARMS 2019-08-08，旧版告警规则接口）：
    CreatePrometheusAlertRule  https://www.alibabacloud.com/help/zh/arms/prometheus-monitoring/api-arms-2019-08-08-createprometheusalertrule
    UpdatePrometheusAlertRule  https://api.aliyun.com/document/ARMS/2019-08-08/UpdatePrometheusAlertRule
    ListPrometheusAlertRules   https://www.alibabacloud.com/help/zh/arms/prometheus-monitoring/api-arms-2019-08-08-listprometheusalertrules
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

# 告警规则列表。
# 注意：只放有真实指标源的规则 —— db_connection_pool_usage（数据库连接池满）曾在此列，
# 但全仓库没有任何服务导出该指标，规则永远不会触发（永不告警的假规则），已删除。
# http_requests_total 计数器同样存在无 .inc() 接线的问题（恒 0，见 CLAUDE.md 已知问题），
# 先修好指标接线再配告警。
#
# 每条规则已翻译为 ARMS CreatePrometheusAlertRule/UpdatePrometheusAlertRule 2019-08-08
# 的完整参数（AlertName/ClusterId/Expression/Duration/Message 必填）：
#   expression: PromQL 表达式（指标定义见 services/*/app/api/metrics.py）
#   duration:   条件持续时长（1m~1440m）
#   labels/annotations: 标签与注释，请求中为 JSON 字符串（[{Name, Value}] 数组）
# 旧版 API 通知走告警运维中心（Operation Center，NotifyType=ALERT_MANAGER 缺省），
# 规则本身无联系人参数 —— 原 notify 团队列表映射进 Annotations 的 notify 键，
# 实际通知人/通知策略仍需在控制台告警运维中心按团队绑定。
# TODO（不确定项）：如需按通知策略通知，改 NotifyType=DISPATCH_RULE 并补 DispatchRuleId
# （int64，控制台创建通知策略后回填），当前未配置。
ALERTS = [
    {
        "name": "AI 回答延迟过高",
        # 原配置：metric=specialist_chat_latency_seconds, threshold=5, op=">"
        # 该指标是 Histogram（桶 0.1/0.5/1/2/5/10/30，answer_generator.py 中 observe），
        # 翻译为 P99 延迟 > 5 秒；末尾 and 子句是空数据护栏 —— 服务空闲无样本时
        # histogram_quantile 在不同 Prometheus 版本可能返回 NaN/+Inf/0，统一用
        # _count>0 兜底避免空闲误报。
        "expression": (
            "histogram_quantile(0.99, sum by (le) (rate(specialist_chat_latency_seconds_bucket[5m]))) > 5 "
            "and sum(rate(specialist_chat_latency_seconds_count[5m])) > 0"
        ),
        "duration": "5m",
        "message": "AI 回答 P99 延迟 {{$value}} 秒，超过 5 秒阈值（持续 5 分钟）",
        "labels": [{"Name": "severity", "Value": "warning"}],
        "annotations": [
            {"Name": "description", "Value": "specialist_chat_latency_seconds P99 > 5s"},
            {"Name": "notify", "Value": "dev_team"},
        ],
    },
    {
        "name": "合规拦截率异常",
        # 原配置：metric=compliance_blocks_total, threshold="0.001|0.1", op=out_of_range
        # compliance_blocks_total 只计 action=reject（拦截），compliance_violations_total
        # 计 reject/warn/log 全量命中（checker.py:236-246），两者之比即拦截率；
        # 翻译为拦截率脱离 [0.1%, 10%] 区间即告警。空闲时 0/0=NaN，比较恒 False，不误报。
        "expression": (
            "(sum(rate(compliance_blocks_total[5m])) / sum(rate(compliance_violations_total[5m])) < 0.001) "
            "or (sum(rate(compliance_blocks_total[5m])) / sum(rate(compliance_violations_total[5m])) > 0.1)"
        ),
        "duration": "10m",
        "message": "合规拦截率 {{$value}} 脱离预期区间 [0.001, 0.1]（reject / 全量命中，持续 10 分钟）",
        "labels": [{"Name": "severity", "Value": "critical"}],
        "annotations": [
            {"Name": "description", "Value": "compliance_blocks_total / compliance_violations_total 比例 <0.1% 或 >10%"},
            {"Name": "notify", "Value": "dev_team,compliance_team"},
        ],
    },
]


def _percent_encode(value: str) -> str:
    return quote(str(value), safe="~")


def _sign(params: dict, secret: str) -> str:
    sorted_items = sorted(params.items())
    canonical = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_items)
    string_to_sign = f"GET&%2F&{_percent_encode(canonical)}"
    # 阿里云 RPC v1 签名规范：HMAC 密钥 = AccessKeySecret + "&"
    digest = hmac.new((secret + "&").encode(), string_to_sign.encode(), hashlib.sha1)
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
    # Code 可能是 int（如 ListPrometheusAlertRules 返回 int64 200）或字符串 "200"/"Success"
    code = body.get("Code")
    if code is not None and str(code) not in ("200", "Success"):
        raise RuntimeError(f"ARMS API 错误: {body}")
    return body


def _rule_payload(alert: dict, cluster_id: str) -> dict:
    """把 ALERTS 条目翻译成 CreatePrometheusAlertRule/UpdatePrometheusAlertRule
    2019-08-08 的查询参数（两个接口的规则字段完全一致，Update 多一个必填 AlertId）。

    字段依据官方文档：
    - 必填：AlertName / ClusterId / Expression / Duration / Message（RegionId 由 _call_arms 统一带）
    - Type=101 表示 Prometheus 告警规则（99=自定义告警）
    - NotifyType 缺省 ALERT_MANAGER（告警运维中心统一通知）
    - Labels / Annotations 是 JSON 字符串（[{Name, Value}] 数组）
    """
    return {
        "AlertName": alert["name"],
        "ClusterId": cluster_id,
        "Type": "101",
        "NotifyType": "ALERT_MANAGER",
        "Expression": alert["expression"],
        "Duration": alert["duration"],
        "Message": alert["message"],
        "Labels": json.dumps(alert.get("labels", []), ensure_ascii=False),
        "Annotations": json.dumps(alert.get("annotations", []), ensure_ascii=False),
    }


def _list_rules_by_name(cluster_id: str, name: str) -> list:
    """ListPrometheusAlertRules 查询已有规则。

    入参 Name 可能是模糊过滤，返回后在客户端再做精确匹配（官方文档注明
    旧版规则可能存在重名，AlertName 不唯一标识一条规则）。
    """
    body = _call_arms("ListPrometheusAlertRules", {"ClusterId": cluster_id, "Name": name})
    rules = body.get("PrometheusAlertRules") or []
    return [r for r in rules if r.get("AlertName") == name]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只打印动作与完整 payload，不调用 API")
    args = parser.parse_args()

    cluster_id = os.getenv("ARMS_CLUSTER_ID", "")
    if not cluster_id and not args.dry_run:
        print("未配置 ARMS_CLUSTER_ID（ARMS Prometheus 实例 ID，控制台 → Prometheus 监控 → 实例列表可查）。",
              file=sys.stderr)
        print("请在 .env 或环境变量中设置 ARMS_CLUSTER_ID 后重跑。", file=sys.stderr)
        sys.exit(1)

    for alert in ALERTS:
        payload = _rule_payload(alert, cluster_id or "<未设置 ARMS_CLUSTER_ID>")
        if args.dry_run:
            print(f"[dry-run] 告警规则「{alert['name']}」")
            print("  步骤 1：ListPrometheusAlertRules 按名称查询已有规则")
            list_payload = {"ClusterId": payload["ClusterId"], "Name": alert["name"]}
            print(f"    payload: {json.dumps(list_payload, ensure_ascii=False)}")
            print("  步骤 2：查到同名规则 → UpdatePrometheusAlertRule（AlertId=查询结果）；未查到 → CreatePrometheusAlertRule")
            print(f"    payload: {json.dumps(payload, ensure_ascii=False)}")
            continue
        try:
            existing = _list_rules_by_name(cluster_id, alert["name"])
            if existing:
                if len(existing) > 1:
                    print(f"WARN 规则「{alert['name']}」已存在 {len(existing)} 条同名规则（旧版 API 允许重名），"
                          f"全部更新以对齐配置；如需去重请在控制台删除多余规则。", file=sys.stderr)
                for rule in existing:
                    update_payload = dict(payload, AlertId=str(rule.get("AlertId")))
                    body = _call_arms("UpdatePrometheusAlertRule", update_payload)
                    print(f"OK 更新告警规则 {alert['name']} (AlertId={rule.get('AlertId')}): {body}")
            else:
                body = _call_arms("CreatePrometheusAlertRule", payload)
                print(f"OK 创建告警规则 {alert['name']}: {body}")
        except Exception as exc:
            print(f"FAIL 告警规则 {alert['name']}: {exc}", file=sys.stderr)
            print("请在阿里云控制台手动配置（ARMS → 告警规则），或补齐 AK/ARMS_CLUSTER_ID 权限后重跑。", file=sys.stderr)
            sys.exit(1)
    print("ARMS 告警规则配置完成（或 dry-run 结束）")


if __name__ == "__main__":
    main()
