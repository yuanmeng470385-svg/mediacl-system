"""pytest 基础设施：把仓库根目录加入 sys.path（shared/ 包位于仓库根）"""
import os
import sys

import pytest

# 本文件位于 services/specialist-service/tests/，需上溯三级到仓库根
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))


@pytest.fixture(autouse=True)
def _isolate_share_web_url_base(monkeypatch):
    """部署挂账 §4：share_url 前缀受 SHARE_WEB_URL_BASE 影响（twin_subscriptions
    每请求读 env）。本机根 .env 有演示值，会污染默认断言——测试默认清掉回到
    深链形态（medagent-doctor://twin/），需要 web 落地页形态的用例自行 setenv。
    """
    monkeypatch.delenv("SHARE_WEB_URL_BASE", raising=False)
