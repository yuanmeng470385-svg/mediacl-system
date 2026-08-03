#!/usr/bin/env python3
"""
MedAgent ARMS + SLS 监控配置脚本
运行前确保已配置 ALIYUN_ACCESS_KEY_ID / ALIYUN_ACCESS_KEY_SECRET

用法:
    python deploy/arms-monitor.py setup     # 创建 ARMS 应用 + SLS 日志项目
    python deploy/arms-monitor.py status    # 查看当前监控状态
"""
import os
import sys
import json
import time

# ---------- 配置（从环境变量读取） ----------
ALIYUN_REGION = os.getenv("ALIYUN_REGION", "cn-hangzhou")
ARMS_ENDPOINT = os.getenv("ARMS_ENDPOINT", f"arms.{ALIYUN_REGION}.aliyuncs.com")
APP_NAME = os.getenv("ARMS_APP_NAME", "medagent")
LOG_PROJECT = "medagent-logs"
LOG_STORE = "medagent-app-logs"

# 告警规则
ALERT_RULES = [
    {
        "name": "medagent-service-down",
        "metric": "service_health",
        "condition": "value == 0",
        "duration": "60s",
        "severity": "critical",
        "message": "服务 {{.service}} 不可用，请立即检查",
    },
    {
        "name": "medagent-api-error-rate",
        "metric": "api_error_rate",
        "condition": "value > 0.05",  # 5% 错误率
        "duration": "120s",
        "severity": "warning",
        "message": "API 错误率 {{.value}}% 超过 5% 阈值",
    },
    {
        "name": "medagent-api-latency-p99",
        "metric": "api_latency_p99",
        "condition": "value > 5000",  # 5 秒
        "duration": "180s",
        "severity": "warning",
        "message": "API P99 延迟 {{.value}}ms 超过 5s",
    },
    {
        "name": "medagent-compliance-block-rate",
        "metric": "compliance_block_rate",
        "condition": "value > 0.20",  # 20% 拦截率
        "duration": "300s",
        "severity": "info",
        "message": "合规拦截率 {{.value}}% 偏高，请关注",
    },
    # 百炼 WebSocket 连接异常
    {
        "name": "medagent-bailian-ws-error",
        "metric": "bailian_ws_error_count",
        "condition": "value > 10",
        "duration": "300s",
        "severity": "warning",
        "message": "百炼 WebSocket 连接错误 {{.value}} 次/5min",
    },
]


def setup():
    """创建监控配置（需要在阿里云控制台手动创建 ARMS 应用）"""
    print("=" * 50)
    print("MedAgent ARMS + SLS 监控配置")
    print("=" * 50)
    print()

    # 检查环境变量
    if not os.getenv("ALIYUN_ACCESS_KEY_ID"):
        print("❌ 请先配置 ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET 环境变量")
        sys.exit(1)

    print(f"区域: {ALIYUN_REGION}")
    print(f"应用名: {APP_NAME}")
    print()

    # ARMS 探针配置（在 docker-compose 中添加环境变量即可）
    print("📌 在 docker-compose.yml 的每个服务 environment 中添加：")
    print("""
    environment:
      - ARMS_APP_NAME=medagent
      - ARMS_REGION=cn-hangzhou
      - ARMS_LICENSE_KEY=<your_arms_license_key>
      - SLS_ENDPOINT=cn-hangzhou.log.aliyuncs.com
      - SLS_PROJECT=medagent-logs
      - SLS_LOGSTORE=medagent-app-logs
    """)

    print("📌 SLS 日志采集配置（在阿里云 SLS 控制台创建）：")
    print(f"  - 项目名: {LOG_PROJECT}")
    print(f"  - 日志库: {LOG_STORE}")
    print(f"  - 日志主题: medagent-{{service}}")
    print(f"  - 索引: 全文字段索引")
    print()

    print("📌 告警规则（需在 ARMS 控制台手动配置或通过 API）：")
    for i, rule in enumerate(ALERT_RULES, 1):
        print(f"  {i}. {rule['name']}")
        print(f"     指标: {rule['metric']}, 条件: {rule['condition']}")
        print(f"     持续时间: {rule['duration']}, 级别: {rule['severity']}")
        print()

    # 钉钉通知渠道配置
    print("📌 告警通知渠道（钉钉机器人）：")
    print("  1. 钉钉群 → 群设置 → 智能群助手 → 添加机器人 → 自定义")
    print("  2. 复制 Webhook URL")
    print("  3. 在 ARMS 告警 → 通知管理 → 新建通知策略中添加")
    print("  4. Webhook URL 配置为环境变量 DINGTALK_WEBHOOK")
    print()

    print("✅ 配置清单已生成，请在阿里云控制台完成上述配置")
    print()
    print("📖 参考文档：")
    print("  ARMS: https://help.aliyun.com/product/34362.html")
    print("  SLS:  https://help.aliyun.com/product/28958.html")


def status():
    """查看监控状态"""
    print("MedAgent 监控概览")
    print("-" * 30)
    print(f"ARMS 应用: {APP_NAME}")
    print(f"区域: {ALIYUN_REGION}")
    print(f"SLS 项目: {LOG_PROJECT}/{LOG_STORE}")
    print(f"告警规则: {len(ALERT_RULES)} 条")
    print()
    print("在阿里云控制台查看详情：")
    print(f"  ARMS: https://arms.console.aliyun.com/")
    print(f"  SLS:  https://sls.console.aliyun.com/")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "setup":
        setup()
    else:
        status()
