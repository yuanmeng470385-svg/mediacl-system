#!/usr/bin/env python3
"""内置合规培训材料种子：医药代表管理办法要点 + RDPAC 行为准则要点 + 2 条已审核题目

用法：
    python scripts/seed_training_materials.py
幂等：已存在同标题 material 时跳过。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "services", "auth-service"))

from dotenv import load_dotenv
load_dotenv()

from shared.common.db_session import SessionLocal
from shared.models.training_exam import ExamQuestion, TrainingMaterial

REGULATION_TITLE = "《医药代表管理办法》要点（2026版）"
RDPAC_TITLE = "RDPAC 行业行为准则要点"

REGULATION_CONTENT = """《医药代表管理办法》（2026-08-01 施行）要点：
一、医药代表备案：须在国家医药代表备案平台完成备案，备案信息真实有效；代表证有效期内方可从事学术推广。
二、职责限定：仅从事学术推广（向医务人员介绍药品信息、收集不良反应信息、协助合规推广活动），不得承担销售任务、不得统方（获取处方量/药品用量信息）、不得虚构拜访记录。
三、二十二项禁止行为（要点）：不得提供财物或其他利益（R009）、不得附加销售条件（R008）、不得隐瞒不良反应（R010）、不得误导用药（R011）、不得超适应症推广、不得无授权推广、不得挂靠其他机构等。
四、合规培训：代表须完成年度合规培训并通过考试；签署年度合规承诺书。
五、监督管理：药企对代表行为负主体责任；违规记录纳入信用档案。"""

RDPAC_CONTENT = """RDPAC（中国外商投资企业协会药品研制和开发行业委员会）行业行为准则要点：
一、推广活动须以学术交流为目的，公平竞争，禁止虚假或误导性信息。
二、与医务人员的互动须透明、适度，不得以馈赠影响处方行为。
三、禁止向处方者提供现金、礼品或任何形式的利益输送。
四、推广信息须符合说明书与已获批适应症范围。"""

# 内置 2 条已审核题目，保证考试开箱可用
BUILTIN_QUESTIONS = [
    {
        "question_type": "judge",
        "content": "医药代表可以收集药品不良反应信息。",
        "options": ["正确", "错误"],
        "answer": [0],
    },
    {
        "question_type": "single",
        "content": "医药代表的核心职责是：",
        "options": ["承担药品销售任务", "从事学术推广并收集不良反应信息", "获取处方量信息", "直接向患者推荐处方"],
        "answer": [1],
    },
]


def main() -> None:
    db = SessionLocal()
    try:
        mat_ids = {}
        for title, mtype, content in [
            (REGULATION_TITLE, "regulation", REGULATION_CONTENT),
            (RDPAC_TITLE, "rdpac", RDPAC_CONTENT),
        ]:
            existing = db.query(TrainingMaterial).filter(TrainingMaterial.title == title).first()
            if existing:
                mat_ids[title] = existing.id
                print(f"跳过已存在材料: {title}")
                continue
            mat = TrainingMaterial(title=title, material_type=mtype, content=content, created_by=None, status="active")
            db.add(mat)
            db.flush()
            mat_ids[title] = mat.id
            print(f"已创建材料: {title} (id={mat.id})")

        reg_id = mat_ids.get(REGULATION_TITLE)
        for q in BUILTIN_QUESTIONS:
            existing = db.query(ExamQuestion).filter(ExamQuestion.content == q["content"]).first()
            if existing:
                continue
            db.add(ExamQuestion(
                material_id=reg_id,
                question_type=q["question_type"],
                content=q["content"],
                options=q["options"],
                answer=q["answer"],
                review_status="approved",
            ))
            print(f"已创建题目: {q['content']}")
        db.commit()
        print("培训考试种子完成。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
