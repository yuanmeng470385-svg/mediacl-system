#!/usr/bin/env python3
"""演示环境一键种子（2026-09-03 演示批二批：种子数据整合）。

一条命令铺出"演示阶段功能一个都不能少"的全链路数据——账号、备案（未来日期）、
官方/代表分身（挂真实百炼 App）、订阅同意、卡片推送、通知中心、夜间简报、
患教专区、拜访记录、医生对话。全部固定内容不调 AI，幂等可重复执行。

用法：
    python scripts/seed_demo_data.py [--password Demo@2026]

前置：postgres 已起；init_db.sql + 迁移 028 已跑；.env 就绪。
演示账号：demo_rep / demo_doctor（密码默认 Demo@2026；验证码登录亦可——
send-code 走 console 通道时验证码在 logs/native/auth-service.log）。

注意（演示账号备案日期必须未来）：24h 备案到期扫描会把 filing_expire_date
过期且 audit_status=approved 的代表自动冻结（status→disabled）——本脚本统一
写 2027-12-31，别在演示前手工改成历史日期。
"""
import argparse
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

# git-bash/VSCode 终端是 UTF-8；PowerShell GBK 控制台跑请用 python -X utf8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services", "auth-service"))

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))

from sqlalchemy import text  # noqa: E402

from shared.common.db_session import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from shared.models.user import User  # noqa: E402
from shared.models.qualification import RepresentativeQualification  # noqa: E402
from shared.models.doctor import (  # noqa: E402
    DoctorCertification, DoctorTwinSubscription, DoctorConsent, ShareLink,
)
from shared.models.digital_specialist import Specialist  # noqa: E402
from shared.models.nightly_briefing import NightlyBriefing  # noqa: E402
from shared.models.academic import AcademicCard, CardPushRecord, Notification  # noqa: E402
from shared.models.doctor_profile import DoctorProfile  # noqa: E402
from shared.models.patient_edu import PatientEduTemplate, EduContentRecord  # noqa: E402
from shared.models.hcp import Hcp  # noqa: E402

SH = ZoneInfo("Asia/Shanghai")
DEMO_EXPIRE = date(2027, 12, 31)   # 演示备案到期日：必须未来（24h 扫描会冻结过期的 approved 代表）
CONSENT_VERSION = "v1.0"

# conversations / visit_records 两表的 ORM 映射分别在 specialist/visit 服务里，
# 多服务 app 包同名冲突 → 用 Core text() 直插（幂等按 session_id / visit_time 查）
SQL_INSERT_CONVERSATION = text("""
    INSERT INTO conversations
        (user_id, specialist_id, session_id, role, content, citations,
         compliance_result, tokens_used, latency_ms, created_at)
    VALUES
        (:user_id, :specialist_id, :session_id, :role, :content,
         CAST(:citations AS JSONB), CAST(:compliance_result AS JSONB),
         :tokens_used, :latency_ms, :created_at)
""")
SQL_COUNT_DEMO_SESSION = text("SELECT count(*) FROM conversations WHERE session_id = :sid")
SQL_INSERT_VISIT = text("""
    INSERT INTO visit_records
        (hcp_id, user_id, specialist_id, visit_time, status, duration_minutes,
         conversation_transcript, ai_summary,
         key_points, hcp_interests, hcp_objections, follow_up_suggestions,
         sentiment, compliance_flags, created_at, updated_at)
    VALUES
        (:hcp_id, :user_id, :specialist_id, :visit_time, 'completed', 45,
         :transcript, :summary,
         CAST(:key_points AS JSONB), CAST(:interests AS JSONB),
         CAST(:objections AS JSONB), CAST(:follow_ups AS JSONB),
         'positive', CAST('[]' AS JSONB), :created_at, :created_at)
""")
SQL_COUNT_DEMO_VISIT = text(
    "SELECT count(*) FROM visit_records WHERE user_id = :uid AND visit_time = :visit_time"
)

OK_COMPLIANCE = json.dumps({"blocked": False, "violations": []})


def _get_or_create(db, model, defaults=None, **filters):
    row = db.query(model).filter_by(**filters).first()
    if row:
        return row, False
    row = model(**(defaults or {}), **filters)
    db.add(row)
    db.flush()
    return row, True


def _ensure_user(db, username, full_name, phone, role, password_hash):
    # users.full_name 等列 NOT NULL —— 创建时必须带全字段，不能先建空行再回填
    user, _ = _get_or_create(
        db, User, username=username,
        defaults={"full_name": full_name, "phone": phone, "role": role,
                  "password_hash": password_hash, "status": "active"},
    )
    user.full_name = full_name
    user.phone = phone
    user.role = role
    user.status = "active"          # 演示号永远 active（复活此前冻结/停用的演示号）
    user.deleted_at = None
    return user


def _sh_yesterday_midday_utc() -> datetime:
    """上海"昨天 14:00"换算成 naive UTC（种子时间稳定落在上海昨天，供简报/统计口径）"""
    sh = datetime.combine(date.today(), datetime.min.time(), tzinfo=SH) - timedelta(days=1)
    return sh.replace(hour=14).astimezone(timezone.utc).replace(tzinfo=None)


def seed(db, password: str) -> dict:
    stats = {}
    ph = hash_password(password)
    ago8 = datetime.utcnow() - timedelta(days=8)

    # ---------- 账号 ----------
    rep = _ensure_user(db, "demo_rep", "演示代表·李明", "13900001001", "rep", ph)
    doctor = _ensure_user(db, "demo_doctor", "演示医生·周琴", "13900001002", "doctor", ph)
    admin = db.query(User).filter_by(role="admin", status="active").order_by(User.id).first()
    db.flush()
    stats["users"] = (rep.id, doctor.id, admin.id if admin else None)

    # ---------- 备案（approved + 未来日期 + 培训/考试/承诺三件套 → MAH 面板高完成率） ----------
    qual, _ = _get_or_create(
        db, RepresentativeQualification, representative_id=rep.id,
        defaults={"education_cert": "https://oss.example.com/demo/education_cert.pdf",
                  "training_cert": "https://oss.example.com/demo/training_cert.pdf",
                  "audit_status": "approved",
                  "filing_number": "DEMO-FILING-2026-001",
                  "filing_expire_date": DEMO_EXPIRE,
                  "reviewed_by": admin.id if admin else None,
                  "reviewed_at": datetime.utcnow() - timedelta(days=10),
                  "compliance_training_completed": True,
                  "compliance_exam_score": 92,
                  "commitment_signed": True},
    )
    # 幂等重跑时刷新到目标态（防演示前被手工改动）
    qual.education_cert = "https://oss.example.com/demo/education_cert.pdf"
    qual.training_cert = "https://oss.example.com/demo/training_cert.pdf"
    qual.audit_status = "approved"
    qual.filing_number = "DEMO-FILING-2026-001"
    qual.filing_expire_date = DEMO_EXPIRE
    qual.reviewed_by = admin.id if admin else None
    qual.reviewed_at = datetime.utcnow() - timedelta(days=10)
    qual.compliance_training_completed = True
    qual.compliance_exam_score = 92
    qual.commitment_signed = True

    # ---------- 医生认证 + 偏好画像 ----------
    cert, _ = _get_or_create(
        db, DoctorCertification, doctor_id=doctor.id,
        defaults={"cert_type": "physician",
                  "cert_image_url": "https://oss.example.com/demo/cert_physician.jpg",
                  "cert_status": "approved",
                  "reviewed_by": admin.id if admin else None,
                  "reviewed_at": datetime.utcnow() - timedelta(days=9)},
    )
    cert.cert_type = "physician"
    cert.cert_image_url = "https://oss.example.com/demo/cert_physician.jpg"
    cert.cert_status = "approved"
    cert.reviewed_by = admin.id if admin else None
    cert.reviewed_at = datetime.utcnow() - timedelta(days=9)
    _get_or_create(
        db, DoctorProfile, doctor_id=doctor.id,
        defaults={"interest_areas": ["肿瘤", "免疫治疗"], "preferred_doc_type": "rct",
                  "preferred_style": "标准", "closed": False},
    )

    # ---------- 分身（rep 分身挂真实百炼 App → 演示对话不降级） ----------
    app_id = (
        os.getenv("DEFAULT_TWIN_BAILIAN_APP_ID", "").strip()
        or db.query(Specialist.bailian_app_id)
            .filter(Specialist.bailian_app_id.isnot(None), Specialist.bailian_app_id != "")
            .order_by(Specialist.is_official.desc())
            .limit(1).scalar()
        or ""
    )
    official, _ = _get_or_create(
        db, Specialist, is_official=True, name="肿瘤学术官·官方分身",
        defaults={"status": "active", "compliance_level": "internal",
                  "bailian_app_id": app_id or None,
                  "persona": {"intro": "药企官方肿瘤学术数字员工，提供循证医学信息。"}},
    )
    twin, _ = _get_or_create(
        db, Specialist, name="李明的数字分身", representative_id=rep.id,
        defaults={"status": "active", "compliance_level": "internal",
                  "bailian_app_id": app_id or None,
                  "persona": {"style": {"formal_level": "标准", "reply_length": "适中",
                                        "opening_mode": "直切主题"}}},
    )
    db.flush()
    stats["specialists"] = (official.id, twin.id)
    stats["bailian_app"] = bool(app_id)

    # ---------- 分享链接（夜间简报的"我的分身"口径 = share_links.created_by） ----------
    _get_or_create(db, ShareLink, created_by=rep.id, twin_id=twin.id,
                   defaults={"url_token": f"demo_{uuid.uuid4().hex[:12]}", "add_count": 3})

    # ---------- 订阅 + 知情同意（push-targets 有数据 / 医生端能对话） ----------
    for sid in (twin.id, official.id):
        _get_or_create(db, DoctorTwinSubscription, doctor_id=doctor.id, twin_id=sid,
                       defaults={"status": "subscribed", "consent_version": CONSENT_VERSION,
                                 "consent_at": ago8})
        _get_or_create(db, DoctorConsent, doctor_id=doctor.id, twin_id=sid,
                       defaults={"consent_type": "twin", "version": CONSENT_VERSION,
                                 "agreed_at": ago8})

    # ---------- 医生↔分身对话（上海昨天 4 轮 → 分身监控/统计/简报口径有数据；全合规不进复核名单） ----------
    y = _sh_yesterday_midday_utc()
    qa_pairs = [
        ("免疫联合治疗在三阴性乳腺癌的最新数据有哪些？",
         "根据 KEYNOTE-522 研究结果，帕博利珠单抗联合化疗新辅助治疗显著提高了病理完全缓解率，"
         "具体数据请参考已发表文献。以上信息仅供学术参考。"),
        ("老年患者使用该方案的安全性如何？",
         "临床研究中老年亚组的安全性与总体人群基本一致，常见不良事件为骨髓抑制和乏力，"
         "具体剂量调整请遵循说明书并结合临床判断。"),
        ("与同类竞品相比优势在哪里？",
         "不同 PD-1/PD-L1 抑制剂在适应症、研究人群和终点设计上存在差异，不建议直接跨研究比较，"
         "建议关注各自适应症内的循证证据。"),
        ("下周科室会能来讲讲真实世界研究吗？",
         "可以的，我会准备真实世界研究数据综述，具体时间请与李明确认，"
         "科室会材料会提前送医学部审核。"),
    ]
    if db.execute(SQL_COUNT_DEMO_SESSION, {"sid": "demo_doctor_chat_1"}).scalar() == 0:
        for i, (q, a) in enumerate(qa_pairs):
            db.execute(SQL_INSERT_CONVERSATION, {
                "user_id": doctor.id, "specialist_id": twin.id,
                "session_id": "demo_doctor_chat_1", "role": "user", "content": q,
                "citations": None, "compliance_result": OK_COMPLIANCE,
                "tokens_used": 120 + i * 15, "latency_ms": 1800 + i * 200,
                "created_at": y + timedelta(minutes=i * 6),
            })
            db.execute(SQL_INSERT_CONVERSATION, {
                "user_id": doctor.id, "specialist_id": twin.id,
                "session_id": "demo_doctor_chat_1", "role": "assistant", "content": a,
                "citations": json.dumps([{"doc_name": "演示文献·免疫治疗综述",
                                          "url": None, "doc_id": None}]),
                "compliance_result": OK_COMPLIANCE,
                "tokens_used": 260 + i * 30, "latency_ms": 2100 + i * 150,
                "created_at": y + timedelta(minutes=i * 6, seconds=40),
            })
        stats["conversations"] = len(qa_pairs) * 2

    # ---------- rep↔分身对话（2026-09-07 A-4：MAH 合规通过率分母已收敛为 rep 的分身
    # 对话，医生对话不再计入——必须补 rep 侧数据，否则 MAH 面板分母归零显示 100%）。
    # 8 轮 = 6 合规 + 1 blocked（R001）+ 1 warn（R005 不拦截）→ 通过率 7/8=87.5%，
    # 拦截明细走 audit/演示口径。blocked 的 compliance_result 落 assistant 行（与
    # review-queue/mah 的行级判定口径一致），内容为掩码文案。
    if db.execute(SQL_COUNT_DEMO_SESSION, {"sid": "demo_rep_chat_1"}).scalar() == 0:
        R001_BLOCKED = json.dumps({"blocked": True, "violations": [
            {"rule_code": "R001", "rule_name": "禁止承诺疗效", "action": "reject"}]})
        R005_WARN = json.dumps({"blocked": False, "violations": [
            {"rule_code": "R005", "rule_name": "禁止贬低竞品", "action": "warn"}]})
        rep_rounds = [
            # (问题, 回答, assistant 行 compliance_result)
            ("帮我整理一下本品在一线治疗的循证证据要点。",
             "本品一线治疗的证据主要来自 III 期随机对照研究，主要终点显著改善，"
             "具体数据以发表文献和说明书为准。以上信息仅供学术参考。", OK_COMPLIANCE),
            ("跟医生沟通时不良反应这部分应该怎么讲比较规范？",
             "建议按说明书口径客观呈现不良反应发生率与管理措施，不隐瞒不淡化，"
             "出现严重不良事件应及时上报。", OK_COMPLIANCE),
            ("这个药用了以后能保证治愈吗？我想这么跟主任说。",
             "该问题建议直接咨询医学顾问。", R001_BLOCKED),
            ("下周拜访心内科，帮我准备一个开场话题。",
             "可以围绕近期发布的科室会主题和文献速览展开，先了解医生当前关注的方向，"
             "再介绍相关学术资料。", OK_COMPLIANCE),
            ("隔壁那家竞品效果不太行，我们是不是可以强调这点？",
             "不建议对竞品做比较性评价。学术沟通应聚焦本品适应症内的循证证据，"
             "跨研究直接比较容易产生误导。", R005_WARN),
            ("患者用药教育这块有什么患者版材料可以用吗？",
             "患教材料需经医学部与合规审核后使用，我可以帮你梳理常见问题的"
             "沟通要点供参考。", OK_COMPLIANCE),
            ("把这份综述的三个关键结论做成卡片要点。",
             "已按综述结论整理为三点：疗效主要终点、安全性谱、用药注意事项，"
             "每点均附文献出处。", OK_COMPLIANCE),
            ("这次科室会材料还需要补充哪些合规注意项？",
             "材料中避免绝对化疗效表述与超适应症内容，引用数据须可溯源，"
             "结尾附免责声明并送医学部审核。", OK_COMPLIANCE),
        ]
        for i, (q, a, a_cr) in enumerate(rep_rounds):
            db.execute(SQL_INSERT_CONVERSATION, {
                "user_id": rep.id, "specialist_id": twin.id,
                "session_id": "demo_rep_chat_1", "role": "user", "content": q,
                "citations": None, "compliance_result": OK_COMPLIANCE,
                "tokens_used": 100 + i * 12, "latency_ms": 1600 + i * 180,
                "created_at": y + timedelta(hours=2, minutes=i * 6),
            })
            db.execute(SQL_INSERT_CONVERSATION, {
                "user_id": rep.id, "specialist_id": twin.id,
                "session_id": "demo_rep_chat_1", "role": "assistant", "content": a,
                "citations": json.dumps([{"doc_name": "演示文献·免疫治疗综述",
                                          "url": None, "doc_id": None}]),
                "compliance_result": a_cr,
                "tokens_used": 220 + i * 25, "latency_ms": 1900 + i * 160,
                "created_at": y + timedelta(hours=2, minutes=i * 6, seconds=40),
            })
        stats["rep_conversations"] = len(rep_rounds) * 2

    # ---------- 学术卡片 + 推送 + 通知（触达统计/收件箱/通知中心全链路有数据） ----------
    card, _ = _get_or_create(
        db, AcademicCard, representative_id=rep.id, title="免疫治疗研究进展速览（演示）",
        defaults={"content": {
            "conclusion": "免疫联合治疗在多个瘤种中显示出持续生存获益，安全管理至关重要。",
            "key_points": [
                "新辅助免疫联合方案显著提高病理完全缓解率",
                "老年亚组安全性与总体人群一致",
                "不良反应管理以早识别、早干预为原则",
            ],
            "summary": "免疫联合治疗进展与安全管理要点。",
            "citations": [{"doc_name": "演示文献·免疫治疗综述", "url": None, "doc_id": None}],
        }, "is_ai_generated": True, "compliance_status": "passed", "status": "active"},
    )
    push, _ = _get_or_create(
        db, CardPushRecord, card_id=card.id, doctor_id=doctor.id,
        defaults={"representative_id": rep.id, "specialist_id": twin.id,
                  "read_status": "read", "read_at": datetime.utcnow() - timedelta(days=1),
                  "tracked_seconds": 95,
                  # 追问文本（非 useful/useless，2026-09-07 A-2 起会并入夜间简报数据源），
                  # 与下方 card_question 通知文案一致
                  "feedback": "老年患者安全性数据能否提供原文出处？",
                  "matched_interest": True},
    )
    # 幂等刷：旧库该行是"内容很有参考价值"（A-2 口径下会被当成追问，文案不自洽）
    push.feedback = "老年患者安全性数据能否提供原文出处？"
    # rep 通知中心：1 条已读（简报就绪）+ 2 条未读（医生反馈/追问）
    _get_or_create(
        db, Notification, user_id=rep.id, type="briefing_ready", title="你的夜间简报已生成",
        defaults={"content": "查看医生提问汇总与需跟进事项", "link": "/briefings",
                  "is_read": True},
    )
    _get_or_create(
        db, Notification, user_id=rep.id, type="card_feedback", title="周琴医生觉得卡片有用",
        defaults={"content": "「免疫治疗研究进展速览（演示）」收到 useful 反馈",
                  "link": "/briefings", "is_read": False},
    )
    _get_or_create(
        db, Notification, user_id=rep.id, type="card_question", title="周琴医生追问了卡片内容",
        defaults={"content": "追问：老年患者安全性数据能否提供原文出处？",
                  "link": "/briefings", "is_read": False},
    )
    _get_or_create(
        db, Notification, user_id=doctor.id, type="card_new",
        title="收到学术卡片：免疫治疗研究进展速览（演示）",
        defaults={"content": None, "link": "/card-pushes", "is_read": False},
    )

    # ---------- 夜间简报（固定内容；briefing_date=上海今天，简报列表即点即看） ----------
    briefing_content = {
        "summary": "周琴医生昨日围绕免疫联合治疗提问 4 次，关注三阴性乳腺癌新辅助数据、"
                   "老年患者安全性与真实世界证据，建议跟进科室会安排。",
        "doctors": [{
            "doctor_name": "演示医生·周琴",
            "questions": ["免疫联合治疗在三阴性乳腺癌的最新数据",
                          "老年患者使用该方案的安全性",
                          "与同类竞品相比优势"],
            "concern": "老年患者安全性与数据出处",
            "follow_up": "提供文献原文；确认下周科室会时间",
        }],
        # 医生对学术卡片的追问（2026-09-07 A-2 并入简报；与卡片反馈/通知文案同源）
        "card_questions": [{
            "doctor_name": "演示医生·周琴",
            "card_title": "免疫治疗研究进展速览（演示）",
            "question": "老年患者安全性数据能否提供原文出处？",
            "suggested_reply": "下次随访带上综述原文与老年亚组森林图，当面核对数据口径",
        }],
    }
    briefing, _ = _get_or_create(
        db, NightlyBriefing, representative_id=rep.id, specialist_id=twin.id,
        briefing_date=datetime.now(SH).date(),
        defaults={"content": briefing_content, "status": "ready"},
    )
    # 幂等刷固定演示文案：已存在的简报行（同 briefing_date 重跑）不走 defaults，
    # 无条件覆写保证演示内容与最新脚本一致
    briefing.content = briefing_content

    # ---------- 患教：2 个 approved 模板 + 1 条已分享患教卡片（专区可见 + 转发留痕） ----------
    tpl_titles = {
        "化疗患者居家护理要点（演示）": "肿瘤",
        "免疫治疗不良反应的自我识别（演示）": "肿瘤",
    }
    for title, area in tpl_titles.items():
        _get_or_create(
            db, PatientEduTemplate, title=title,
            defaults={"disease_area": area, "content":
                      "本材料面向患者及家属，介绍居家护理/自我监测要点。出现发热、气促、"
                      "出血倾向等情况请立即就医。内容仅供患者教育参考，不构成诊疗建议。",
                      "review_status": "approved", "created_by": admin.id if admin else None,
                      "reviewed_by": admin.id if admin else None},
        )
    demo_tpl = db.query(PatientEduTemplate).filter_by(
        title="免疫治疗不良反应的自我识别（演示）").first()
    _get_or_create(
        db, EduContentRecord, doctor_id=doctor.id, template_id=demo_tpl.id,
        defaults={"content": {
            "title": "免疫治疗期间出现这些情况请及时就医",
            "body": "免疫治疗可能引起罕见但需要重视的不良反应。若出现持续发热、明显气促、"
                    "严重腹泻、皮肤大面积皮疹或黄疸，请立即联系主管医生或前往急诊。",
            "notes": "本卡片由医生通过患教工具生成，转发前已确认内容。",
            "seek_care": "发热超过 38.5℃、气促、严重腹泻、黄疸等请立即就医。",
        }, "is_ai_generated": True, "visibility": "shared", "audit_status": "approved",
          "forward_count": 2, "last_forwarded_at": datetime.utcnow() - timedelta(days=1)},
    )

    # ---------- 拜访（工作台统计/web 拜访管理有数据） ----------
    hcp, _ = _get_or_create(
        db, Hcp, name="王建国", hospital="市第一人民医院",
        defaults={"department": "肿瘤内科", "title": "主任医师", "specialty": "肿瘤",
                  "influence_level": "high", "tags": ["肿瘤KOL", "学术型"],
                  "status": "active"},
    )
    visit_time = y + timedelta(hours=2)
    # 转写用现行 [代表]/[医生] 行首前缀（visit_manager 2026-08-27 双方分离落库口径，
    # 也是 style-sources 拜访素材 [代表] 行聚合的抓取依据——旧「李明：」格式抓不到）
    demo_transcript = (
        "[代表] 王主任好，上次提到的免疫治疗数据我整理好了。\n"
        "[医生] 嗯，老年患者那部分再展开讲讲。\n"
        "[代表] 老年亚组安全性与总体一致，常见不良事件是骨髓抑制……\n"
        "[医生] 行，下周科室会你来讲真实世界研究这块。"
    )
    if db.execute(SQL_COUNT_DEMO_VISIT, {"uid": rep.id, "visit_time": visit_time}).scalar() == 0:
        db.execute(SQL_INSERT_VISIT, {
            "hcp_id": hcp.id, "user_id": rep.id, "specialist_id": twin.id,
            "visit_time": visit_time,
            "transcript": demo_transcript,
            "summary": "拜访市第一人民医院肿瘤内科王建国主任，围绕免疫联合治疗老年患者安全性"
                       "展开交流，王主任对真实世界研究数据表达关注，约定下周科室会讲解。",
            "key_points": json.dumps(["老年亚组安全性", "真实世界研究关注"]),
            "interests": json.dumps(["免疫联合治疗", "真实世界证据"]),
            "objections": json.dumps(["竞品对比数据说服力"]),
            "follow_ups": json.dumps(["提供文献原文", "确认科室会时间"]),
            "created_at": datetime.utcnow() - timedelta(days=1),
        })
        stats["visits"] = 1
    else:
        # transcript 幂等刷无条件覆写（卡片 feedback 同款先例）：
        # 存量行的旧「李明：」格式刷新后才能被分身选材命中
        db.execute(text(
            "UPDATE visit_records SET conversation_transcript = :t "
            "WHERE user_id = :uid AND visit_time = :visit_time"
        ), {"t": demo_transcript, "uid": rep.id, "visit_time": visit_time})

    db.commit()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="演示环境一键种子（幂等）")
    parser.add_argument("--password", default="Demo@2026", help="演示账号密码（默认 Demo@2026）")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stats = seed(db, args.password)
    finally:
        db.close()

    rep_id, doctor_id, admin_id = stats["users"]
    official_id, twin_id = stats["specialists"]
    print("=" * 62)
    print("演示种子完成（幂等，重复执行安全）")
    print(f"  demo_rep    id={rep_id}  13900001001  演示代表·李明（备案 approved 至 {DEMO_EXPIRE}）")
    print(f"  demo_doctor id={doctor_id} 13900001002  演示医生·周琴（认证 approved）")
    print(f"  密码：{args.password}（用户名或手机号均可登录）")
    print(f"  分身：官方 #{official_id} / 李明的分身 #{twin_id}（百炼 App：{'已挂' if stats['bailian_app'] else '未找到，对话将降级！'}）")
    print("  数据：医生对话×%s 卡片×1 推送×1 通知×4 简报×1 患教模板×2 患教专区×1 拜访×%s" % (stats.get("conversations", 0), stats.get("visits", 0)))
    print("-" * 62)
    print("演示动线建议：")
    print("  web   admin 登录 → 仪表盘/MAH 总览（备案+培训完成率 100%）→ 监管报告导出")
    print("  rep   demo_rep → 工作台 → 与分身对话 → 通知中心（2 条未读）→ 夜间简报")
    print("        → 学术卡片推送（push-targets 勾选周琴）→ 拜访记录")
    print("  doc   demo_doctor → 广场/订阅 → 收件箱（1 张卡片）→ 患教专区 → 我的患教")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
