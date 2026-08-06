# -*- coding: utf-8 -*-
"""直连百炼 WS，dump 对话协议的所有帧，定位 chat() 空答案问题。
用法: python scripts/probe_bailian_ws.py <app_id>
"""
import asyncio
import json
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()  # 从仓库根加载 .env（向上查找）

import websockets

WS_URL = os.getenv("BAILIAN_WS_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")
API_KEY = os.getenv("BAILIAN_API_KEY", "")
WORKSPACE_ID = os.getenv("BAILIAN_WORKSPACE_ID", "")


async def main(app_id: str):
    task_id = str(uuid.uuid4())
    print(f"ws={WS_URL}\napp_id={app_id}\nworkspace={WORKSPACE_ID}")
    async with websockets.connect(
        WS_URL,
        additional_headers={"Authorization": f"Bearer {API_KEY}"},
        close_timeout=10,
    ) as ws:
        start_msg = {
            "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {
                "task_group": "aigc",
                "task": "multimodal-generation",
                "function": "generation",
                "model": "multimodal-dialog",
                "input": {
                    "directive": "Start",
                    "workspace_id": WORKSPACE_ID,
                    "app_id": app_id,
                },
                "parameters": {
                    "upstream": {"type": "AudioOnly", "mode": "duplex"},
                    "client_info": {"user_id": "probe"},
                },
            },
        }
        await ws.send(json.dumps(start_msg, ensure_ascii=False))
        print(">> START sent")

        # 等待 Listening
        dialog_id = None
        for _ in range(20):
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            ev = msg.get("payload", {}).get("output", {}).get("event", "")
            print(f"<< event={ev} full={json.dumps(msg, ensure_ascii=False)[:400]}")
            if ev == "Started":
                dialog_id = msg["payload"]["output"].get("dialog_id")
            elif ev == "DialogStateChanged" and msg["payload"]["output"].get("state") == "Listening":
                break
            elif ev == "Error":
                print("!!! ERROR EVENT")
                return
        print(f"dialog_id={dialog_id}")

        respond_msg = {
            "header": {"action": "continue-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {
                "input": {
                    "directive": "RequestToRespond",
                    "type": "prompt",
                    "text": "这个药的用法用量？",
                }
            },
        }
        if dialog_id:
            respond_msg["payload"]["input"]["dialog_id"] = dialog_id
        await ws.send(json.dumps(respond_msg, ensure_ascii=False))
        print(">> RequestToRespond sent")

        n = 0
        while n < 60:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            except asyncio.TimeoutError:
                print(f"<< timeout after {n} frames")
                break
            n += 1
            ev = msg.get("payload", {}).get("output", {}).get("event", "")
            text = msg.get("payload", {}).get("output", {}).get("text", "")
            print(f"<< [{n}] event={ev} text={text!r} finished={msg.get('payload',{}).get('output',{}).get('finished')}")
            if ev == "RespondingContent":
                out = msg["payload"]["output"]
                if out.get("finished"):
                    print("    (finished) extra_info:", json.dumps(out.get("extra_info"), ensure_ascii=False)[:300])
                    break
            elif ev == "Error":
                print("!!! ERROR:", json.dumps(msg["payload"]["output"], ensure_ascii=False))
                break


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "mm_cd1af9fc5bf1444ebc50c5a8fe4e"))
