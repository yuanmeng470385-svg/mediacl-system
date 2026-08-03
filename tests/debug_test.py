#!/usr/bin/env python3
"""直接调后端服务（绕过网关）排查问题"""
import sys, os, json, time, jwt, httpx, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret")
payload = {"id": 1, "username": "admin", "role": "admin", "exp": int(time.time()) + 86400}
token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Test 1: Compliance directly
        print("=== 1. 合规直调 (8004) ===")
        r = await client.post("http://localhost:8004/api/v1/compliance/check", json={
            "content": "肺癌靶向药注意事项",
            "context": {"user_id": 1, "type": "user_input"}
        })
        print(f"  HTTP {r.status_code}: {r.json()}")

        # Test 2: Specialist list directly
        print("\n=== 2. 专员列表直调 (8001) ===")
        r = await client.get("http://localhost:8001/api/v1/specialists",
            headers={"Authorization": f"Bearer {token}"})
        print(f"  HTTP {r.status_code}")
        print(f"  {json.dumps(r.json(), ensure_ascii=False)[:500]}")

        # Test 3: Specialist chat directly
        print("\n=== 3. 专员对话直调 (8001) ===")
        r = await client.post("http://localhost:8001/api/v1/specialists/1/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "肺癌靶向药有哪些注意事项", "session_id": None})
        print(f"  HTTP {r.status_code}")
        data = r.json()
        print(f"  code={data.get('code')}, message={data.get('message','')}")
        if data.get("data"):
            d = data["data"]
            print(f"  answer: {d.get('answer','')[:200]}...")
            print(f"  evidence_level: {d.get('evidence_level')}")
            print(f"  latency_ms: {d.get('latency_ms')}")
            print(f"  blocked: {d.get('blocked')}")
        else:
            print(f"  Full: {json.dumps(data, ensure_ascii=False)[:1000]}")

        # Test 4: Gateway routing test
        print("\n=== 4. 网关路由通配测试 ===")
        # Test with and without auth
        r1 = await client.get("http://localhost:8000/api/v1/compliance/rules")
        print(f"  合规规则(白名单,无auth): HTTP {r1.status_code}")

        r2 = await client.get("http://localhost:8000/api/v1/specialists",
            headers={"Authorization": f"Bearer {token}"})
        print(f"  专员列表(有auth): HTTP {r2.status_code}")
        if r2.status_code != 200:
            print(f"  Body: {r2.text[:300]}")

asyncio.run(main())
