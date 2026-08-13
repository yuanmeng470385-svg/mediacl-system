"""拜访流程管理器 — 陪访助手核心编排

流程：
  拜访前  prepare_visit    → 医生画像+历史 → 调 A 生成准备包
  拜访中  start_visit      → 创建拜访记录
          process_transcript → 听悟转写 + 合规实时检查 + 异议识别
  拜访后  end_visit        → 调 A 生成结构化记录 → 审计日志
          follow_up        → 调 A 生成跟进建议

降级策略（"遇到阻塞先 mock，不等"）：
  - A 不可用/未配置专员 → 返回 degraded 结果，不阻塞拜访流程
  - D 不可用 → 合规检查放行（客户端 fail-open）
  - 听悟不可用 → process_transcript 报错并给出明确提示，可改用 text 直传
"""
import json
import os
import asyncio
import logging
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

from shared.common.response import ParamError, BusinessError

from app.models.visit_record import VisitRecord
from app.db.repositories.visit_repo import VisitRepo
from app.services.tingwu_client import TingwuClient
from app.services.compliance_client import check_compliance
from app.services.specialist_client import chat_with_specialist
from app.services.audit_client import write_audit_log
from app.core.objection_detector import ObjectionDetector
from app.services.qwen_client import QwenClient
from app.constants import (
    AI_SUMMARY_PLACEHOLDER,
    AI_SUMMARY_BLOCKED,
    VISIT_STATUS_CANCELLED,
    VISIT_STATUS_COMPLETED,
    VISIT_STATUS_IN_PROGRESS,
)

logger = logging.getLogger(__name__)

# 占位串 / 拦截话术定义在 app.constants（visit_record/visit_repo 共用），
# 此处直接 import 使 visit_manager.AI_SUMMARY_PLACEHOLDER 兼容旧调用路径

# 同库直读 hcps / digital_specialists（数据属于 hcp-service / specialist-service，此处只读）
_HCP_SQL = text("""
    SELECT id, name, hospital, department, title, specialty, region, tags
    FROM hcps WHERE id = :hcp_id
""")
_SPECIALIST_SQL = text("""
    SELECT id, name FROM digital_specialists
    WHERE product_id = :product_id AND status = 'active'
    ORDER BY id LIMIT 1
""")
_HISTORY_SQL = text("""
    SELECT visit_time, sentiment, key_points, hcp_interests, hcp_objections, ai_summary
    FROM visit_records
    WHERE hcp_id = :hcp_id AND user_id = :user_id AND ai_summary IS NOT NULL
    ORDER BY visit_time DESC LIMIT :limit
""")

# 异议类型的应对话术建议（规则层兜底，引用材料由代表按产品补充）
_OBJECTION_RESPONSES = {
    "price": "回应价格异议：引用产品经济性数据与医保政策，避免直接比较竞品价格",
    "efficacy": "回应疗效异议：引用 III 期临床研究数据与真实世界证据",
    "safety": "回应安全性异议：引用说明书不良反应数据，告知已知风险与监测建议",
    "competition": "回应竞品对比：客观呈现本产品证据，不贬低竞品（合规红线）",
    "deferral": "回应拖延：留下资料与摘要，预约下次拜访时间",
    "other": "先倾听完整诉求，记录后由医学顾问跟进",
}


def _parse_json_content(content: str) -> Optional[dict]:
    """解析模型输出的 JSON（兼容 ```json 包裹），失败返回 None"""
    if not content:
        return None
    text_content = content.strip()
    if text_content.startswith("```"):
        text_content = text_content.strip("`")
        if text_content.startswith("json"):
            text_content = text_content[4:]
    try:
        result = json.loads(text_content)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


from app.db.repositories.task_repo import TaskRepo, CHANNEL_TYPE_MAP, infer_channel


def _parse_follow_up_items(items: list, visit_id: int, user_id: int) -> list:
    """把 AI 返回的 follow_up_items 归一化为 tasks 行数据（坏格式跳过）"""
    parsed = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = (item.get("action") or "").strip()
        if not action:
            continue
        due_raw = (item.get("due") or "").strip()
        try:
            due_date = date.fromisoformat(due_raw) if due_raw else None
        except ValueError:
            due_date = None
        channel = (item.get("channel") or "").strip()
        parsed.append({
            "title": action,
            "description": item.get("description"),
            "task_type": CHANNEL_TYPE_MAP.get(channel, "follow_up"),
            "due_date": due_date,
            "channel": channel or None,
        })
    return parsed


def _parse_end_visit_tasks(follow_up: list, next_plan: dict) -> list:
    """把 end_visit 结构化结果（follow_up_suggestions + next_visit_plan）归一化为 tasks 行数据

    形状与 _parse_follow_up_items 一致（title/description/task_type/due_date/channel）：
      - follow_up_suggestions：逐条文本建任务，按动作词推断通道/类型，映射失败仍创建
        （默认类型 follow_up + 原文标题）
      - next_visit_plan.recommended_time：建"预约下次拜访"任务（时间作 due_date）
      - next_visit_plan.materials_to_send：逐条建"发送资料：xxx"任务
    """
    parsed = []
    for suggestion in follow_up or []:
        if not isinstance(suggestion, str):
            continue
        action = suggestion.strip()
        if not action:
            continue
        channel = infer_channel(action)
        parsed.append({
            "title": action,
            "description": None,
            "task_type": CHANNEL_TYPE_MAP.get(channel, "follow_up"),
            "due_date": None,
            "channel": channel,
        })

    plan = next_plan or {}
    if not isinstance(plan, dict):
        plan = {}
    due_raw = str(plan.get("recommended_time") or "").strip()
    due_date = None
    if due_raw:
        try:
            due_date = date.fromisoformat(due_raw)
        except ValueError:
            due_date = None
    topics = plan.get("recommended_topics") or []
    if due_date or topics:
        parsed.append({
            "title": f"预约下次拜访（{due_raw}）" if due_date else "预约下次拜访",
            "description": "；".join(str(t) for t in topics) if topics else None,
            "task_type": "book_appointment",
            "due_date": due_date,
            "channel": "下次拜访",
        })
    for material in plan.get("materials_to_send") or []:
        m = str(material).strip()
        if not m:
            continue
        parsed.append({
            "title": f"发送资料：{m}",
            "description": m,
            "task_type": "send_material",
            "due_date": None,
            "channel": "发送资料",
        })
    return parsed


# pre-visit 推荐内容的固定 schema（空结构：AI 输出不可用时兜底，绝不透传原始文本）
EMPTY_RECOMMENDATIONS = {
    "suggested_topics": [],
    "red_lines": [],
    "opening_remarks": "",
    "materials": [],
    "last_follow_up": "",
}

# 中英文键归一化：canonical 键 ← 各别名（模型可能输出任一语言）
_RECOMMENDATION_KEY_ALIASES = {
    "suggested_topics": ("suggested_topics", "推荐话题", "建议话题", "topics"),
    "red_lines": ("red_lines", "红线提醒", "红线", "合规红线"),
    "opening_remarks": ("opening_remarks", "开场白建议", "开场白"),
    "materials": ("materials", "材料", "所需材料", "资料"),
    "last_follow_up": ("last_follow_up", "上次未完成的跟进项", "上次未完成跟进项", "跟进项"),
}


def _parse_recommendations(content: str) -> dict:
    """解析 pre-visit AI 输出的推荐内容（固定 schema）

    健壮化：剥离 markdown 代码围栏；JSON 解析失败 / 形状不对 → 返回空结构
    （而非把原始文本塞给前端）；兼容中文键与英文键两套命名。
    """
    if not content:
        return dict(EMPTY_RECOMMENDATIONS)
    text_content = content.strip()
    if text_content.startswith("```"):
        text_content = text_content[3:]
        if text_content.endswith("```"):
            text_content = text_content[:-3]
        text_content = text_content.strip()
        if text_content.startswith("json"):
            text_content = text_content[4:].strip()
    try:
        parsed = json.loads(text_content)
    except json.JSONDecodeError:
        return dict(EMPTY_RECOMMENDATIONS)
    if not isinstance(parsed, dict):
        return dict(EMPTY_RECOMMENDATIONS)

    out = dict(EMPTY_RECOMMENDATIONS)
    for canonical, aliases in _RECOMMENDATION_KEY_ALIASES.items():
        value = None
        for alias in aliases:
            if alias in parsed:
                value = parsed[alias]
                break
        if canonical in ("suggested_topics", "red_lines", "materials"):
            if isinstance(value, list):
                out[canonical] = [str(v) for v in value if v]
        elif isinstance(value, str):
            out[canonical] = value
    return out


async def _push_profile_update(hcp_id: int, structured: dict, visit_id: int) -> bool:
    """拜访后画像更新：调 hcp-service 内部接口，失败不阻塞主流程"""
    import httpx
    from shared.common.internal_auth import internal_headers
    gateway_url = os.getenv("GATEWAY_URL", "http://localhost:8000")
    updates = {}
    interests = structured.get("hcp_interests") or []
    if interests:
        updates["academic_background"] = {"research_interest": interests[0][:200]}
        updates["tags"] = [f"兴趣:{i[:30]}" for i in interests[:3]]
    objections = structured.get("hcp_objections") or []
    if objections:
        updates["prescription_preference"] = {"noted_objections": [str(o)[:200] for o in objections[:5]]}
    sentiment = structured.get("sentiment")
    if sentiment:
        # 情绪（positive/neutral/negative）记入画像备注，与 noted_objections 并列；
        # influence_level 语义不同（high/medium/low），画像更新不写入
        pref = updates.setdefault("prescription_preference", {})
        pref["noted_sentiment"] = sentiment
    if not updates:
        return True
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{gateway_url}/api/v1/hcps/profile-update",
                headers=internal_headers(),
                json={"hcp_id": hcp_id, **updates, "source": "ai_visit", "visit_id": visit_id},
            )
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.warning("医生画像更新失败（不影响拜访记录）: hcp_id=%s err=%s", hcp_id, exc)
        return False


class VisitManager:
    """拜访流程管理器"""

    def __init__(
        self,
        tingwu: Optional[TingwuClient] = None,
        detector: Optional[ObjectionDetector] = None,
        qwen: Optional["QwenClient"] = None,
    ):
        self.tingwu = tingwu or TingwuClient()
        self.detector = detector or ObjectionDetector()
        self.qwen = qwen or QwenClient()

    # ==================== 内部查询 ====================

    def _get_hcp(self, db: Session, hcp_id: int) -> Optional[Dict]:
        try:
            row = db.execute(_HCP_SQL, {"hcp_id": hcp_id}).mappings().first()
            return dict(row) if row else None
        except Exception as e:
            logger.warning(f"读取医生档案失败: {e}")
            return None

    def _get_history(self, db: Session, hcp_id: int, user_id: int, limit: int = 3) -> List[Dict]:
        """读取当前用户对该医生的历史拜访（S4：拜访记录仅本人可见）"""
        try:
            rows = db.execute(
                _HISTORY_SQL, {"hcp_id": hcp_id, "user_id": user_id, "limit": limit},
            ).mappings().all()
            history = []
            for r in rows:
                row = dict(r)
                # datetime 不可 JSON 序列化（prompt 里 json.dumps）→ 转 isoformat
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.isoformat()
                history.append(row)
            return history
        except Exception as e:
            logger.warning(f"读取互动历史失败: {e}")
            return []

    def _resolve_specialist(self, db: Session, product_id: int) -> Optional[int]:
        """按产品找对应数字专员（A 侧未配置时返回 None）"""
        try:
            row = db.execute(_SPECIALIST_SQL, {"product_id": product_id}).mappings().first()
            return row["id"] if row else None
        except Exception as e:
            logger.warning(f"查询数字专员失败: {e}")
            return None

    async def _call_specialist(
        self, specialist_id: Optional[int], prompt: str, user_id: int,
        auth_token: Optional[str] = None,
    ) -> Dict:
        """调 A 生成内容；未找到专员或 A 不可用时降级。

        auth_token：当前用户 JWT 原样透传（chat 接口网关要求 JWT，不带则 401 → 永久 degraded）
        """
        if not specialist_id:
            return {"answer": "", "blocked": False, "degraded": True, "error": "未找到该产品的数字专员（需先在 specialist-service 配置）"}
        return await chat_with_specialist(specialist_id, prompt, user_id, auth_token=auth_token)

    # ==================== 拜访前：准备包 ====================

    async def prepare_visit(
        self, db: Session, hcp_id: int, user_id: int, product_id: int,
        auth_token: Optional[str] = None,
    ) -> Dict:
        """生成拜访准备包：医生画像 + 历史互动 → 调 A 生成推荐话题/红线提醒/开场白"""
        hcp = self._get_hcp(db, hcp_id)
        if not hcp:
            raise BusinessError(f"医生档案不存在: hcp_id={hcp_id}")

        history = self._get_history(db, hcp_id, user_id, limit=3)
        prompt = f"""为医药代表准备拜访以下医生的资料：

医生信息：
- 姓名：{hcp.get('name')}
- 医院科室：{hcp.get('hospital')} {hcp.get('department')}
- 职称：{hcp.get('title')}
- 专业方向：{hcp.get('specialty') or '未知'}
- 标签：{hcp.get('tags') or []}

历史互动（最近 {len(history)} 次）：
{json.dumps(history, ensure_ascii=False, indent=2)}

请生成：3-5 个推荐话题、1-2 个红线提醒（合规）、1 段开场白建议、
拜访需带的材料、以及上次未完成的跟进项。

必须严格按以下 JSON schema 输出（只输出 JSON，不要 markdown 代码块，
不要任何额外文字），suggested_topics 保持 3-5 个：
{{
  "suggested_topics": ["话题1", "话题2", "话题3"],
  "red_lines": ["红线提醒1"],
  "opening_remarks": "开场白建议",
  "materials": ["需带材料1"],
  "last_follow_up": "上次未完成的跟进项"
}}"""

        specialist_id = self._resolve_specialist(db, product_id)
        result = await self._call_specialist(specialist_id, prompt, user_id, auth_token=auth_token)

        recommendations = _parse_recommendations(result.get("answer", ""))
        return {
            "hcp_profile": hcp,
            "history": history,
            "recommendations": recommendations,
            "specialist_id": specialist_id,
            "degraded": result.get("degraded", False) or bool(result.get("error")),
            "generated_at": datetime.now().isoformat(),
        }

    # ==================== 拜访中：开始 & 实时转写 ====================

    async def start_visit(self, db: Session, hcp_id: int, user_id: int, product_id: int) -> Dict:
        """开始拜访：创建拜访记录（status=in_progress）"""
        hcp = self._get_hcp(db, hcp_id)
        if not hcp:
            raise BusinessError(f"医生档案不存在: hcp_id={hcp_id}")

        record = VisitRepo.create(db, {
            "hcp_id": hcp_id,
            "user_id": user_id,
            "product_id": product_id,
            "visit_time": datetime.now(),
            "status": VISIT_STATUS_IN_PROGRESS,
        })
        await write_audit_log(
            user_id=user_id, action="visit_start",
            resource_type="visit", resource_id=str(record.id),
        )
        logger.info(f"拜访开始: visit_id={record.id} hcp_id={hcp_id} user_id={user_id}")
        result = record.to_dict()
        result["visit_id"] = record.id  # 移动端契约：读取 visit_id
        return result

    async def process_transcript(
        self,
        db: Session,
        visit_id: int,
        user_id: int,
        audio_url: Optional[str] = None,
        text_content: Optional[str] = None,
    ) -> Dict:
        """处理拜访中对话：ASR 转写 + 合规实时检查 + 异议识别

        Args:
            audio_url: 录音 URL（走听悟转写）
            text_content: 直接文本（开发调试，跳过听悟）
        """
        record = VisitRepo.get(db, visit_id)
        if not record:
            raise BusinessError(f"拜访记录不存在: visit_id={visit_id}")
        # F12：已结束/已取消的拜访拒绝追加转写 —— 证据已封存，后续内容
        # 不再入档（可重试的占位串不算已结束，仍允许追加后重试 end）
        if record.status == VISIT_STATUS_CANCELLED:
            raise BusinessError(f"拜访已取消，不能追加转写: visit_id={visit_id}")
        if record.ai_summary and record.ai_summary != AI_SUMMARY_PLACEHOLDER:
            raise BusinessError(f"拜访已结束，不能追加转写: visit_id={visit_id}")

        if not text_content:
            if not audio_url:
                raise ParamError("audio_url 和 text 至少提供一个")
            try:
                tingwu_result = await asyncio.to_thread(self.tingwu.transcribe, audio_url)
            except Exception as e:
                logger.error(f"听悟转写失败: {e}")
                raise BusinessError(f"音频转写失败: {e}（开发调试可用 text 直传）")
            text_content = tingwu_result.get("text", "")

        text_content = text_content.strip()
        if not text_content:
            raise ParamError("转写结果为空")

        # 合规实时检查（D）
        compliance = await check_compliance(
            text_content,
            {"user_id": user_id, "type": "live_conversation", "visit_id": visit_id},
        )
        # 异议识别（规则 + 语义，语义不可用自动降级）。B6：detect 内部是同步千问
        # 调用，包到线程池执行，防阻塞事件循环（与 end_visit 直调同模式）
        objection_result = await asyncio.to_thread(self.detector.detect, text_content)

        # F7：锁内追加 —— 并发 process_transcript / end_visit 的读改写窗口串行化，
        # 不互相覆盖；锁内复查状态（拿到锁前对方可能已 end / 取消）
        record = VisitRepo.get(db, visit_id, for_update=True)
        if not record:
            raise BusinessError(f"拜访记录不存在: visit_id={visit_id}")
        if record.status == VISIT_STATUS_CANCELLED:
            raise BusinessError(f"拜访已取消，不能追加转写: visit_id={visit_id}")
        if record.ai_summary and record.ai_summary != AI_SUMMARY_PLACEHOLDER:
            raise BusinessError(f"拜访已结束，不能追加转写: visit_id={visit_id}")

        # 追加转写 + 累积合规标记（不整句覆盖，保留全部违规证据）
        record.conversation_transcript = (record.conversation_transcript or "") + text_content + "\n"
        existing_flags = record.compliance_flags or {"violations": []}
        existing_violations = existing_flags.get("violations") or []
        existing_violations.extend(compliance.get("violations", []))
        record.compliance_flags = {
            "violations": existing_violations,
            "blocked": existing_flags.get("blocked", False) or compliance.get("blocked", False),
        }
        db.commit()

        await write_audit_log(
            user_id=user_id, action="visit_transcript",
            resource_type="visit", resource_id=str(visit_id),
            ai_involved=True, ai_model="tingwu",
            ai_response=text_content[:2000],
            compliance_result=compliance,
        )
        # LLM 实时推荐（关键节点 + 话术建议）：节流触发、失败降级不阻塞
        rec = await self._llm_recommend(db, visit_id, user_id, text_content)
        return {
            "visit_id": visit_id,
            "transcript": text_content,
            "compliance": compliance,
            "objections": objection_result,
            "suggestions": self._generate_suggestions(objection_result, compliance),
            "key_nodes": (rec or {}).get("key_nodes", []),
            "ai_suggestion": (rec or {}).get("ai_suggestion"),
        }

    def _generate_suggestions(self, objection_result: Dict, compliance: Dict) -> Dict:
        """按异议类型生成应对话术建议（规则层兜底）"""
        objection_responses = [
            {"objection": obj.get("text"), "response": _OBJECTION_RESPONSES.get(obj.get("type"), _OBJECTION_RESPONSES["other"])}
            for obj in objection_result.get("objections", [])
        ]
        return {
            "objection_responses": objection_responses,
            "compliance_warnings": compliance.get("violations", []),
        }

    # ==================== 拜访中：LLM 实时推荐（关键节点 + 话术建议） ====================

    _LLM_REC_COOLDOWN_SECONDS = 20.0
    _LLM_REC_MIN_LENGTH = 6

    async def _llm_recommend(
        self, db: Session, visit_id: int, user_id: int, text: str,
    ) -> Optional[Dict]:
        """LLM 实时推荐：生成关键节点标记（决策点/兴趣点）与话术建议

        触发条件：新句去空白后 ≥6 字；同 visit 冷却 20s（以 key_nodes 最后一条的
        created_at 计，进程重启/换实例同样生效）。
        降级：LLM 超时/异常/解析失败 → 记 warning 日志并返回 None，不阻塞主流程。
        """
        stripped = text.strip()
        if len(stripped) < self._LLM_REC_MIN_LENGTH:
            return None

        # 行锁读：并发 process_transcript 对同一 visit 的 key_nodes 追加不互相覆盖
        # （读改写窗口内另一请求 commit 的批次不会丢失；锁随下方 LLM 调用窗口持有）
        record = VisitRepo.get(db, visit_id, for_update=True)
        if not record:
            return None
        if record.key_nodes is not None and not isinstance(record.key_nodes, list):
            # 非列表 JSONB（脏数据）→ 不参与节流判断也不追加（降级铁律：不抛异常）
            return None
        nodes = list(record.key_nodes or [])
        now = datetime.now()
        if nodes and isinstance(nodes[-1], dict) and nodes[-1].get("created_at"):
            try:
                last = datetime.fromisoformat(str(nodes[-1]["created_at"]))
                if (now - last).total_seconds() < self._LLM_REC_COOLDOWN_SECONDS:
                    return None
            except (ValueError, TypeError):
                # created_at 无法解析（含 tz-aware/naive 相减的 TypeError）→ 放行
                pass

        recent_quotes = [str(n.get("quote", "")) for n in nodes[-3:]
                         if isinstance(n, dict) and n.get("quote")]
        prompt = [
            {"role": "system", "content": (
                "你是医药代表拜访的实时陪访助手。根据刚发生的对话片段，标记关键节点并给应对话术。"
                "只输出一个 JSON 对象，不要任何其他文字："
                '{"key_nodes":[{"type":"decision_point|interest_point","label":"≤10字短标签",'
                '"quote":"引用原话≤40字"}],"suggestion":{"topic":"异议主题",'
                '"advice":"应对话术建议≤80字"} 或 null}。'
                "没有值得标记的内容时 key_nodes 给空数组；没有异议时 suggestion 给 null。"
                "type 只能是 decision_point（医生做决策表态/询问决策相关）或 interest_point（医生表现出兴趣/认可）。"
            )},
            {"role": "user", "content": (
                f"对话片段：{stripped}\n"
                f"最近已标记：{'；'.join(recent_quotes) if recent_quotes else '无'}"
                "\n（不要重复标记已标记过的引用）"
            )},
        ]
        try:
            result = await asyncio.to_thread(
                self.qwen.chat, prompt, temperature=0.2, max_tokens=800,
            )
            content = str(result.get("content", "") or "")
            parsed = self._parse_recommendation_json(content)
            if parsed is None:
                logger.warning("visit %s LLM 推荐输出无法解析: %.200s", visit_id, content)
                return None
            key_nodes = []
            for n in parsed.get("key_nodes") or []:
                if not isinstance(n, dict):
                    continue
                ntype = n.get("type")
                label = str(n.get("label", "")).strip()
                quote = str(n.get("quote", "")).strip()
                if ntype not in ("decision_point", "interest_point") or not label:
                    continue
                key_nodes.append({
                    "type": ntype, "label": label[:20], "quote": quote[:60],
                    "created_at": now.isoformat(),
                })
            suggestion = parsed.get("suggestion")
            if not (isinstance(suggestion, dict) and suggestion.get("advice")):
                suggestion = None
            else:
                suggestion = {
                    "topic": str(suggestion.get("topic", "")).strip()[:50] or "对话要点",
                    "advice": str(suggestion.get("advice", "")).strip()[:200],
                }
            if key_nodes:
                record.key_nodes = nodes + key_nodes
                db.commit()
            await write_audit_log(
                user_id=user_id, action="visit_llm_recommend",
                resource_type="visit", resource_id=str(visit_id),
                ai_involved=True, ai_model="qwen-plus",
                ai_response=json.dumps({"key_nodes": key_nodes, "suggestion": suggestion}, ensure_ascii=False)[:2000],
            )
            return {"key_nodes": key_nodes, "ai_suggestion": suggestion}
        except Exception as e:
            # 降级铁律：推荐失败绝不影响转写/合规/异议主流程
            logger.warning("visit %s LLM 实时推荐失败（不阻塞）: %s", visit_id, e)
            return None

    @staticmethod
    def _parse_recommendation_json(content: str) -> Optional[Dict]:
        """从 LLM 输出提取 JSON 对象：容忍 ```json 代码块与前后缀杂讯"""
        text = content.strip()
        # 去 markdown 代码块围栏
        if text.startswith("```"):
            text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    # ==================== 拜访后：结构化记录 & 跟进建议 ====================

    def _create_tasks_idempotent(self, db: Session, visit_id: int, user_id: int, items: list) -> list:
        """按 visit_id 幂等创建任务：该 visit 已有任务（end_visit / follow-up 任一先建过）则跳过

        与 /follow-up 端点共用同一去重规则 —— end_visit 自动建任务后再调
        /follow-up 不会重复建（审计 M20：follow-up 无去重可重复建任务）。
        单条创建失败不影响其余任务（失败记日志，主流程不阻塞）。
        """
        if TaskRepo.list_by_visit(db, visit_id):
            logger.info("visit %s 已有任务，跳过自动创建（按 visit_id 幂等）", visit_id)
            return []
        created = []
        for item in items:
            try:
                task = TaskRepo.create(db, visit_id, user_id, item)
                created.append(task.id)
            except Exception as exc:
                logger.error("任务创建失败: %s", exc)
        if created:
            logger.info("visit %s 自动创建任务 %s 条: %s", visit_id, len(created), created)
        return created

    async def _generate_summary_json(self, prompt: str) -> Optional[Dict]:
        """直调千问生成结构化总结（JSON prompt + system 约束，to_thread 防阻塞事件循环）

        end_visit 不再经专员链路中转（真机联调 2026-08-12 实测）：
        百炼 App 输出是聊天式散文，无论发布与否都无法满足 end_visit 的 JSON 契约，
        旧流程每次都白付专员耗时 + 二次生成；直调一次 ~3s 稳定产出结构化结果。
        返回解析后的结构化 dict；失败 / JSON 里 summary 为空（空转写时 qwen
        偶发返回 {"summary": "", ...}）→ 返回 None，外层写占位串可重试 end。
        """
        try:
            messages = [
                {"role": "system", "content": "只输出 JSON，不要任何额外文字或 markdown 代码块。"},
                {"role": "user", "content": prompt},
            ]
            resp = await asyncio.to_thread(
                self.qwen.chat, messages, model="qwen-max", temperature=0.1, max_tokens=2000,
            )
            structured = _parse_json_content(resp.get("content", ""))
            if structured and not str(structured.get("summary") or "").strip():
                structured = None
            return structured
        except Exception as exc:
            logger.warning("end_visit qwen 生成失败: %s", exc)
            return None

    async def end_visit(
        self,
        db: Session,
        visit_id: int,
        user_id: int,
        full_transcript: Optional[str] = None,
        auth_token: Optional[str] = None,
    ) -> Dict:
        """结束拜访：直调千问生成结构化记录（JSON 契约）→ 合规审核 → 审计日志

        auth_token 保留参数（旧专员链路透传 JWT，直调后不再使用，接口签名兼容）
        """
        # 行锁读：并发双 end / end+cancel / end+transcript 的读改写窗口串行化 ——
        # 只有第一个拿到锁的请求能看到"未结束"状态，其余在锁上等，复查时拒绝
        record = VisitRepo.get(db, visit_id, for_update=True)
        if not record:
            raise BusinessError(f"拜访记录不存在: visit_id={visit_id}")

        if record.status == VISIT_STATUS_CANCELLED:
            raise BusinessError(f"拜访已取消，不能结束: visit_id={visit_id}")

        # 状态锁（S4）：已结束的拜访不能重复 end —— 防止覆盖已生成的结构化记录/证据。
        # AI 失败时写入的是占位串（AI_SUMMARY_PLACEHOLDER），不算已结束，允许重试覆盖
        if record.ai_summary and record.ai_summary != AI_SUMMARY_PLACEHOLDER:
            raise BusinessError(f"拜访已结束，不能重复结束: visit_id={visit_id}")

        if full_transcript:
            record.conversation_transcript = full_transcript
        transcript = record.conversation_transcript or "（无转写内容）"

        prompt = f"""根据以下拜访对话，生成结构化拜访记录。

对话全文：
{transcript}

输出 JSON：
{{
  "summary": "100字摘要",
  "key_points": ["关键点1", "关键点2"],
  "hcp_interests": ["兴趣点"],
  "hcp_objections": ["异议"],
  "follow_up_suggestions": ["跟进建议"],
  "sentiment": "positive/neutral/negative",
  "next_visit_plan": {{
    "recommended_time": "YYYY-MM-DD",
    "recommended_topics": ["话题"],
    "materials_to_send": ["资料"]
  }}
}}"""

        # 直调千问生成结构化总结（不再经专员链路——百炼 App 输出是聊天式散文，
        # 无论发布与否都无法满足 end_visit 的 JSON 契约，旧流程每次白付专员耗时 +
        # 二次生成；真机联调 2026-08-12 实测直调一次 ~3s 稳定产出结构化结果）
        structured = None
        compliance = {"blocked": False, "violations": [], "risk_level": "none"}
        ai_ran = False
        precheck_task = None
        if transcript == "（无转写内容）":
            # 无转写内容 → 无实质对话可总结：直写占位串（不发 AI 调用，可重试 end）
            logger.warning("转写为空，跳过 AI 总结写占位串: visit_id=%s", visit_id)
        else:
            # 合规预检（防御纵深，对齐原专员链路提问侧预检）：转写先过合规再喂 AI。
            # 与 qwen 生成并发执行（互不依赖，串行会白等一次 LLM 往返）；预检拦截时
            # 丢弃生成结果走拦截路径（罕见场景多花一次生成调用，可接受）。
            # check_compliance 客户端对失败安全放行（不抛异常），并发无 500 风险
            precheck_task = asyncio.create_task(check_compliance(
                transcript, {"user_id": user_id, "type": "user_input", "visit_id": visit_id},
            ))
            ai_ran = True
            structured = await self._generate_summary_json(prompt)
            precheck = await precheck_task
            if precheck.get("blocked"):
                logger.warning(
                    f"转写内容被合规拦截: visit_id={visit_id} violations={precheck.get('violations')}"
                )
                structured = None
                compliance = precheck

        if structured:
            ai_summary = str(structured.get("summary", ""))
            key_points = structured.get("key_points", [])
            interests = structured.get("hcp_interests", [])
            objections = structured.get("hcp_objections", [])
            follow_up = structured.get("follow_up_suggestions", [])
            sentiment = structured.get("sentiment", "neutral")
            next_plan = structured.get("next_visit_plan", {})
        elif compliance.get("blocked"):
            # 转写内容预检拦截 → 拦截话术（AI 未运行）
            ai_summary = AI_SUMMARY_BLOCKED
            key_points = interests = objections = follow_up = []
            sentiment, next_plan = "neutral", {}
        else:
            # AI 失败 / 无转写 / 输出不可解析 → 写占位串（不等于"已结束"），允许再次 end 重试
            logger.warning("AI 总结不可用，写入占位串可重试: visit_id=%s", visit_id)
            ai_summary = AI_SUMMARY_PLACEHOLDER
            key_points = interests = objections = follow_up = []
            sentiment, next_plan = "neutral", {}

        # AI 输出合规审核（D）——预检已拦截则跳过（compliance 已带 blocked）
        if not compliance.get("blocked"):
            compliance = await check_compliance(
                ai_summary, {"user_id": user_id, "type": "ai_output", "visit_id": visit_id},
            )
            if compliance.get("blocked"):
                logger.warning(f"拜访总结被合规拦截: visit_id={visit_id} violations={compliance.get('violations')}")
                ai_summary = AI_SUMMARY_BLOCKED
                key_points = interests = objections = follow_up = []
                sentiment, next_plan = "neutral", {}

        # 时长 = 开始到结束的分钟数
        duration = None
        if record.visit_time:
            duration = max(1, int((datetime.now() - record.visit_time).total_seconds() // 60))

        record.ai_summary = ai_summary
        record.key_points = key_points
        record.hcp_interests = interests
        record.hcp_objections = objections
        record.follow_up_suggestions = follow_up
        record.sentiment = sentiment
        record.next_visit_plan = next_plan
        record.duration_minutes = duration
        # 占位串（AI 失败可重试）不算已结束，status 保持 in_progress；真实总结/拦截话术 → completed
        if ai_summary != AI_SUMMARY_PLACEHOLDER:
            record.status = VISIT_STATUS_COMPLETED
        flags = record.compliance_flags or {}
        flags["blocked"] = compliance.get("blocked", False)
        flags["violations"] = flags.get("violations", []) + compliance.get("violations", [])
        record.compliance_flags = flags
        db.commit()

        await write_audit_log(
            user_id=user_id, action="visit_end",
            resource_type="visit", resource_id=str(visit_id),
            ai_involved=ai_ran, ai_model="qwen-max" if ai_ran else None,
            ai_prompt=prompt[:2000], ai_response=ai_summary[:2000],
            compliance_result=compliance,
        )
        # 自动创建后续任务（必做项 需求 2.2.2"任务创建，自动创建后续任务"）：
        # 结构化记录生成成功 → follow_up_suggestions / next_visit_plan 中的动作落库为任务。
        # AI 失败（占位串）/ 合规拦截路径 follow_up/next_plan 已为空 → 不建任务；
        # 按 visit_id 幂等（重复 end 重试不重复建），与 /follow-up 端点共用同一去重
        if structured:
            items = _parse_end_visit_tasks(follow_up, next_plan)
            self._create_tasks_idempotent(db, visit_id, user_id, items)
        # 医生画像更新（必做项）：基于本次拜访的 AI 结构化结果。
        # fire-and-forget：更新是 DB merge + 缓存失效（函数本意"失败不阻塞主流程"），
        # 异步执行省去用户等待的 ~1s 网关往返；visit 记录已落库，画像后续可补
        if structured:
            asyncio.create_task(_push_profile_update(record.hcp_id, structured, visit_id))
        logger.info(f"拜访结束: visit_id={visit_id} duration={duration}min sentiment={sentiment}")
        result = record.to_dict()
        result["visit_id"] = record.id  # 移动端契约：读取 visit_id
        return result

    async def follow_up(
        self, db: Session, visit_id: int, user_id: int,
        auth_token: Optional[str] = None,
    ) -> Dict:
        """生成跟进建议：基于拜访记录 + 医生信息 → 直调千问（不再经专员链路）

        B2 修复（2026-08-12）：旧实现走 chat_with_specialist —— 产品未配置数字专员时
        永久 degraded（answer="" → parsed 回退 {"content": ""}，follow_up_items 恒空，
        跟进建议功能形同虚设且任务永不创建）。直调 qwen-max 一次 ~3s 稳定产出，
        与 end_visit 同一模式（JSON 契约 + to_thread）。
        auth_token 保留参数（旧专员链路透传 JWT，直调后不再使用，接口签名兼容）
        """
        # 行锁：与 end/cancel 的读写串行化；取消的拜访不再生成跟进
        record = VisitRepo.get(db, visit_id, for_update=True)
        if not record:
            raise BusinessError(f"拜访记录不存在: visit_id={visit_id}")
        if record.status == VISIT_STATUS_CANCELLED:
            raise BusinessError(f"拜访已取消，无法生成跟进建议: visit_id={visit_id}")

        hcp = self._get_hcp(db, record.hcp_id) or {}
        prompt = f"""为医药代表生成拜访后的跟进建议。

医生：{hcp.get('name')}（{hcp.get('hospital')} {hcp.get('department')} {hcp.get('title') or ''}）
本次拜访摘要：{record.ai_summary or '（无）'}
兴趣点：{record.hcp_interests or []}
异议：{record.hcp_objections or []}
跟进建议（已有）：{record.follow_up_suggestions or []}

请输出 JSON：
{{
  "follow_up_items": [
    {{"action": "具体跟进动作", "due": "YYYY-MM-DD", "channel": "电话/微信/邮件/下次拜访"}}
  ],
  "reminders": ["下次拜访需要带的材料/注意点"]
}}"""

        try:
            resp = await asyncio.to_thread(
                self.qwen.chat,
                [
                    {"role": "system", "content": "只输出 JSON，不要任何额外文字或 markdown 代码块。"},
                    {"role": "user", "content": prompt},
                ],
                model="qwen-max", temperature=0.1, max_tokens=2000,
            )
            parsed = _parse_json_content(resp.get("content", "")) or {}
            degraded = False
        except Exception as exc:
            logger.warning("follow_up qwen 生成失败（降级返回空建议）: %s", exc)
            parsed = {}
            degraded = True

        # 自动创建后续任务（必做项）：AI 建议逐条落库，失败不影响主流程；
        # 按 visit_id 幂等（end_visit 已自动建过则跳过，避免重复任务）
        follow_up_items = (parsed.get("follow_up_items") or []) if isinstance(parsed, dict) else []
        self._create_tasks_idempotent(
            db, visit_id, user_id,
            _parse_follow_up_items(follow_up_items, visit_id, user_id),
        )

        await write_audit_log(
            user_id=user_id, action="visit_follow_up",
            resource_type="visit", resource_id=str(visit_id),
            ai_involved=not degraded, ai_model="qwen-max" if not degraded else None,
        )
        return {
            "visit_id": visit_id,
            "follow_up": parsed,
            "degraded": degraded,
        }
