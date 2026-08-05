"""Prometheus 指标端点（方案 15.4 监控数据源）"""
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["metrics"])

REQUESTS = Counter("http_requests_total", "HTTP 请求总数", ["service", "method"])
CHAT_LATENCY = Histogram(
    "specialist_chat_latency_seconds", "专员回答延迟（秒）",
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30),
)
COMPLIANCE_BLOCKS = Counter("compliance_blocks_total", "合规拦截总数", ["action", "severity"])


@router.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
