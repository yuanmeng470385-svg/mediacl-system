#!/usr/bin/env python3
"""
端到端联调测试 v2
全链路：合规检查 → 数字专员对话（合规→百炼→合规→审计）
"""
import sys, os, json, time, jwt, httpx, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

GATEWAY = "http://localhost:8000"
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")

# 生成正确格式的测试 token (使用 sub 字段)
payload = {"sub": "1", "username": "admin", "role": "admin",
           "exp": int(time.time()) + 86400, "iat": int(time.time())}
token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}  {detail}")

async def main():
    global passed, failed
    print("=" * 60)
    print("MedAgent 端到端联调测试 v2")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=60.0) as client:
        # ====== Test 1: Health ======
        print("\n📌 Test 1: 服务健康检查")
        for svc, port in [("Gateway", 8000), ("Specialist", 8001), ("Compliance", 8004), ("Audit", 8005)]:
            try:
                r = await client.get(f"http://localhost:{port}/health")
                check(f"{svc} ({port})", r.status_code == 200)
            except Exception as e:
                check(f"{svc} ({port})", False, str(e)[:80])

        # ====== Test 2: Compliance Check ======
        print("\n📌 Test 2: 合规检查（正常内容）")
        r = await client.post(f"{GATEWAY}/api/v1/compliance/check", json={
            "content": "肺癌靶向药有哪些注意事项",
            "context": {"user_id": 1, "type": "user_input"}
        })
        data = r.json()
        check("正常内容不拦截", data["data"]["blocked"] == False)

        # ====== Test 3: Compliance blocks violation ======
        print("\n📌 Test 3: 合规检查（违规内容）")
        r = await client.post(f"{GATEWAY}/api/v1/compliance/check", json={
            "content": "这个药保证治好你的病",
            "context": {"user_id": 1, "type": "user_input"}
        })
        data = r.json()
        check("违规内容被拦截", data["data"]["blocked"] == True)
        check("检测到违规规则", len(data["data"]["violations"]) > 0)

        # ====== Test 4: Gateway routing ======
        print("\n📌 Test 4: 网关路由")
        r = await client.get(f"{GATEWAY}/api/v1/specialists", headers=headers)
        check("专员列表(需auth)", r.status_code == 200, f"HTTP {r.status_code}: {r.text[:100]}")

        r = await client.get(f"{GATEWAY}/api/v1/compliance/rules")
        check("合规规则(白名单)", r.status_code == 200, f"HTTP {r.status_code}")

        # ====== Test 5: Specialist Chat (Full Pipeline) ======
        print("\n📌 Test 5: 数字专员对话（全链路：合规→百炼→合规→审计）")
        try:
            r = await client.post(
                f"{GATEWAY}/api/v1/specialists/1/chat",
                headers=headers,
                json={"question": "肺癌靶向药有哪些注意事项", "session_id": None}
            )
            data = r.json()
            print(f"  HTTP {r.status_code}, code={data.get('code')}")

            check("返回200", r.status_code == 200, f"HTTP {r.status_code}")
            check("code=0", data.get("code") == 0, f"code={data.get('code')}")

            chat_data = data.get("data", {})
            if chat_data:
                check("包含answer", "answer" in chat_data)
                check("answer不为空", bool(chat_data.get("answer", "")))
                check("包含session_id", "session_id" in chat_data)
                check("包含request_id", "request_id" in chat_data)
                check("包含latency_ms", "latency_ms" in chat_data)
                check("未被合规拦截", chat_data.get("blocked") != True)

                answer = chat_data.get("answer", "")
                print(f"\n  📝 答案预览 ({len(answer)}字):")
                print(f"  {'-'*40}")
                print(f"  {answer[:400]}")
                if len(answer) > 400:
                    print(f"  ...")
                print(f"  {'-'*40}")
                print(f"  evidence_level: {chat_data.get('evidence_level')}")
                print(f"  latency_ms: {chat_data.get('latency_ms')}")
                print(f"  session_id: {chat_data.get('session_id')}")
            else:
                print(f"  Full response: {json.dumps(data, ensure_ascii=False)[:500]}")

        except Exception as e:
            check("对话请求异常", False, str(e)[:200])

        # ====== Test 6: Audit Log ======
        print("\n📌 Test 6: 审计日志")
        try:
            r = await client.get(f"{GATEWAY}/api/v1/audit/logs?page=1&page_size=5", headers=headers)
            data = r.json()
            check("审计日志查询成功", r.status_code == 200 and data.get("code") == 0,
                  f"HTTP {r.status_code}: {str(data)[:150]}")
            if data.get("data"):
                items = data["data"].get("items", [])
                total = data["data"].get("total", 0)
                print(f"  审计日志共 {total} 条，当前页 {len(items)} 条")
        except Exception as e:
            check("审计日志", False, str(e)[:100])

        # ====== Test 7: Violation chat blocked ======
        print("\n📌 Test 7: 违规问题被拦截（端到端合规）")
        try:
            r = await client.post(
                f"{GATEWAY}/api/v1/specialists/1/chat",
                headers=headers,
                json={"question": "保证治好你的肺癌，无效退款", "session_id": None}
            )
            data = r.json()
            chat_data = data.get("data", {})
            blocked = chat_data.get("blocked", False)
            check("违规问题被合规预检拦截", blocked == True or "不合规" in str(data),
                  f"blocked={blocked}, msg={data.get('message','')}")
        except Exception as e:
            check("违规问题测试", False, str(e)[:100])

    # ====== Summary ======
    print("\n" + "=" * 60)
    total = passed + failed
    print(f"结果: {passed}/{total} 通过", end="")
    if failed > 0:
        print(f", {failed} 失败 ❌")
    else:
        print(" ✅ 全部通过！")
    print("=" * 60)
    return failed == 0

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
