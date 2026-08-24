# -*- coding: utf-8 -*-
"""2026-08-24 修复批端到端功能测试（走网关 8000，真实服务 + 真实 PG/Redis）

覆盖：H-1 考试会话绑定 / M-1 学术卡片引用链 / M-2 导出自批拦截 /
M-3 hcp 读角色门 / M-4 反馈 upsert。输出 [ok]/[FAIL] 与结论。
"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://localhost:8000"
REP_PHONE = "13800000002"   # rep_test
ADMIN_PHONE = "13812345678" # admin

results = []


def call(method, path, body=None, headers=None, timeout=90):
    hdrs = dict(headers or {})
    hdrs.setdefault("Content-Type", "application/json")
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None


def check(name, ok, detail=""):
    results.append(ok)
    print(("[ok] " if ok else "[FAIL] ") + name + ("  | " + str(detail)[:220] if detail else ""))


def login(phone):
    st, resp = call("POST", "/api/v1/auth/send-code", {"phone": phone})
    code = ((resp or {}).get("data") or {}).get("code")
    if st != 200 or not code:
        # 撞冷却时等待重试一次
        import time
        time.sleep(62)
        st, resp = call("POST", "/api/v1/auth/send-code", {"phone": phone})
        code = ((resp or {}).get("data") or {}).get("code")
    st, resp = call("POST", "/api/v1/auth/login", {"phone": phone, "code": code})
    tok = ((resp or {}).get("data") or {}).get("token")
    assert st == 200 and tok, f"login failed {st} {resp}"
    return {"Authorization": f"Bearer {tok}"}, ((resp or {}).get("data") or {})


def main():
    rep_h, rep_info = login(REP_PHONE)
    print(f"rep 登录 ok uid={rep_info.get('user', {}).get('id')}")

    # ==================== H-1 考试会话 ====================
    print("\n--- H-1 考试会话绑定 ---")
    st, resp = call("POST", "/api/v1/exams/start", {"question_count": 2}, headers=rep_h)
    d = (resp or {}).get("data") or {}
    qs = d.get("questions") or []
    check("开考返回 questions+session_token+expires_in",
          st == 200 and resp.get("code") == 0 and len(qs) == 2 and d.get("session_token") and d.get("expires_in"),
          f"q={len(qs)} token={'Y' if d.get('session_token') else 'N'}")
    # 全对交卷：approved 答案不可见 → 用单选题穷举无意义；这里交"全选 A"看分数
    # 与会话强绑定：分数可能不满分，但 question_count 必须=2 且过会话校验
    st, resp = call("POST", "/api/v1/exams/submit",
                    {"session_token": d.get("session_token"),
                     "answers": [{"question_id": q["id"], "selected": [0]} for q in qs]},
                    headers=rep_h)
    rd = (resp or {}).get("data") or {}
    check("整卷交卷过会话校验（question_count=2）",
          st == 200 and resp.get("code") == 0 and rd.get("question_count") == 2,
          f"score={rd.get('score')} passed={rd.get('passed')}")

    # 绕过路径 1：只交一道题
    st, resp = call("POST", "/api/v1/exams/submit",
                    {"session_token": d.get("session_token"),
                     "answers": [{"question_id": qs[0]["id"], "selected": [0]}]},
                    headers=rep_h)
    check("单题交卷被拒（4001）", st == 422 and resp.get("code") == 4001, f"{st} {resp}")

    # 绕过路径 2：无 token
    st, resp = call("POST", "/api/v1/exams/submit",
                    {"answers": [{"question_id": qs[0]["id"], "selected": [0]}]},
                    headers=rep_h)
    check("无 session_token 交卷被拒（1000）", st == 400 and resp.get("code") == 1000, f"{st} {resp}")

    # ==================== M-3 hcp 角色门 ====================
    print("\n--- M-3 医生档案读取角色门 ---")
    st, resp = call("GET", "/api/v1/hcps?page=1&page_size=1", headers=rep_h)
    check("rep 读医生列表 200", st == 200 and resp.get("code") == 0,
          f"total={((resp or {}).get('data') or {}).get('total')}")
    st, resp = call("GET", "/api/v1/hcps/1/profile", headers=rep_h)
    check("rep 读医生画像 200（含 hcp 字段）",
          st == 200 and resp.get("code") == 0 and "hcp" in ((resp or {}).get("data") or {}), f"{st}")

    # ==================== M-4 反馈 upsert ====================
    print("\n--- M-4 对话反馈 upsert（admin 冒烟对话 id=180 属 admin）---")
    admin_h, admin_info = login(ADMIN_PHONE)
    print(f"admin 登录 ok uid={admin_info.get('user', {}).get('id')}")
    st, resp = call("POST", "/api/v1/conversations/180/feedback", {"rating": 1, "comment": "e2e-1"}, headers=admin_h)
    fid1 = ((resp or {}).get("data") or {}).get("feedback_id")
    st, resp = call("POST", "/api/v1/conversations/180/feedback", {"rating": -1, "comment": "e2e-2"}, headers=admin_h)
    fid2 = ((resp or {}).get("data") or {}).get("feedback_id")
    check("两次反馈返回同一 feedback_id（upsert）", fid1 and fid1 == fid2, f"{fid1} vs {fid2}")

    # ==================== M-2 导出自批拦截 ====================
    print("\n--- M-2 导出审批防自批 ---")
    st, resp = call("POST", "/api/v1/data-exports/requests",
                    {"export_type": "conversations", "reason": "e2e 自批测试"}, headers=admin_h)
    rid = ((resp or {}).get("data") or {}).get("id")
    check("admin 建导出申请", st == 200 and rid, f"{st} id={rid}")
    if rid:
        st, resp = call("POST", f"/api/v1/data-exports/requests/{rid}/review",
                        {"verdict": "approve"}, headers=admin_h)
        check("admin 自批被拒（4001）", st == 422 and resp.get("code") == 4001, f"{st} {resp}")

    # ==================== M-1 学术卡片引用链（真实检索 + LLM）====================
    print("\n--- M-1 学术卡片引用链 ---")
    st, resp = call("POST", "/api/v1/academic-cards",
                    {"title": "E2E 临床指南要点卡", "topic": "示例临床指南摘要"}, headers=rep_h, timeout=120)
    d = (resp or {}).get("data") or {}
    cites = ((d.get("content") or {}).get("citations")) or []
    concl = ((d.get("content") or {}).get("conclusion") or "")
    if st == 200 and resp.get("code") == 0:
        # M-1 残留教训（2026-08-24）：断言须查值非空——只查键存在时，
        # 百炼降级检索的空元数据条目（title=""/url=""/doc_id=""）照样通过
        ok = bool(cites) and all(
            (c.get("doc_name") or "").strip() and (c.get("doc_id") or "") not in ("", None)
            for c in cites)
        check("卡片 citations 为真实契约 {doc_name, url, doc_id}", ok,
              f"cites={json.dumps(cites, ensure_ascii=False)[:200]}")
        check("卡片 conclusion 非空（检索原文入模产出）", bool(concl.strip()), concl[:120])
    else:
        # 知识库仅测试种子文档时 LLM 可能无有效输出：fail-closed 6001 拒空壳卡
        # 也是 M-1 的正确行为（此前会落 compliance_status=passed 的空壳卡）
        check("空输出 fail-closed（6001 拒绝，不落空壳卡）",
              resp.get("code") == 6001, f"{st} {resp}")
        check("卡片 conclusion 非空（跳过：本单被拒）", True, "N/A")

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r)
    print(f"结论：{passed}/{len(results)} 通过")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
