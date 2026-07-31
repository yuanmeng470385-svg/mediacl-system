"""
合规审核引擎 — 三层审核流水线

第 1 关：关键词匹配（快速，零成本）
第 2 关：正则匹配（快速，零成本）
第 3 关：LLM 语义审核（慢，仅对 semantic 类型规则触发）

拦截动作：
  - reject: 拒绝（blocked=True）
  - warn:   警告（blocked=False，但返回 violations）
  - log:    仅记录（blocked=False，但返回 violations）
"""

import os
import re
import json
import logging
from typing import Dict, List, Optional

import yaml
from openai import OpenAI

logger = logging.getLogger(__name__)


class ComplianceChecker:
    """合规审核器"""

    def __init__(self):
        self.qwen_client = None  # 延迟初始化（仅语义审核时需要）
        self.rules: List[Dict] = []
        self._reload_rules()

    # ==================== 规则加载 ====================

    def _reload_rules(self):
        """从 YAML 文件 + 数据库加载规则，合并去重"""
        rules = []
        # 1. 从 YAML 文件加载
        yaml_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "shared", "compliance-rules", "rules.yaml"
        )
        if os.path.exists(yaml_path):
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            rules.extend(config.get("rules", []))

        # 2. TODO: 从数据库加载规则（优先级高于 YAML，可覆盖）
        # db_rules = self._load_db_rules()
        # rules = self._merge_rules(rules, db_rules)

        # 3. 仅保留 enabled 的规则
        rules = [r for r in rules if r.get("enabled", True)]
        self.rules = rules
        self._compile_rules()
        logger.info(f"合规规则加载完成，共 {len(self.rules)} 条有效规则")

    def _compile_rules(self):
        """预编译关键词和正则，提高运行效率"""
        for rule in self.rules:
            if rule["type"] == "keyword":
                rule["_patterns"] = [p for p in rule.get("patterns", [])]
            elif rule["type"] == "regex":
                rule["_compiled"] = [re.compile(p) for p in rule.get("patterns", [])]

    def reload(self):
        """热更新：重新加载所有规则"""
        self._reload_rules()
        logger.info("合规规则热更新完成")

    # ==================== 审核主流程 ====================

    def check(self, content: str, context: Optional[Dict] = None) -> Dict:
        """
        审核内容合规性

        Args:
            content: 待审核的文本内容
            context: 上下文信息 {user_id, type, specialist_id, visit_id}

        Returns:
            {
                "blocked": True/False,
                "violations": [{rule_code, rule_name, severity, action, matched_text}],
                "risk_level": "high"/"medium"/"low"/"none",
                "checked_rules": [...]
            }
        """
        if not content or not content.strip():
            return self._safe_result()

        context = context or {}
        violations = []
        checked_rules = []

        # ----- 第 1 关 + 第 2 关：关键词 + 正则（合并，都是文本匹配） -----
        for rule in self.rules:
            if rule["type"] not in ("keyword", "regex"):
                continue
            checked_rules.append(rule["id"])
            matched = self._match_rule(content, rule)
            if matched:
                violations.append({
                    "rule_code": rule["id"],
                    "rule_name": rule["name"],
                    "severity": rule["severity"],
                    "action": rule["action"],
                    "matched_text": matched,
                })

        # 如果已有 reject 级别的违规，直接返回（省一次 LLM 调用）
        if any(v["action"] == "reject" for v in violations):
            return self._result(True, violations)

        # ----- 第 3 关：LLM 语义审核 -----
        semantic_rules = [r for r in self.rules if r["type"] == "semantic"]
        if semantic_rules:
            semantic_violations = self._semantic_check(content, semantic_rules, context)
            violations.extend(semantic_violations)

        blocked = any(v["action"] == "reject" for v in violations)
        return self._result(blocked, violations)

    # ==================== 第 1 关 + 第 2 关：文本匹配 ====================

    def _match_rule(self, content: str, rule: Dict) -> Optional[str]:
        """对单条规则匹配内容，返回匹配到的文本或 None"""
        if rule["type"] == "keyword":
            for pattern in rule.get("_patterns", []):
                if pattern in content:
                    return pattern
        elif rule["type"] == "regex":
            for compiled in rule.get("_compiled", []):
                m = compiled.search(content)
                if m:
                    return m.group()
        return None

    # ==================== 第 3 关：LLM 语义审核 ====================

    def _semantic_check(self, content: str, semantic_rules: List[Dict], context: Dict) -> List[Dict]:
        """调用通义千问进行语义层面的合规审核"""
        if not self.qwen_client:
            api_key = os.getenv("DASHSCOPE_API_KEY", "")
            if not api_key:
                logger.warning("DASHSCOPE_API_KEY 未配置，跳过语义审核")
                return []
            self.qwen_client = OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )

        rules_desc = "\n".join([
            f"- {r['id']}: {r['name']}（{r.get('description', '')}）→ 动作: {r['action']}"
            for r in semantic_rules
        ])

        prompt = f"""你是药企合规审核员。检查以下内容是否违反合规规则。

合规规则：
{rules_desc}

待检查内容：
{content}

请只输出 JSON（不要额外文字）：
{{"violations": [{{"rule_code": "R003", "matched_text": "违规的文本片段", "reason": "简要原因"}}]}}

如果内容合规，输出：
{{"violations": []}}"""

        try:
            response = self.qwen_client.chat.completions.create(
                model=os.getenv("QWEN_TURBO_MODEL", "qwen-turbo"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=500,
            )
            raw = response.choices[0].message.content.strip()
            # 清理可能的 markdown 代码块包裹
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("\n", 1)[0]
            parsed = json.loads(raw)
            violations = []
            for v in parsed.get("violations", []):
                rule = next((r for r in semantic_rules if r["id"] == v["rule_code"]), None)
                if rule:
                    violations.append({
                        "rule_code": v["rule_code"],
                        "rule_name": rule["name"],
                        "severity": rule["severity"],
                        "action": rule["action"],
                        "matched_text": v.get("matched_text", ""),
                        "reason": v.get("reason", ""),
                    })
            return violations
        except Exception as e:
            logger.error(f"LLM 语义审核失败: {e}")
            return []  # LLM 失败时放行，避免误伤业务

    # ==================== 辅助方法 ====================

    def _result(self, blocked: bool, violations: List[Dict]) -> Dict:
        """构建审核结果"""
        if not violations:
            return self._safe_result()

        # 计算风险等级
        if any(v["severity"] == "high" for v in violations):
            risk_level = "high"
        elif any(v["severity"] == "medium" for v in violations):
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "blocked": blocked,
            "violations": violations,
            "risk_level": risk_level,
            "checked_rules": [r["id"] for r in self.rules],
        }

    def _safe_result(self) -> Dict:
        return {"blocked": False, "violations": [], "risk_level": "none", "checked_rules": []}

    def test_rule(self, content: str, rule_code: Optional[str] = None) -> Dict:
        """
        测试规则：查看给定内容会命中哪些规则（供管理后台使用）

        Args:
            content: 测试文本
            rule_code: 可选，仅测试指定规则
        """
        rules_to_test = [r for r in self.rules if not rule_code or r["id"] == rule_code]
        hits = []
        for rule in rules_to_test:
            if rule["type"] in ("keyword", "regex"):
                matched = self._match_rule(content, rule)
            else:
                # 语义规则走 LLM
                result = self._semantic_check(content, [rule], {})
                matched = result[0]["matched_text"] if result else None
            hits.append({
                "rule_code": rule["id"],
                "rule_name": rule["name"],
                "rule_type": rule["type"],
                "severity": rule["severity"],
                "action": rule["action"],
                "hit": matched is not None,
                "matched_text": matched,
            })
        return {"content": content, "hits": hits, "total_rules_tested": len(rules_to_test)}


# 全局单例
_checker_instance: Optional[ComplianceChecker] = None


def get_checker() -> ComplianceChecker:
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = ComplianceChecker()
    return _checker_instance
