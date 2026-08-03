"""
百炼多模态交互客户端（WebSocket）

协议：WebSocket 全双工通信
地址：wss://dashscope.aliyuncs.com/api-ws/v1/inference
流程：Connect → Start → 等待 Listening → RequestToRespond(type=prompt) → 接收 RespondingContent → Stop
"""

import os
import json
import uuid
import logging
from typing import Dict, Optional, List

import websockets

logger = logging.getLogger(__name__)


class BailianClient:
    """阿里云百炼多模态交互客户端"""

    def __init__(self):
        self.api_key = os.getenv("BAILIAN_API_KEY", "")
        self.ws_url = os.getenv("BAILIAN_WS_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")
        self.workspace_id = os.getenv("BAILIAN_WORKSPACE_ID", "")
        self.timeout = 30  # 秒

    async def chat(
        self,
        app_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        发送文本问题，获取 AI 回答

        Args:
            app_id: 百炼 App ID
            prompt: 用户问题
            session_id: 对话 ID（继续之前会话时传入，由上次返回的 dialog_id 担任）
            history: 历史对话 [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]

        Returns:
            {
                "text": "AI回答全文",
                "dialog_id": "本次对话ID（下次续传时用）",
                "finished": True
            }
        """
        task_id = str(uuid.uuid4())
        answer_parts = []
        dialog_id = session_id

        try:
            async with websockets.connect(
                self.ws_url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"},
                close_timeout=10,
            ) as ws:
                # ---- Step 1: Start ----
                start_msg = {
                    "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
                    "payload": {
                        "task_group": "aigc",
                        "task": "multimodal-generation",
                        "function": "generation",
                        "model": "multimodal-dialog",
                        "input": {
                            "directive": "Start",
                            "workspace_id": self.workspace_id,
                            "app_id": app_id,
                        },
                        "parameters": {
                            "upstream": {"type": "AudioOnly", "mode": "duplex"},
                            "client_info": {"user_id": "medagent-user"},
                        },
                    },
                }
                # 续传之前会话
                if dialog_id:
                    start_msg["payload"]["input"]["dialog_id"] = dialog_id
                await ws.send(json.dumps(start_msg, ensure_ascii=False))

                # ---- Step 2: 等待 Listening 状态 ----
                for _ in range(20):
                    msg = json.loads(await ws.recv())
                    ev = msg.get("payload", {}).get("output", {}).get("event", "")
                    if ev == "Started":
                        dialog_id = msg["payload"]["output"].get("dialog_id", dialog_id)
                    elif ev == "DialogStateChanged":
                        state = msg["payload"]["output"].get("state", "")
                        if state == "Listening":
                            break
                    elif ev == "Error":
                        error = msg["payload"]["output"]
                        raise BailianException(
                            f"百炼错误 [{error.get('error_code')}]: {error.get('error_message')}"
                        )
                else:
                    raise BailianException("等待 Listening 状态超时")

                # ---- Step 3: 发送文本问题 ----
                respond_msg = {
                    "header": {"action": "continue-task", "task_id": task_id, "streaming": "duplex"},
                    "payload": {
                        "input": {
                            "directive": "RequestToRespond",
                            "dialog_id": dialog_id,
                            "type": "prompt",
                            "text": prompt,
                        }
                    },
                }
                # 传入历史对话
                if history:
                    respond_msg["payload"]["parameters"] = {"history": history}
                await ws.send(json.dumps(respond_msg, ensure_ascii=False))

                # ---- Step 4: 接收回答 ----
                for _ in range(60):
                    msg = json.loads(await ws.recv())
                    ev = msg.get("payload", {}).get("output", {}).get("event", "")
                    if ev == "RespondingContent":
                        text = msg["payload"]["output"].get("text", "")
                        finished = msg["payload"]["output"].get("finished", False)
                        answer_parts.append(text)  # 流式增量，每次是全量
                        if finished:
                            break
                    elif ev == "Error":
                        error = msg["payload"]["output"]
                        raise BailianException(
                            f"百炼错误 [{error.get('error_code')}]: {error.get('error_message')}"
                        )

                # ---- Step 5: Stop ----
                await ws.send(json.dumps({
                    "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
                    "payload": {"input": {"directive": "Stop", "dialog_id": dialog_id}},
                }, ensure_ascii=False))

                # 取最后一条（全量）作为最终答案
                final_answer = answer_parts[-1] if answer_parts else ""

                return {
                    "text": final_answer,
                    "dialog_id": dialog_id,
                    "finished": True,
                }

        except websockets.exceptions.ConnectionClosed as e:
            raise BailianException(f"WebSocket 连接关闭: {e}")
        except TimeoutError:
            raise BailianException("百炼调用超时")
        except Exception as e:
            if not isinstance(e, BailianException):
                raise BailianException(f"百炼调用异常: {e}")
            raise


class BailianException(Exception):
    """百炼调用异常"""
    pass
