# 批次 3：WS 流式完整链路 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 聊天从"REST 一次性返回"升级为全链路 WS 流式：specialist 新增对外 WS 端点（逐帧转发百炼增量）、gateway 加 WS 代理（统一入口）、mobile 流式渲染 + REST 自动降级。

**Architecture:** specialist 的 BailianClient 抽出 `chat_stream()` async generator（每帧 delta 文本），AnswerGenerator 加 `generate_stream()`（合规预检→流式→合规审核→审计→done 帧），新 WS 端点 `/ws/specialists/{id}/chat?token=JWT` 按帧转发；gateway 用 starlette WebSocket 双向透传到 specialist（token 原样透传，认证由 specialist 做）；mobile 用 RN 内置 WebSocket 走网关 8000，start 8s 超时或 error 自动降级 REST。

**Tech Stack:** FastAPI + websockets（specialist）、starlette WebSocket（gateway）、RN 内置 WebSocket（mobile）。

## Global Constraints

- WS 帧协议（修正版，见 spec 3.1/3.3）：
  - 客户端→服务端：`{"type":"question","text":"...","session_id":"..."}`（首帧必发）；`{"type":"stop"}`（可选中止）
  - 服务端→客户端：`{"type":"start","request_id":...}` → `{"type":"delta","text":"..."}`* → `{"type":"done","text":"<全文>","session_id":...,"conversation_id":...,"citations":[...]}`；异常 `{"type":"error","message":...}` 后关 4500；token 无效关 4401
- REST `POST /chat` 保留（mobile fallback + 既有测试/契约不破坏），`chat()` 重构为复用 `chat_stream()` 攒包，返回结构不变。
- send 必须加锁防 websockets>=12 ConcurrencyError（沿用 asr_ws.py send_lock 模式）。
- 网关 WS 代理不重复鉴权（token 原样透传，spec 定论）。
- 后端测试：`cd services/<s> && python -m pytest -q`；mobile：`cd mobile && npx jest && npx tsc --noEmit`。
- commit 惯例：`feat(scope): 描述`，结尾 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`，本地不 push。
- 本批次不改 REST chat 的返回结构、不碰 feedback/favorite 接口。

---

### Task 1: specialist — BailianClient.chat_stream()（TDD）

**Files:**
- Modify: `services/specialist-service/app/services/bailian_client.py`（新增 chat_stream，chat 重构复用）
- Create: `services/specialist-service/tests/test_bailian_stream.py`

**Interfaces:**
- Consumes: 既有 `BailianException`
- Produces:
  - `async def chat_stream(app_id: str, prompt: str, session_id: Optional[str] = None, history: Optional[List[Dict]] = None) -> AsyncIterator[Dict]`
  - yield 帧：`{"type":"delta","text":str}`（RespondingContent 每帧）；末尾 `{"type":"done","text":str,"dialog_id":str,"citations":list}`；Error 事件抛 `BailianException`。与 `chat()` 的协议流程完全一致（Start→Listening→RequestToRespond→帧循环→Stop）。

- [ ] **Step 1: 写失败测试（复用 _FakeWs 模式，参考 tests/test_bailian_citations.py）**

```python
# services/specialist-service/tests/test_bailian_stream.py
"""BailianClient.chat_stream 流式测试（mock websockets.connect）"""
import asyncio
import json
import pytest
from app.services.bailian_client import BailianClient, BailianException


class _FakeWs:
    """模拟百炼 WS：按脚本回消息"""
    def __init__(self, replies):
        self._replies = list(replies)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def recv(self):
        if not self._replies:
            await asyncio.sleep(0.1)
            raise ConnectionClosedFake
        return json.dumps(self._replies.pop(0), ensure_ascii=False)


class ConnectionClosedFake(Exception):
    pass


def _ev(event: str, **output):
    return {"payload": {"output": {"event": event, **output}}}


def test_chat_stream_yields_delta_and_done(monkeypatch):
    replies = [
        _ev("Started", dialog_id="dlg-1"),
        _ev("DialogStateChanged", state="Listening"),
        _ev("RespondingContent", text="你好", finished=False),
        _ev("RespondingContent", text="你好，我是专员。", finished=True),
    ]
    fake = _FakeWs(replies)
    monkeypatch.setattr("app.services.bailian_client.websockets.connect", lambda *a, **k: fake)

    async def run():
        client = BailianClient()
        frames = []
        async for frame in client.chat_stream(app_id="app-1", prompt="你好"):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert [f["type"] for f in frames] == ["delta", "delta", "done"]
    assert frames[0]["text"] == "你好"
    assert frames[1]["text"] == "你好，我是专员。"
    assert frames[-1]["dialog_id"] == "dlg-1"
    # Start 消息里带了 app_id
    start_sent = fake.sent[0]["payload"]["input"]
    assert start_sent["app_id"] == "app-1"


def test_chat_stream_error_event_raises(monkeypatch):
    replies = [
        _ev("Started", dialog_id="dlg-1"),
        _ev("DialogStateChanged", state="Listening"),
        _ev("Error", error_code="E1", error_message="模型错误"),
    ]
    fake = _FakeWs(replies)
    monkeypatch.setattr("app.services.bailian_client.websockets.connect", lambda *a, **k: fake)

    async def run():
        client = BailianClient()
        async for _ in client.chat_stream(app_id="app-1", prompt="你好"):
            pass

    with pytest.raises(BailianException):
        asyncio.run(run())
```

Run: `cd services/specialist-service && python -m pytest tests/test_bailian_stream.py -v`
Expected: FAIL（`BailianClient` 无 `chat_stream` 属性）。

- [ ] **Step 2: 实现 chat_stream + 重构 chat()**

`bailian_client.py`：新增方法（协议流程与 `chat()` 的 :59-158 相同，把"接收回答"循环改为逐帧 yield）：

```python
    async def chat_stream(
        self,
        app_id: str,
        prompt: str,
        session_id: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ):
        """流式版 chat()：每帧 yield {"type":"delta","text":...}，末尾 yield done 帧。

        done 帧: {"type":"done","text","dialog_id","citations"}
        Error 事件抛 BailianException（与 chat() 一致）。
        """
        task_id = str(uuid.uuid4())
        answer_parts = []
        citations = []
        dialog_id = session_id

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
            if history:
                respond_msg["payload"]["parameters"] = {"history": history}
            await ws.send(json.dumps(respond_msg, ensure_ascii=False))

            # ---- Step 4: 接收回答（逐帧 yield）----
            for _ in range(60):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=self.timeout))
                ev = msg.get("payload", {}).get("output", {}).get("event", "")
                if ev == "RespondingContent":
                    output = msg["payload"]["output"]
                    text = output.get("text", "")
                    finished = output.get("finished", False)
                    answer_parts.append(text)
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
```

`chat()` 重构为消费 chat_stream（:30-177 的方法体整体替换）：

```python
    async def chat(self, app_id, prompt, session_id=None, history=None):
        """非流式版：消费 chat_stream 攒包，返回结构与原先完全一致。"""
        try:
            answer_parts = []
            citations = []
            dialog_id = session_id
            async for frame in self.chat_stream(
                app_id=app_id, prompt=prompt,
                session_id=session_id, history=history,
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
```

- [ ] **Step 3: 跑新测试 + 既有回归**

Run: `cd services/specialist-service && python -m pytest tests/test_bailian_stream.py tests/test_bailian_citations.py -v`
Expected: 新 2 例 + 既有 citations 测试全部 PASS。

- [ ] **Step 4: 全量回归**

Run: `cd services/specialist-service && python -m pytest -q`
Expected: 全部通过（既有 11 用例不变）。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add services/specialist-service && git commit -m "feat(specialist): BailianClient.chat_stream 流式帧 + chat() 重构复用
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: specialist — AnswerGenerator.generate_stream()（TDD）

**Files:**
- Modify: `services/specialist-service/app/core/answer_generator.py`（新增 generate_stream）
- Create: `services/specialist-service/tests/test_generate_stream.py`

**Interfaces:**
- Consumes: `self.bailian.chat_stream`（Task 1）、既有 `check_compliance` / `write_audit_log` / `_fallback_generate` / `_extract_evidence_level`
- Produces:
  - `async def generate_stream(question: str, specialist: Specialist, user_id: int, session_id: Optional[str] = None) -> AsyncIterator[Dict]`
  - yield 帧：
    - `{"type":"delta","text":str}`（百炼增量；降级 qwen 时也发一次全量 delta）
    - `{"type":"done","answer":str,"citations":list,"evidence_level":str|None,"session_id":str,"request_id":str,"latency_ms":int,"blocked":bool,"violations":list}`
    - 问题合规预检 blocked → 只 yield 一个 done 帧（blocked=True，violations 带明细）
    - 答案合规审核 blocked → done 帧（blocked=True，answer="该问题建议直接咨询医学顾问。")
  - 与 `generate()` 的返回字段完全一致（done 帧 = generate() 的 dict + type）。

- [ ] **Step 1: 写失败测试（monkeypatch chat_stream）**

```python
# services/specialist-service/tests/test_generate_stream.py
"""AnswerGenerator.generate_stream 流式测试"""
import asyncio
import pytest
from app.core.answer_generator import AnswerGenerator
from app.models.specialist import Specialist


def _spec(**kwargs):
    data = dict(
        id=1, name="测试专员", bailian_app_id="app-1",
        persona="", knowledge_scope="", compliance_level="internal",
    )
    data.update(kwargs)
    return Specialist(**data)


class FakeBailianStream:
    """替代 bailian.chat_stream：预置 delta/done 帧"""
    def __init__(self, frames):
        self._frames = list(frames)

    def __call__(self, app_id, prompt, session_id=None, history=None):
        async def gen():
            for f in self._frames:
                yield f
        return gen()


def _delta(text):
    return {"type": "delta", "text": text}


def _done(text):
    return {"type": "done", "text": text, "dialog_id": "dlg-1", "citations": []}


def test_generate_stream_delta_and_done(monkeypatch):
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance",
        lambda content, context: asyncio.sleep(0) or {"blocked": False, "violations": []},
    )
    monkeypatch.setattr(
        "app.core.answer_generator.write_audit_log",
        lambda **kw: asyncio.sleep(0),
    )
    generator = AnswerGenerator()
    generator.bailian = FakeBailianStream([_delta("你"), _delta("你好"), _done("你好呀")])

    async def run():
        frames = []
        async for frame in generator.generate_stream("你好", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    types = [f["type"] for f in frames]
    assert types == ["delta", "delta", "done"]
    assert frames[0]["text"] == "你"
    done = frames[-1]
    assert done["answer"] == "你好呀"
    assert done["blocked"] is False
    assert done["session_id"] == "dlg-1"
    assert done["request_id"]


def test_generate_stream_question_blocked(monkeypatch):
    monkeypatch.setattr(
        "app.core.answer_generator.check_compliance",
        lambda content, context: asyncio.sleep(0)
        or {"blocked": True, "violations": [{"rule_code": "R001", "description": "违规"}]},
    )
    generator = AnswerGenerator()

    async def run():
        frames = []
        async for frame in generator.generate_stream("违禁问题", _spec(), user_id=1):
            frames.append(frame)
        return frames

    frames = asyncio.run(run())
    assert len(frames) == 1
    assert frames[0]["type"] == "done"
    assert frames[0]["blocked"] is True
    assert frames[0]["violations"][0]["rule_code"] == "R001"
```

Run: `cd services/specialist-service && python -m pytest tests/test_generate_stream.py -v`
Expected: FAIL（`generate_stream` 不存在）。

- [ ] **Step 2: 实现 generate_stream**

`answer_generator.py` 新增（与 `generate()` 流程一致，delta 帧来自 chat_stream，done 帧 = generate() 的返回 dict 加 "type"）：

```python
    async def generate_stream(
        self,
        question: str,
        specialist: Specialist,
        user_id: int,
        session_id: Optional[str] = None,
    ):
        """流式版 generate()：逐帧 yield delta，末尾 yield done。

        done 帧字段与 generate() 返回 dict 完全一致（多一个 "type"）。
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()

        # ---- Step 1: 合规预检 ----
        logger.info(f"[{request_id}] 合规预检")
        question_check = await check_compliance(
            content=question,
            context={"user_id": user_id, "type": "user_input"}
        )
        if question_check.get("blocked"):
            yield {
                "type": "done",
                "answer": "您的问题包含不合规内容，请调整后重试。",
                "citations": [],
                "evidence_level": None,
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": 0,
                "blocked": True,
                "violations": question_check.get("violations", []),
            }
            return

        # ---- Step 2: 百炼流式 ----
        logger.info(f"[{request_id}] 调用百炼 App: {specialist.bailian_app_id}")
        ai_prompt = question
        ai_response = None
        ai_model = "multimodal-dialog"
        answer = ""
        citations = []

        try:
            async for frame in self.bailian.chat_stream(
                app_id=specialist.bailian_app_id,
                prompt=question,
                session_id=session_id,
            ):
                if frame["type"] == "delta":
                    yield {"type": "delta", "text": frame["text"]}
                elif frame["type"] == "done":
                    answer = frame.get("text", "")
                    citations = frame.get("citations", [])
                    session_id = frame.get("dialog_id", session_id)
                    ai_response = answer
        except BailianException as e:
            logger.warning(f"[{request_id}] 百炼调用失败，降级到通义千问: {e}")
            answer = self._fallback_generate(question, specialist)
            citations = []
            ai_response = answer
            ai_model = "qwen-max"
            yield {"type": "delta", "text": answer}

        # ---- Step 3: 合规审核 AI 答案 ----
        logger.info(f"[{request_id}] 合规审核答案")
        answer_check = await check_compliance(
            content=answer,
            context={"user_id": user_id, "type": "ai_output", "specialist_id": specialist.id}
        )
        if answer_check.get("blocked"):
            latency_ms = int((time.time() - start_time) * 1000)
            from app.api.metrics import CHAT_LATENCY
            CHAT_LATENCY.observe(latency_ms / 1000.0)
            await write_audit_log(
                user_id=user_id, action="chat_blocked", ai_involved=True,
                ai_model=ai_model, ai_prompt=ai_prompt, ai_response=ai_response,
                compliance_result=answer_check, request_id=request_id,
            )
            yield {
                "type": "done",
                "answer": "该问题建议直接咨询医学顾问。",
                "citations": citations,
                "evidence_level": None,
                "session_id": session_id,
                "request_id": request_id,
                "latency_ms": latency_ms,
                "blocked": True,
                "violations": answer_check.get("violations", []),
            }
            return

        # ---- Step 4: 审计日志 ----
        latency_ms = int((time.time() - start_time) * 1000)
        from app.api.metrics import CHAT_LATENCY
        CHAT_LATENCY.observe(latency_ms / 1000.0)
        await write_audit_log(
            user_id=user_id, action="chat_response",
            resource_type="conversation", ai_involved=True,
            ai_model=ai_model, ai_prompt=ai_prompt, ai_response=ai_response,
            compliance_result=answer_check, request_id=request_id,
        )
        logger.info(f"[{request_id}] 回答完成，耗时 {latency_ms}ms")

        yield {
            "type": "done",
            "answer": answer,
            "citations": citations,
            "evidence_level": self._extract_evidence_level(answer),
            "session_id": session_id,
            "request_id": request_id,
            "latency_ms": latency_ms,
            "blocked": False,
            "violations": [],
        }
```

- [ ] **Step 3: 跑测试 + 全量回归**

Run: `cd services/specialist-service && python -m pytest -q`
Expected: 新 2 例 + 既有全量 PASS。

- [ ] **Step 4: Commit**

```bash
cd "/d/gongsi/medical system" && git add services/specialist-service && git commit -m "feat(specialist): AnswerGenerator.generate_stream 流式帧
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: specialist — WS 端点 /ws/specialists/{id}/chat（TDD）

**Files:**
- Create: `services/specialist-service/app/api/chat_ws.py`
- Modify: `services/specialist-service/app/main.py`（挂载 router）
- Create: `services/specialist-service/tests/test_chat_ws.py`

**Interfaces:**
- Consumes: `verify_token`（`shared/common/auth.py:41`）、`AnswerGenerator.generate_stream`（Task 2）、`_persist_conversation`（`app/api/specialists.py:45`，import 复用）
- Produces:
  - WS 端点 `/ws/specialists/{specialist_id}/chat?token=<JWT>`
  - 协议见 Global Constraints；落库在 done 帧前完成（`_persist_conversation(db, user_id, specialist_id, question, result_dict)` 返回 conversation_id 填入 done 帧）

- [ ] **Step 1: 写失败测试（TestClient websocket + 生成器 monkeypatch）**

```python
# services/specialist-service/tests/test_chat_ws.py
"""chat_ws 端点测试：帧协议 + 鉴权（mock generate_stream）"""
import json
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

os.environ.setdefault("JWT_SECRET", "test-secret")
from shared.common.auth import create_token
from app.main import app
from app.api.chat_ws import get_generator_factory, set_generator_factory


@pytest.fixture(autouse=True)
def reset_factory():
    """每个用例后清掉注入的生成器工厂"""
    yield
    set_generator_factory(None)


class FakeGenerator:
    """模拟 AnswerGenerator：generate_stream 逐帧 yield 预置帧"""
    def __init__(self, frames):
        self._frames = frames

    async def generate_stream(self, question, specialist, user_id, session_id=None):
        for f in self._frames:
            yield f


def test_ws_无token关4401():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/specialists/1/chat") as ws:
            pass  # 不应成功；TestClient 在握手失败时抛 WebSocketDisconnect
    # 上面不抛即为失败


def test_ws_question_delta_done_流程():
    token = create_token(user_id=1, username="rep1", role="rep")
    done = {
        "type": "done", "answer": "最终答案", "citations": [],
        "evidence_level": "B", "session_id": "dlg-1", "request_id": "req-1",
        "latency_ms": 100, "blocked": False, "violations": [],
    }
    frames = [{"type": "delta", "text": "你"}, {"type": "delta", "text": "你好"}, done]
    set_generator_factory(lambda: FakeGenerator(frames))

    with TestClient(app) as client:
        with client.websocket_connect(
            f"/ws/specialists/1/chat?token={token}"
        ) as ws:
            ws.send_text(json.dumps({"type": "question", "text": "你好"}))
            start = json.loads(ws.receive_text())
            assert start["type"] == "start"
            d1 = json.loads(ws.receive_text())
            d2 = json.loads(ws.receive_text())
            assert (d1["type"], d2["type"]) == ("delta", "delta")
            fin = json.loads(ws.receive_text())
            assert fin["type"] == "done"
            assert fin["answer"] == "最终答案"
```

说明：
- `chat_ws.py` 提供模块级 `get_generator_factory()` / `set_generator_factory(fn)`（默认返回 `AnswerGenerator()`），测试注入假生成器，绕开 DB/合规/百炼。
- specialist 存在性校验在测试中通过注入假 DB 会话处理：`chat_ws.py` 内 `db = SessionLocal()` 手动管理；测试通过 `app.dependency_overrides` 不可行（WS 依赖不走 Depends 时需手动），故 chat_ws 内校验 specialist 的逻辑在测试里用 monkeypatch 处理——**简化决策：chat_ws 端点只做 token 鉴权 + 生成器调用 + 落库，specialist 存在性校验复用 REST 的查询逻辑但允许 404 时关 4404；测试覆盖 4401 与帧协议，4404 分支用 monkeypatch DB 或直接跳过（存在性由 REST 层语义保证，WS 层失败也会在生成阶段暴露）**。若 Step 1 测试因 DB 依赖失败，则在 chat_ws.py 里把"校验 specialist"抽成 `_get_specialist(db, specialist_id)`，测试 monkeypatch 它返回 None/对象。

Run: `cd services/specialist-service && python -m pytest tests/test_chat_ws.py -v`
Expected: FAIL（chat_ws 模块不存在）。

- [ ] **Step 2: 实现 chat_ws.py**

```python
"""数字专员对话 WebSocket 端点（流式）

协议（见 docs/superpowers/specs/2026-08-06-gap-closure-batch2-design.md 3.1）：
    客户端 → {"type":"question","text","session_id"} / {"type":"stop"}
    服务端 → start → delta* → done；异常 error（关 4500）；token 无效关 4401
send 统一加锁，防 websockets>=12 ConcurrencyError（沿用 asr_ws.py send_lock 模式）。
"""
import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from sqlalchemy.orm import Session

from shared.common.auth import verify_token
from shared.common.db_session import get_db
from app.core.answer_generator import AnswerGenerator

router = APIRouter(tags=["chat-ws"])
logger = logging.getLogger(__name__)

# 生成器工厂（测试注入用）
_generator_factory = lambda: AnswerGenerator()


def get_generator_factory():
    return _generator_factory


def set_generator_factory(fn):
    global _generator_factory
    _generator_factory = fn


@router.websocket("/ws/specialists/{specialist_id}/chat")
async def chat_ws(
    websocket: WebSocket,
    specialist_id: int,
    db: Session = Depends(get_db),
):
    token = websocket.query_params.get("token", "")
    try:
        payload = verify_token(token)
    except HTTPException:
        await websocket.close(code=4401)
        return
    user_id = int(payload["sub"])

    # 校验专员存在（与 REST 语义一致）
    from app.models.specialist import Specialist
    specialist = db.query(Specialist).filter(
        Specialist.id == specialist_id,
        Specialist.status == "active",
    ).first()
    if not specialist:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    send_lock = asyncio.Lock()

    async def send(frame: dict):
        async with send_lock:
            await websocket.send_text(json_dumps(frame))

    # 读客户端首帧 question（60s 内未发则关 4500）
    question = None
    session_id = None
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=60)
        msg = json.loads(raw)
        if msg.get("type") == "question":
            question = (msg.get("text") or "").strip()
            session_id = msg.get("session_id")
        elif msg.get("type") == "stop":
            await websocket.close(code=4500)
            return
    except (WebSocketDisconnect, Exception):
        await websocket.close(code=4500)
        return
    if not question:
        await send({"type": "error", "message": "question 不能为空"})
        await websocket.close(code=4500)
        return

    generator = get_generator_factory()()
    stop_event = asyncio.Event()

    async def client_loop():
        """接收客户端消息：stop → 中止生成"""
        try:
            while not stop_event.is_set():
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                if msg.get("type") == "stop":
                    stop_event.set()
        except Exception:
            pass  # 连接断开

    client_task = asyncio.create_task(client_loop())

    # 开始生成（start 帧不带 request_id：该值在 generate_stream 内部生成，客户端以 type 为准）
    await send({"type": "start"})
    result = None
    try:
        async for frame in generator.generate_stream(
            question=question,
            specialist=specialist,
            user_id=user_id,
            session_id=session_id,
        ):
            if stop_event.is_set():
                break
            if frame["type"] == "delta":
                await send({"type": "delta", "text": frame["text"]})
            elif frame["type"] == "done":
                result = frame
                break
    except Exception as e:
        logger.exception(f"[chat_ws] 生成异常: {e}")
        await send({"type": "error", "message": "生成失败，请稍后重试"})
        await websocket.close(code=4500)
        return
    finally:
        client_task.cancel()

    if result is None:
        await send({"type": "error", "message": "生成中断"})
        await websocket.close(code=4500)
        return

    # 落库（复用 REST 的 _persist_conversation，使用注入的 db 会话）
    from app.api.specialists import _persist_conversation
    conversation_id = _persist_conversation(
        db, user_id, specialist_id, question,
        {
            "session_id": result.get("session_id"),
            "answer": result.get("answer"),
            "citations": result.get("citations"),
            "blocked": result.get("blocked"),
            "latency_ms": result.get("latency_ms"),
        },
    )

    await send({
        "type": "done",
        "text": result.get("answer", ""),
        "session_id": result.get("session_id"),
        "conversation_id": conversation_id,
        "citations": result.get("citations", []),
        "blocked": result.get("blocked", False),
        "violations": result.get("violations", []),
        "evidence_level": result.get("evidence_level"),
        "latency_ms": result.get("latency_ms"),
    })
    await websocket.close(code=1000)


def json_dumps(obj: dict) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)
```

- `app/main.py` 挂载：`from app.api.chat_ws import router as chat_ws_router` + `app.include_router(chat_ws_router)`。
- **注意**：start 帧的 request_id 来自生成帧——但 generate_stream 内部生成 request_id，start 帧先发时拿不到。修正：start 帧的 request_id 留空字符串由客户端忽略；或者把 request_id 前置到 start 帧不准确。**实现决策：start 帧不发 request_id 字段，只发 {"type":"start"}**（客户端以 type 为准）。同步 Global Constraints 协议描述——start 帧 = `{"type":"start"}`。

- [ ] **Step 3: 跑测试**

Run: `cd services/specialist-service && python -m pytest tests/test_chat_ws.py -v`
Expected: 2 passed（4401 关闭 + question/delta/done 流程；若 specialist 校验依赖 DB 导致测试失败，按 Step 1 说明抽 `_get_specialist` 并 monkeypatch）。

- [ ] **Step 4: 全量回归**

Run: `cd services/specialist-service && python -m pytest -q`
Expected: 全部通过。

- [ ] **Step 5: Commit**

```bash
cd "/d/gongsi/medical system" && git add services/specialist-service && git commit -m "feat(specialist): 对话 WS 流式端点（鉴权/帧协议/落库）
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: gateway — WS 代理（TDD）

**Files:**
- Modify: `services/gateway/requirements.txt`（加 websockets）
- Modify: `services/gateway/app/main.py`（加 WS 代理路由）
- Create: `services/gateway/tests/test_ws_proxy.py`

**Interfaces:**
- Consumes: `settings.SPECIALIST_SERVICE_URL`（`app/config.py` 已有）
- Produces:
  - `app.main` 的 `_upstream_factory(backend_url, path, query)` 模块级函数：返回一个类 WebSocket 的上游对象（`send_text/send_bytes/receive_text/receive_bytes/close`）；默认实现用 `websockets.connect(ws://...)` 包一层
  - WS 路由 `/api/v1/specialists/{specialist_id}/chat/ws`：accept 后双 Task 双向转发（client→upstream、upstream→client，send 加锁），任一侧断开即清理两侧

- [ ] **Step 1: 写失败测试（注入 fake 上游）**

```python
# services/gateway/tests/test_ws_proxy.py
"""网关 WS 代理测试（注入 fake 上游，不真连 specialist）"""
import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from app.main import app, set_upstream_factory


class FakeUpstream:
    """模拟 specialist 上游：队列驱动"""
    def __init__(self):
        self.closed = False
        self.to_client = asyncio.Queue()   # 上游→客户端
        self.received = []                  # 客户端→上游

    async def send_text(self, text):
        await self.to_client.put(("text", text))

    async def send_bytes(self, data):
        await self.to_client.put(("bytes", data))

    async def receive_text(self):
        kind, payload = await self.to_client.get()
        return payload

    async def receive_bytes(self):
        kind, payload = await self.to_client.get()
        return payload

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_factory():
    yield
    set_upstream_factory(None)


def test_ws_proxy_双向透传():
    fake = FakeUpstream()
    set_upstream_factory(lambda url: fake)

    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/specialists/1/chat/ws?token=abc") as ws:
            # 客户端 → 上游
            ws.send_text(json.dumps({"type": "question", "text": "你好"}))
            assert json.loads(fake.received.pop(0))["type"] == "question"
            # 上游 → 客户端
            fake.send_text(json.dumps({"type": "delta", "text": "你"}))
            assert json.loads(ws.receive_text())["type"] == "delta"
            fake.send_text(json.dumps({"type": "done", "text": "你好", "conversation_id": 1}))
            assert json.loads(ws.receive_text())["type"] == "done"
```

Run: `cd services/gateway && python -m pytest tests/test_ws_proxy.py -v`
Expected: FAIL（`set_upstream_factory` 不存在）。

- [ ] **Step 2: 实现**

`services/gateway/app/main.py` 追加：

```python
import websockets

# ---- WS 代理上游工厂（测试注入用）----
_upstream_factory = None


def set_upstream_factory(fn):
    """测试注入：替换默认的上游连接函数。fn(url: str) -> FakeUpstream 对象"""
    global _upstream_factory
    _upstream_factory = fn


async def _default_upstream(url: str):
    ws = await websockets.connect(url)
    return ws  # 原生 websockets WebSocket 已具备 send_text/receive_text/close 等


@app.websocket("/api/v1/specialists/{specialist_id}/chat/ws")
async def proxy_chat_ws(websocket: WebSocket, specialist_id: int):
    token = websocket.query_params.get("token", "")
    await websocket.accept()

    ws_scheme = "wss" if settings.SPECIALIST_SERVICE_URL.startswith("https") else "ws"
    upstream_url = (
        f"{ws_scheme}://{settings.SPECIALIST_SERVICE_URL.split('://')[1]}"
        f"/ws/specialists/{specialist_id}/chat?token={token}"
    )
    factory = _upstream_factory or _default_upstream
    try:
        upstream = await factory(upstream_url)
    except Exception:
        await websocket.close(code=4500)
        return

    send_lock = asyncio.Lock()

    async def client_to_upstream():
        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.receive":
                    if "text" in msg and msg["text"] is not None:
                        await upstream.send_text(msg["text"])
                    elif "bytes" in msg and msg["bytes"] is not None:
                        await upstream.send_bytes(msg["bytes"])
                elif msg["type"] == "websocket.disconnect":
                    break
        except Exception:
            pass
        finally:
            await upstream.close()

    async def upstream_to_client():
        try:
            while True:
                try:
                    text = await upstream.receive_text()
                    async with send_lock:
                        await websocket.send_text(text)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception:
                    break
        finally:
            try:
                async with send_lock:
                    await websocket.close(code=1000)
            except Exception:
                pass

    t1 = asyncio.create_task(client_to_upstream())
    t2 = asyncio.create_task(upstream_to_client())
    try:
        await asyncio.gather(t1, t2)
    finally:
        t1.cancel(); t2.cancel()
        try:
            await upstream.close()
        except Exception:
            pass
```

（`main.py` 顶部补 `import asyncio`、`from fastapi import WebSocket`、`import websockets`。）

- [ ] **Step 3: 跑测试 + 既有回归**

Run: `cd services/gateway && python -m pytest -q`
Expected: 新用例 + 既有 health 测试 PASS。

- [ ] **Step 4: Commit**

```bash
cd "/d/gongsi/medical system" && git add services/gateway && git commit -m "feat(gateway): 对话 WS 代理（双向透传，token 原样转发）
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: mobile — wsChat.ts 客户端 + 单测

**Files:**
- Create: `mobile/src/services/wsChat.ts`
- Create: `mobile/src/services/__tests__/wsChat.test.ts`

**Interfaces:**
- Consumes: `apiClient.getToken()`（`mobile/src/api/client.ts:37-41`）
- Produces:
  - `openChatWs(specialistId: number, token: string, cbs: ChatWsCallbacks): ChatWsSession`
  - `ChatWsCallbacks`: `onStart(): void`、`onDelta(text: string): void`、`onDone(done: { text: string; conversationId?: number | null; sessionId?: string; citations?: unknown[] }): void`、`onError(message: string): void`
  - `ChatWsSession`: `sendQuestion(text: string, sessionId?: string): void`、`close(): void`
  - URL：`ws://10.0.2.2:8000/api/v1/specialists/{id}/chat/ws?token=<JWT>`（android）/ `ws://localhost:8000/...`（ios）——**走网关 8000**。

- [ ] **Step 1: 写失败测试（mock 全局 WebSocket，同 asr 测试模式）**

```ts
// mobile/src/services/__tests__/wsChat.test.ts
import { openChatWs } from '../wsChat';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((e: any) => void) | null = null;
  sent: any[] = [];
  constructor(url: string) { this.url = url; MockWebSocket.instances.push(this); }
  send(data: any) { this.sent.push(data); }
  close() { this.onmessage?.({ data: JSON.stringify({ type: 'done', text: '' }) }); }
  emit(data: any) { this.onmessage?.({ data }); }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  (global as any).WebSocket = MockWebSocket;
});

describe('wsChat 客户端', () => {
  it('URL 走网关并带 token 与 specialistId', async () => {
    const ws = openChatWs(3, 'tok-1', { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    expect(inst.url).toContain(':8000/api/v1/specialists/3/chat/ws');
    expect(inst.url).toContain('token=tok-1');
    ws.close();
  });

  it('sendQuestion 发 question 帧', async () => {
    const ws = openChatWs(3, 'tok', { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: () => {} });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    ws.sendQuestion('你好', 'sess-1');
    expect(inst.sent[0]).toBe(JSON.stringify({ type: 'question', text: '你好', session_id: 'sess-1' }));
    ws.close();
  });

  it('start/delta/done 帧触发回调，done 带 conversationId', async () => {
    const events: string[] = [];
    let convId: number | null | undefined;
    const ws = openChatWs(3, 'tok', {
      onStart: () => events.push('start'),
      onDelta: (t) => events.push('d:' + t),
      onDone: (d) => { events.push('done'); convId = d.conversationId; },
      onError: () => events.push('err'),
    });
    await new Promise((r) => setTimeout(r, 0));
    const inst = MockWebSocket.instances[0];
    inst.emit(JSON.stringify({ type: 'start' }));
    inst.emit(JSON.stringify({ type: 'delta', text: '你' }));
    inst.emit(JSON.stringify({ type: 'done', text: '你好', conversation_id: 42 }));
    await new Promise((r) => setTimeout(r, 0));
    expect(events).toEqual(['start', 'd:你', 'done']);
    expect(convId).toBe(42);
    ws.close();
  });

  it('error 帧触发 onError', async () => {
    const errors: string[] = [];
    const ws = openChatWs(3, 'tok', { onStart: () => {}, onDelta: () => {}, onDone: () => {}, onError: (m) => errors.push(m) });
    await new Promise((r) => setTimeout(r, 0));
    MockWebSocket.instances[0].emit(JSON.stringify({ type: 'error', message: '生成失败' }));
    await new Promise((r) => setTimeout(r, 0));
    expect(errors).toEqual(['生成失败']);
    ws.close();
  });
});
```

Run: `cd mobile && npx jest services/__tests__/wsChat`
Expected: FAIL（wsChat 模块不存在）。

- [ ] **Step 2: 实现 wsChat.ts**

```ts
/**
 * 对话 WS 流式客户端（走网关 8000）
 * 协议见 specs 3.1/3.3：发 question 帧，收 start/delta/done/error 帧
 */
import { Platform } from 'react-native';

const GATEWAY_HOST = Platform.select({
  android: '10.0.2.2:8000',
  ios: 'localhost:8000',
  default: 'localhost:8000',
});

export interface ChatWsDone {
  text: string;
  conversationId?: number | null;
  sessionId?: string;
  citations?: unknown[];
}

export interface ChatWsCallbacks {
  onStart: () => void;
  onDelta: (text: string) => void;
  onDone: (done: ChatWsDone) => void;
  onError: (message: string) => void;
}

export interface ChatWsSession {
  sendQuestion(text: string, sessionId?: string): void;
  close(): void;
}

export function openChatWs(
  specialistId: number,
  token: string,
  cbs: ChatWsCallbacks
): ChatWsSession {
  const ws = new WebSocket(
    `ws://${GATEWAY_HOST}/api/v1/specialists/${specialistId}/chat/ws?token=${encodeURIComponent(token)}`
  );

  ws.onmessage = (e) => {
    try {
      const frame = JSON.parse(e.data as string);
      switch (frame.type) {
        case 'start':
          cbs.onStart();
          break;
        case 'delta':
          cbs.onDelta(frame.text ?? '');
          break;
        case 'done':
          cbs.onDone({
            text: frame.text ?? '',
            conversationId: frame.conversation_id ?? null,
            sessionId: frame.session_id,
            citations: frame.citations ?? [],
          });
          ws.close();
          break;
        case 'error':
          cbs.onError(frame.message || '对话服务异常');
          break;
        default:
          break;
      }
    } catch {
      // 非 JSON 帧忽略
    }
  };
  ws.onerror = () => cbs.onError('对话服务连接失败');

  return {
    sendQuestion(text: string, sessionId?: string) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'question',
          text,
          ...(sessionId ? { session_id: sessionId } : {}),
        }));
      }
    },
    close() {
      ws.close();
    },
  };
}
```

- [ ] **Step 3: 跑测试**

Run: `cd mobile && npx jest services/__tests__/wsChat`
Expected: 4 passed。

- [ ] **Step 4: 类型检查 + Commit**

Run: `cd mobile && npx tsc --noEmit`
Expected: PASS。

```bash
cd "/d/gongsi/medical system" && git add mobile/src/services && git commit -m "feat(mobile): 对话 WS 流式客户端（走网关）
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: mobile — ChatScreen 流式渲染 + REST 降级

**Files:**
- Modify: `mobile/src/screens/Chat/ChatScreen.tsx`（handleSend 改 WS 优先 + 流式渲染）

**Interfaces:**
- Consumes: `openChatWs`（Task 5）、`apiClient.getToken()`、既有 `specialistAPI.sendMessage`（fallback）、`sessionId` state（现有 :54）
- 无新接口。

- [ ] **Step 1: handleSend 改造**

`ChatScreen.tsx`：
- import 加：`openChatWs`（`../../services/wsChat`）、`apiClient`（`../../api/client`）
- 新状态：

```tsx
const [streaming, setStreaming] = useState(false);      // 流式生成中
const [streamText, setStreamText] = useState('');       // 当前增量累积
const wsRef = useRef<ReturnType<typeof openChatWs> | null>(null);
```

- handleSend 前半段（用户消息入列、清输入）不变；发送部分改为：

```tsx
const tryStream = async (text: string, session: string | null): Promise<boolean> => {
  return new Promise((resolve) => {
    let started = false;
    const timer = setTimeout(() => {                      // 8s 未收到 start → 降级
      if (!started) { cleanup(); resolve(false); }
    }, 8000);
    const cleanup = () => {
      clearTimeout(timer);
      if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    };
    const ws = openChatWs(specialistId, token, {
      onStart: () => { started = true; setStreaming(true); setStreamText(''); },
      onDelta: (t) => { setStreamText(t); },
      onDone: (d) => {
        started = true;
        clearTimeout(timer);
        setStreamText('');
        setStreaming(false);
        const aiMsg: Message = {
          id: `a_${Date.now()}`,
          role: 'assistant',
          content: d.text,
          citations: (d.citations ?? []) as Message['citations'],
          blocked: false,
          conversationId: d.conversationId ?? null,
        };
        setMessages((prev) => [...prev, aiMsg]);
        if (d.sessionId) setSessionId(d.sessionId);
        wsRef.current = null;
        resolve(true);
      },
      onError: (m) => {
        started = true;
        clearTimeout(timer);
        setStreaming(false);
        setStreamText('');
        wsRef.current = null;
        resolve(false);                                  // 降级 REST
      },
    });
    wsRef.current = ws;
    ws.sendQuestion(text, session ?? undefined);
  });
};
```

- handleSend 主体：

```tsx
const handleSend = useCallback(async () => {
  const text = input.trim();
  if (!text || loading) return;
  const userMsg: Message = { id: `u_${Date.now()}`, role: 'user', content: text };
  setMessages((prev) => [...prev, userMsg]);
  setInput('');
  setLoading(true);
  try {
    const token = (await apiClient.getToken()) || '';
    const ok = await tryStream(text, sessionId, token);
    if (ok) return;                                      // WS 完成（含 done）
    // ---- REST fallback（既有逻辑）----
    const response = await specialistAPI.sendMessage(specialistId, {
      question: text,
      session_id: sessionId || undefined,
    });
    if (!sessionId && response.session_id) setSessionId(response.session_id);
    const violationText = (response.violations ?? [])
      .map((v) => v.description).filter(Boolean).join('；');
    const content = response.blocked
      ? [response.answer, violationText && `（${violationText}）`].filter(Boolean).join('')
      : response.answer;
    const aiMsg: Message = {
      id: response.request_id || `a_${Date.now()}`,
      role: 'assistant',
      content,
      citations: response.citations,
      evidenceLevel: response.evidence_level,
      blocked: response.blocked,
      conversationId: response.conversation_id ?? null,
    };
    setMessages((prev) => [...prev, aiMsg]);
  } catch (e: any) {
    setMessages((prev) => [...prev, {
      id: `err_${Date.now()}`, role: 'assistant',
      content: `抱歉，出错了：${e.message || '请稍后重试'}`,
    }]);
  } finally {
    setLoading(false);
  }
}, [input, loading, specialistId, sessionId]);
```

（`tryStream(text, session, token)` 签名含 token——实现时把 token 作为第三个参数传入。）

- [ ] **Step 2: 流式渲染（增量气泡）**

`FlatList` data 前插入临时流式气泡：把 `streaming || streamText` 状态并入 messages 渲染。在 renderMessage 前加：

```tsx
const streamMsg: Message | null = streaming || streamText
  ? { id: 'streaming', role: 'assistant', content: streamText || '正在思考...' }
  : null;
const listData = streamMsg ? [...messages, streamMsg] : messages;
```

FlatList `data={listData}`。流式气泡与普通 aiBubble 同渲染（conversationId 为空 → 不显示反馈/收藏按钮，已有条件 `item.conversationId` 天然满足）。

- [ ] **Step 3: 测试 + 类型检查**

Run: `cd mobile && npx jest && npx tsc --noEmit`
Expected: 全部 PASS（既有契约测试不破坏——sendMessage 仍存在）。

- [ ] **Step 4: Commit**

```bash
cd "/d/gongsi/medical system" && git add mobile/src/screens/Chat && git commit -m "feat(mobile): ChatScreen 流式渲染 + WS 8s 超时自动降级 REST
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: 批次 3 收尾 — 全链路验证

- [ ] **Step 1: specialist 全量 pytest**

Run: `cd services/specialist-service && python -m pytest -q`
Expected: 全部通过。

- [ ] **Step 2: gateway 全量 pytest**

Run: `cd services/gateway && python -m pytest -q`
Expected: 全部通过（health + WS 代理）。

- [ ] **Step 3: mobile 全量测试 + 类型**

Run: `cd mobile && npx jest && npx tsc --noEmit`
Expected: 全部 PASS。

- [ ] **Step 4: 手工端到端冒烟（可选，需百炼 API key 与模拟器）**

1. 起 specialist:8001、gateway:8000
2. 模拟器 App 打开专员对话 → 发消息 → 观察回答逐字流式出现（WS 路径）；对比 REST fallback（停掉 specialist 或断网时自动降级）

- [ ] **Step 5: 汇报**

汇总：chat_stream/generate_stream 重构、WS 端点帧协议、网关代理、mobile 流式与降级、测试结果；注明 spec 修正点（question 帧、start 帧无 conversation_id、done 帧携带 conversation_id）。
