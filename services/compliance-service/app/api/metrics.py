"""Prometheus 指标端点（方案 15.4 监控数据源）"""
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["metrics"])

REQUESTS = Counter("http_requests_total", "HTTP 请求总数", ["service", "method"])
CHAT_LATENCY = Histogram(
    "specialist_chat_latency_seconds", "专员回答延迟（秒）",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)
# 口径对齐（2026-08-11 修复）：compliance_blocks_total 只计 action=reject
# （执行语义里 blocked 仅对 reject 生效，warn/log 是记录在案不拦截）——
# warn/log 命中不再虚增"拦截"数；全量命中另行记入 violations 指标保证可观测。
COMPLIANCE_BLOCKS = Counter("compliance_blocks_total", "合规拦截总数（仅 reject）", ["action", "severity"])
COMPLIANCE_VIOLATIONS = Counter("compliance_violations_total", "合规命中总数（reject/warn/log 全量）", ["action", "severity"])
# LLM 语义层漏检可观测（2026-08-11）：模型返回未知 rule_code 等被丢弃的违规数
COMPLIANCE_SEMANTIC_DROPS = Counter("compliance_semantic_drops_total", "语义层丢弃的违规数", ["reason"])

# 规则库加载可观测（2026-08-21 审计修复）：加载失败/为空原先只打日志静默全放行
COMPLIANCE_RULES_LOADED = Gauge("compliance_rules_loaded", "当前已加载的合规规则数（enabled 且编译通过）")
COMPLIANCE_RULES_LOAD_FAILURES = Counter("compliance_rules_load_failures_total", "规则库加载失败/为空次数")
# 审计写失败可观测（2026-08-21 审计修复）：失败原先仅 logger.error，监控不可见
COMPLIANCE_AUDIT_WRITE_FAILURES = Counter("compliance_audit_write_failures_total", "审计日志写入失败次数")


@router.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
