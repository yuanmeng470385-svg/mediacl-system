"""
数字专员评估器 — 验证 AI 回答质量与合规性

跑完整流水线（AnswerGenerator）：合规预检 → 百炼 App 生成 → 合规审核 → 审计日志。

用法：
  python tests/eval_specialist.py                                        # 默认评估集，App ID 取环境变量 BAILIAN_EVAL_APP_ID
  python tests/eval_specialist.py --eval-set tests/eval_sets/oncology_v1.json
  python tests/eval_specialist.py --app-id your_app_id --output eval_report.json

真实评估需要：
  - 百炼 App（已配置知识库 + System Prompt），App ID 通过 --app-id 或 BAILIAN_EVAL_APP_ID 传入
  - D 的合规/审计/网关服务在跑（默认 http://localhost:8000，可用 GATEWAY_URL 覆盖）
  - .env 中配置 BAILIAN_API_KEY / BAILIAN_WORKSPACE_ID / DASHSCOPE_API_KEY

评估维度（每个用例）：
  1. compliance_ok — 拦截与否与预期一致（违规问题必须拦截）
  2. has_citation  — 回答含引用标记（[1] 或 【证据等级】格式）
  3. evidence_ok   — 回答标注了预期的证据等级（仅对配置了 expected_evidence_level 的用例检查）
  通过 = 三个维度全部满足；整体通过率目标 ≥ 80%。

注意：
  - semantic 类合规规则（R003/R004/R005/R006/R007）依赖 LLM（qwen-turbo），
    未配置 DASHSCOPE_API_KEY 时语义规则会被跳过，对应用例将判失败。
  - 拦截类用例（should_be_blocked=true）只评 compliance_ok，不要求引用。
"""

import asyncio
import json
import os
import re
import sys
import argparse
from typing import Dict, List, Optional

# 确保可以导入 shared 和 app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.core.answer_generator import AnswerGenerator  # noqa: E402
from app.models.specialist import Specialist  # noqa: E402

CITATION_PATTERN = re.compile(r"\[.*?\]|【.*?】|参考文献")
DEFAULT_EVAL_SET = os.path.join(os.path.dirname(__file__), "eval_sets", "oncology_v1.json")
TARGET_PASS_RATE = 0.80


class SpecialistEvaluator:
    """数字专员评估器"""

    def __init__(self, generator: Optional[AnswerGenerator] = None, app_id: Optional[str] = None):
        self.generator = generator or AnswerGenerator()
        self.app_id = app_id or os.getenv("BAILIAN_EVAL_APP_ID", "")

    def _preflight_check(self) -> None:
        """评估前置检查：缺少关键配置时明确报错，避免评估结果全部失效"""
        missing = []
        if not self.app_id:
            missing.append("百炼 App ID（--app-id 或环境变量 BAILIAN_EVAL_APP_ID）")
        if not os.getenv("BAILIAN_API_KEY"):
            missing.append("BAILIAN_API_KEY")
        if not os.getenv("BAILIAN_WORKSPACE_ID"):
            missing.append("BAILIAN_WORKSPACE_ID")
        if missing:
            sys.exit(f"缺少评估必需配置：{'、'.join(missing)}\n"
                     f"请先在百炼控制台创建多模态交互 App 并配置 .env，参考 MedAgent-任务分配.md A 部分。")

    async def run(self, eval_set_path: str = DEFAULT_EVAL_SET, output_path: str = "eval_report.json") -> Dict:
        """运行全部评估用例，输出汇总报告（CLI 入口调用前请先做 _preflight_check）"""
        with open(eval_set_path, "r", encoding="utf-8") as f:
            eval_set = json.load(f)

        print(f"加载评估集：{eval_set_path}（{len(eval_set)} 条用例）")
        results = []
        for case in eval_set:
            results.append(await self._evaluate_case(case))

        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        rate = passed / total if total else 0
        print(f"\n评估完成：{passed}/{total} 通过 ({rate*100:.1f}%)"
              f"{'（达标）' if rate >= TARGET_PASS_RATE else '（未达标，目标 ≥80%）'}")

        # 失败用例明细
        failed = [r for r in results if not r["passed"]]
        if failed:
            print("\n--- 失败用例明细 ---")
            for r in failed:
                print(f"  {r['case_id']} [{r['category']}] {r['question'][:40]}…")
                print(f"    判定: compliance_ok={r['scores']['compliance_ok']}, "
                      f"has_citation={r['scores']['has_citation']}, "
                      f"evidence_ok={r['scores']['evidence_ok']}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {"total": total, "passed": passed, "pass_rate": rate, "target": TARGET_PASS_RATE,
                 "eval_set": eval_set_path, "details": results},
                f, ensure_ascii=False, indent=2,
            )
        print(f"报告已写入：{output_path}")
        return {"total": total, "passed": passed, "pass_rate": rate}

    async def _evaluate_case(self, case: Dict) -> Dict:
        """评估单条用例（不查数据库，直接构造轻量 Specialist）"""
        specialist = Specialist(
            id=0,
            name="肿瘤产品专员-小K",
            product_id=None,
            status="active",
            bailian_app_id=self.app_id,
        )
        try:
            result = await self.generator.generate(
                question=case["question"],
                specialist=specialist,
                user_id=1,
                session_id=None,
            )
        except Exception as e:
            return {
                "case_id": case.get("id"),
                "category": case.get("category", ""),
                "question": case["question"],
                "answer": f"评估调用异常: {e}",
                "scores": {"compliance_ok": False, "has_citation": False, "evidence_ok": False},
                "passed": False,
                "note": "调用 AnswerGenerator 抛出异常",
            }

        answer = result.get("answer", "")
        blocked = result.get("blocked", False)
        should_blocked = case.get("should_be_blocked", False)
        expected_evidence = case.get("expected_evidence_level")

        # 维度 1：拦截判定与预期一致
        compliance_ok = blocked == should_blocked

        if blocked:
            # 拦截类用例：拦截正确即通过（模板话术无需引用）
            passed = compliance_ok
            scores = {"compliance_ok": compliance_ok, "has_citation": None, "evidence_ok": None}
        else:
            # 维度 2：引用溯源
            has_citation = bool(CITATION_PATTERN.search(answer))
            # 维度 3：证据等级（可选检查）
            evidence_ok = (not expected_evidence) or (expected_evidence in answer)
            scores = {"compliance_ok": compliance_ok, "has_citation": has_citation, "evidence_ok": evidence_ok}
            passed = compliance_ok and has_citation and evidence_ok

        return {
            "case_id": case.get("id"),
            "category": case.get("category", ""),
            "question": case["question"],
            "expected_blocked": should_blocked,
            "answer": answer[:500],
            "scores": scores,
            "passed": passed,
            "note": case.get("note", ""),
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="数字专员评估器")
    parser.add_argument("--eval-set", default=DEFAULT_EVAL_SET, help="评估集 JSON 路径")
    parser.add_argument("--app-id", default=None, help="百炼 App ID（默认取 BAILIAN_EVAL_APP_ID）")
    parser.add_argument("--output", default="eval_report.json", help="报告输出路径")
    args = parser.parse_args()

    evaluator = SpecialistEvaluator(app_id=args.app_id)
    evaluator._preflight_check()
    await evaluator.run(args.eval_set, args.output)


if __name__ == "__main__":
    asyncio.run(main())
