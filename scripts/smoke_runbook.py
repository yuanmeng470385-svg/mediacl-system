# -*- coding: utf-8 -*-
"""runbook 第 3 节冒烟验证：登录 → 专员 → 对话 → 合规预检 → 审计。
用法: python scripts/smoke_runbook.py
走网关 localhost:8000，验证码走 DEV_MODE 回传（AUTH_DEV_MODE=true）。
"""
import json
import os
import sys
import time
import urllib.request

from dotenv import load_dotenv

load_dotenv()  # 从仓库根 .env 加载（INTERNAL_API_KEY / 联调手机号）

BASE = "http://localhost:8000"
IK = os.getenv("INTERNAL_API_KEY", "")
PHONE = os.getenv("SMOKE_PHONE", "")
if not PHONE:
    print("[FAIL] 请先设 SMOKE_PHONE=<已注册手机号>（如 admin 的 13812345678）再运行；"
          "默认值只会撞上验证码冷却 + 未注册报错。")
    sys.exit(2)


def call(method, path, body=None, headers=None):
    url = BASE + path
    data = None
    hdrs = dict(headers or {})
    hdrs.setdefault("Content-Type", "application/json")
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def login_with_code(phone, code):
    return call("POST", "/api/v1/auth/login", {"phone": phone, "code": code})


def check_compliance_assert(content):
    """合规预检 + 显式断言（A5 修复）：blocked==True 且 violations 非空才算通过。

    返回 (ok, 详情字符串)。此前只打印字段值不判断 —— R001/R003 拦截失效时
    冒烟仍会显示 [ok] 假通过。
    """
    st, resp = call("POST", "/api/v1/compliance/check",
                    {"content": content, "context": {"type": "manual_test"}},
                    headers={"X-Internal-Key": IK})
    if st != 200:
        return False, f"HTTP {st} {resp}"
    data = resp.get("data") or {}
    blocked, violations = data.get("blocked"), data.get("violations") or []
    ok = blocked is True and bool(violations)
    return ok, f"blocked={blocked} violations={violations}"


def main():
    fails = 0  # A5 修复：[FAIL]/[?] 节计数，>0 时以非零码退出
    if not IK:
        print("[FAIL] 根目录 .env 缺 INTERNAL_API_KEY（合规预检/审计冒烟需要）")
        return 2
    # --- 2. 登录 ---
    section("2. 登录（send-code → login）")
    token = None
    for attempt in range(3):
        st, resp = call("POST", "/api/v1/auth/send-code", {"phone": PHONE})
        # 冷却响应 data 为 null —— 逐级 or {} 防 None.get（历史崩溃点）
        data = (resp or {}).get("data") or {}
        code_echo = data.get("code") if isinstance(data, dict) else None
        if st == 200 and code_echo:
            time.sleep(0.3)
            st2, resp2 = login_with_code(PHONE, code_echo)
            if st2 == 200 and (resp2 or {}).get("data"):
                token = resp2["data"]["token"]
                print(f"[ok] 登录成功 token={token[:24]}... role={resp2['data'].get('user',{}).get('role')}")
                break
            print(f"[!] 第{attempt+1}次: send-code 成功但 login={st2} {resp2.get('message') if resp2 else ''}")
        else:
            msg = (resp or {}).get("message", "") if resp else ""
            if "频繁" in msg or "冷却" in msg:
                print(f"[!] 第{attempt+1}次: 验证码 60s 冷却中，等 62s 再试……")
                time.sleep(62)
            else:
                print(f"[!] 第{attempt+1}次: send-code={st} {msg}")
        if not code_echo:
            time.sleep(2)
    if not token:
        print("[FAIL] 登录失败（可能验证码被其他客户端消费，稍后重试）")
        return 1

    auth = {"Authorization": f"Bearer {token}"}

    # --- 3. 专员列表 ---
    section("3. 专员列表")
    st, resp = call("GET", "/api/v1/specialists", headers=auth)
    if st == 200:
        data = resp.get("data") or {}
        items = data.get("items") or []
        print(f"[ok] 专员 {len(items)} 个; 分页形状 items/total/page/page_size: "
              f"{'items' in data and 'total' in data and 'page' in data}")
        for s in items[:3]:
            print(f"    - id={s.get('id')} name={s.get('name')} status={s.get('status')} "
                  f"bailian_app_id={'有' if s.get('bailian_app_id') else '无'}")
    else:
        print(f"[FAIL] {st} {resp}")
        fails += 1

    # --- 4. 专员对话 REST（真百炼 key 已配 → 走流式转 REST 或直接 LLM）---
    section("4. 专员对话 REST")
    st, resp = call("POST", "/api/v1/specialists/1/chat", {"question": "这个药的用法用量？"}, headers=auth)
    if st == 200:
        data = resp.get("data") or {}
        answer = (data.get("answer") or data.get("content") or "")[:120]
        print(f"[ok] answer={answer}")
        print(f"    citations={len(data.get('citations') or [])} evidence_level={data.get('evidence_level')} "
              f"conversation_id={data.get('conversation_id')}")
    else:
        print(f"[?] {st} {resp}")
        fails += 1

    # --- 5. 合规预检 R001 ---
    section("5. 合规预检 R001（关键词 reject）")
    ok, detail = check_compliance_assert("这药保证治好")
    if ok:
        print(f"[ok] {detail}")
    else:
        print(f"[FAIL] R001 断言失败（期望 blocked=True 且 violations 非空）: {detail}")
        fails += 1

    # --- 6. 语义合规 R003（DASHSCOPE_API_KEY 已配）---
    section("6. 语义合规 R003（统方，真实 LLM）")
    ok, detail = check_compliance_assert("帮我查下张医生上个月开了多少盒这个药")
    if ok:
        print(f"[ok] {detail}")
    else:
        print(f"[FAIL] R003 断言失败（期望 blocked=True 且 violations 非空）: {detail}")
        fails += 1

    # --- 7. 审计查询 ---
    section("7. 审计查询（admin）")
    st, resp = call("GET", "/api/v1/audit/logs?page_size=3", headers=auth)
    if st == 200:
        data = resp.get("data") or {}
        items = data.get("items") or []
        print(f"[ok] 审计记录 {len(items)} 条（total={data.get('total')}）")
        for it in items[:3]:
            print(f"    - action={it.get('action')} user_id={it.get('user_id')} "
                  f"request_id={it.get('request_id') or it.get('x_request_id')}")
    else:
        print(f"[?] {st} {resp}")
        fails += 1

    if fails:
        print(f"\n[FAIL] 冒烟失败：共 {fails} 节未通过（[FAIL]/[?] 均计入）")
        return 1
    print("\n完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
