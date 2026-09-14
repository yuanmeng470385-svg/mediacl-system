"""
百炼多模态交互客户端（WebSocket）

协议：WebSocket 全双工通信
地址：wss://dashscope.aliyuncs.com/api-ws/v1/inference
流程：Connect → Start → 等待 Listening → RequestToRespond(type=prompt) → 接收 RespondingContent → Stop
"""

import asyncio
import os
import json
import uuid
import logging
from typing import Dict, Optional, List

import websockets

logger = logging.getLogger(__name__)

# App 未发布时百炼下发空文本帧约 150ms/帧：8 帧 ≈ 1.2s 无内容即判定无回复，
# 提前降级（qwen）而不是等满 60 帧（~9s）。正常流式回复首字远快于此阈值。
_MAX_EMPTY_FRAMES = 8


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
        user_id: Optional[int] = None,
    ) -> Dict:
        """
        发送文本问题，获取 AI 回答

        Args:
            app_id: 百炼 App ID
            prompt: 用户问题
            session_id: 对话 ID（继续之前会话时传入，由上次返回的 dialog_id 担任）
            history: 历史对话 [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}]
            user_id: 真实用户 ID（client_info.user_id 分流用，见 chat_stream docstring）

        Returns:
            {
                "text": "AI回答全文",
                "dialog_id": "本次对话ID（下次续传时用）",
                "finished": True
            }
        """
        try:
            answer_parts = []
            citations = []
            dialog_id = session_id
            async for frame in self.chat_stream(
                app_id=app_id, prompt=prompt,
                session_id=session_id, history=history, user_id=user_id,
            ):
                if frame["type"] == "delta":
                    answer_parts.append(frame["text"])
                elif frame["type"] == "done":
                    dialog_id = frame["dialog_id"]
                    citations = frame["citations"]
            return {
                "text": answer_parts[-1] if answer_parts else "",
                "dialog_id": dialog_id,
                "finished": True,
                "citations": citations,
            }
        except websockets.exceptions.ConnectionClosed as e:
            raise BailianException(f"WebSocket 连接关闭: {e}")
        except TimeoutError:
            raise BailianException("百炼调用超时")
        except Exception as e:
            if not isinstance(e, BailianException):
                raise BailianException(f"百炼调用异常: {e}")
            raise

    async def chat_stream(
        self,
        app_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        history: Optional[List[Dict]] = None,
        user_id: Optional[int] = None,
    ):
        """流式版 chat()：每帧 yield {"type":"delta","text":...}，末尾 yield done 帧。

        done 帧: {"type":"done","text","dialog_id","citations"}
        Error 事件抛 BailianException（与 chat() 一致）。

        user_id（2026-09-11 张浩然幻觉批）：client_info.user_id 按真实用户分流
        （medagent-u{user_id}）。此前硬编码 "medagent-user" 把全部真人折叠成
        同一个百炼侧用户——App 开启记忆/用户画像时，8 月测试期 "我叫张浩然"
        的对话被记成"该用户"的画像，之后所有端、所有分身、全新会话都被
        App 称呼为张浩然。分流后各用户的百炼侧记忆互不污染。

        G2（2026-08-13）：传输层异常（wait_for 超时 TimeoutError / ws 断连
        ConnectionClosed / 畸形帧 JSONDecodeError/AttributeError 等）同样统一转
        BailianException —— 与 REST chat() 的包裹口径一致。此前裸抛会让
        answer_generator.generate_stream 只捕 BailianException 的捕获落空，
        流式中途断连直接 error 帧而不走 qwen 降级。函数内主动抛出的
        BailianException 原样透传（含空帧提前降级/Error 事件/等待超时）。
        """
        task_id = str(uuid.uuid4())
        answer_parts = []
        citations = []
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
                            # 按真实用户分流（防 App 侧记忆跨用户串味，见 chat_stream docstring）
                            "client_info": {"user_id": f"medagent-u{user_id}" if user_id else "medagent-user"},
                        },
                    },
                }
                # 续传之前会话
                if dialog_id:
                    start_msg["payload"]["input"]["dialog_id"] = dialog_id
                await ws.send(json.dumps(start_msg, ensure_ascii=False))

                # ---- Step 2: 等待 Listening ----
                for _ in range(20):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=self.timeout))
                    ev = msg.get("payload", {}).get("output", {}).get("event", "")
                    if ev == "Started":
                        dialog_id = msg["payload"]["output"].get("dialog_id", dialog_id)
                    elif ev == "DialogStateChanged":
                        if msg["payload"]["output"].get("state", "") == "Listening":
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

                # ---- Step 4: 接收回答（逐帧 yield）----
                # App 未发布/无回复时百炼持续下发空文本 RespondingContent 帧
                # （实测约 150ms/帧）——旧实现等满 60 帧才超时降级，白白等待 ~9s；
                # 连续空帧计数达到阈值即判定无回复，提前降级（真机联调 2026-08-12）
                empty_frames = 0
                for _ in range(60):
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=self.timeout))
                    ev = msg.get("payload", {}).get("output", {}).get("event", "")
                    if ev == "RespondingContent":
                        output = msg["payload"]["output"]
                        text = output.get("text", "")
                        if text.strip():
                            empty_frames = 0
                        else:
                            empty_frames += 1
                            if empty_frames >= _MAX_EMPTY_FRAMES:
                                raise BailianException(
                                    f"百炼 App 连续 {empty_frames} 帧空内容（疑似未发布或未启用回复），提前降级"
                                )
                        finished = output.get("finished", False)
                        answer_parts.append(text)  # 流式增量，每次是全量
                        # 引用溯源：解析 extra_info.docs（缺省/结构不符时防御式跳过）
                        extra_info = output.get("extra_info") or {}
                        for doc in extra_info.get("docs") or []:
                            if not isinstance(doc, dict):
                                continue
                            title = doc.get("doc_name") or doc.get("title") or doc.get("file_name") or ""
                            if title and not any(c["title"] == title for c in citations):
                                citations.append({
                                    "title": title,
                                    "url": doc.get("doc_url") or doc.get("url") or "",
                                    "doc_id": str(doc.get("doc_id") or doc.get("file_id") or ""),
                                })
                        yield {"type": "delta", "text": text}
                        if finished:
                            break
                    elif ev == "Error":
                        error = msg["payload"]["output"]
                        raise BailianException(
                            f"百炼错误 [{error.get('error_code')}]: {error.get('error_message')}"
                        )
                else:
                    raise BailianException("等待回答完成超时（60 次消息未结束）")

                # ---- Step 5: Stop ----
                await ws.send(json.dumps({
                    "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
                    "payload": {"input": {"directive": "Stop", "dialog_id": dialog_id}},
                }, ensure_ascii=False))

                final_answer = answer_parts[-1] if answer_parts else ""
                yield {
                    "type": "done",
                    "text": final_answer,
                    "dialog_id": dialog_id,
                    "citations": citations,
                }
        except websockets.exceptions.ConnectionClosed as e:
            raise BailianException(f"WebSocket 连接关闭: {e}")
        except TimeoutError:
            raise BailianException("百炼调用超时")
        except (json.JSONDecodeError, AttributeError) as e:
            raise BailianException(f"百炼返回数据格式异常: {e}")
        except Exception as e:
            if not isinstance(e, BailianException):
                raise BailianException(f"百炼调用异常: {e}")
            raise


class BailianException(Exception):
    """百炼调用异常"""
    pass
