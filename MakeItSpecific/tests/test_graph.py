"""LangGraph 图 + Agent 单元测试 — V2。

测试新架构中的纯函数：维度合并、完整度计算、追问生成、Planner JSON 解析。
V2 移除了正则维度提取（改为 LLM），对应移除正则相关测试。
"""

from core.graph import (
    _merge_dimensions_from_plan,
    _parse_planner_json,
    _parse_reflection_json,
    _fallback_plan,
    _generate_fallback_questions,
    _format_clarification_message,
)
from prompts.templates import (
    MODULE_DIMENSIONS,
    calculate_completeness,
    CLARIFICATION_TEMPLATES,
)


class TestDimensionMerging:
    """V2 维度合并：从 Planner JSON 的 extracted_dimensions 合并到已有维度。"""

    def test_merge_new_dimensions(self):
        existing = {"purpose": "写代码", "purpose_confidence": 0.8}
        extracted = {
            "output_style": {"value": "简洁", "confidence": 0.9},
        }
        merged = _merge_dimensions_from_plan(existing, extracted)
        assert merged["purpose"] == "写代码"
        assert merged["output_style"] == "简洁"
        assert merged["output_style_confidence"] == 0.9

    def test_merge_overwrites_lower_confidence(self):
        existing = {"purpose": "模糊描述", "purpose_confidence": 0.3}
        extracted = {
            "purpose": {"value": "清晰描述", "confidence": 0.9},
        }
        merged = _merge_dimensions_from_plan(existing, extracted)
        assert merged["purpose"] == "清晰描述"
        assert merged["purpose_confidence"] == 0.9

    def test_merge_keeps_higher_confidence(self):
        existing = {"purpose": "已确认描述", "purpose_confidence": 0.95}
        extracted = {
            "purpose": {"value": "新提取但低置信", "confidence": 0.4},
        }
        merged = _merge_dimensions_from_plan(existing, extracted)
        assert merged["purpose"] == "已确认描述"
        assert merged["purpose_confidence"] == 0.95

    def test_merge_with_string_values(self):
        """测试 extracted 中是简单字符串（非 dict）时的兼容处理。"""
        existing = {}
        extracted = {"purpose": "做翻译"}
        merged = _merge_dimensions_from_plan(existing, extracted)
        assert merged["purpose"] == "做翻译"

    def test_merge_skips_null_values(self):
        existing = {}
        extracted = {"purpose": {"value": None, "confidence": 0}}
        merged = _merge_dimensions_from_plan(existing, extracted)
        assert "purpose" not in merged or merged.get("purpose") is None


class TestCompleteness:
    """完整度计算（已移至 prompts/templates.py）。"""

    def test_empty_score_zero(self):
        expressed = {}
        dims = MODULE_DIMENSIONS["prompt_refiner"]
        score, gaps = calculate_completeness(expressed, dims)
        assert score == 0.0
        assert len(gaps) > 0

    def test_partial_score(self):
        expressed = {
            "purpose": "优化提示词",
            "purpose_confidence": 0.9,
            "output_style": "简洁",
            "output_style_confidence": 0.8,
        }
        dims = MODULE_DIMENSIONS["prompt_refiner"]
        score, gaps = calculate_completeness(expressed, dims)
        assert 0.3 < score < 0.8

    def test_full_score(self):
        expressed = {}
        for key in MODULE_DIMENSIONS["info_retention"]:
            expressed[key] = "填好了"
            expressed[f"{key}_confidence"] = 1.0
        dims = MODULE_DIMENSIONS["info_retention"]
        score, gaps = calculate_completeness(expressed, dims)
        assert score > 0.9


class TestFallbackQuestions:
    """V2 追问生成：基于模板的兜底追问。"""

    def test_generates_up_to_three(self):
        dims = MODULE_DIMENSIONS["prompt_refiner"]
        questions = _generate_fallback_questions(
            "prompt_refiner", {}, clarify_round=0, max_q=3
        )
        assert len(questions) <= 3
        assert len(questions) > 0
        assert all("text" in q for q in questions)
        assert all("dimension" in q for q in questions)

    def test_with_existing_dimensions(self):
        """已有部分维度时，追问应该更少。"""
        expressed = {
            "purpose": "已说过了",
            "purpose_confidence": 0.9,
        }
        questions = _generate_fallback_questions(
            "prompt_refiner", expressed, clarify_round=0, max_q=3
        )
        # 因为 purpose 已填，追问中不应包含 purpose
        for q in questions:
            assert q["dimension"] != "purpose"


class TestPlannerJSONParsing:
    """Planner JSON 输出解析。"""

    def test_parse_valid_json(self):
        result = _parse_planner_json('{"is_complete": true, "completeness": 0.9}')
        assert result["is_complete"] is True
        assert result["completeness"] == 0.9

    def test_parse_json_in_code_block(self):
        result = _parse_planner_json('''
```json
{"is_complete": false, "completeness": 0.3, "missing_info": ["需要更多信息"]}
```
''')
        assert result["is_complete"] is False
        assert "missing_info" in result

    def test_parse_malformed_json(self):
        """损坏的 JSON 应返回降级结果。"""
        result = _parse_planner_json("这不是 JSON")
        assert isinstance(result, dict)
        assert "is_complete" in result

    def test_parse_empty_string(self):
        result = _parse_planner_json("")
        assert isinstance(result, dict)
        assert result["is_complete"] is False


class TestReflectionJSONParsing:
    """Reflector JSON 输出解析。"""

    def test_parse_valid(self):
        result = _parse_reflection_json('{"pass": true, "score": 8}')
        assert result["pass"] is True
        assert result["score"] == 8

    def test_parse_fail(self):
        result = _parse_reflection_json('{"pass": false, "score": 3, "issues": ["不完整"]}')
        assert result["pass"] is False

    def test_parse_malformed(self):
        result = _parse_reflection_json("not json")
        assert result["pass"] is True  # 出错时默认通过


class TestFallbackPlan:
    """Planner 降级逻辑。"""

    def test_short_message_triggers_clarify(self):
        plan = _fallback_plan("hi", MODULE_DIMENSIONS["prompt_refiner"])
        assert plan["is_complete"] is False
        assert len(plan.get("clarify_questions", [])) > 0

    def test_long_message_bypasses(self):
        long_msg = "我想用 React 和 Node.js 搭建一个个人博客，技术栈偏好 TypeScript，风格简洁现代，大概一个月左右完成，主要用来写前端技术文章分享和个人项目展示，需要支持 Markdown 编辑和评论功能" * 2
        plan = _fallback_plan(long_msg, MODULE_DIMENSIONS["work_arranger"])
        assert plan["is_complete"] is True


class TestClarificationFormatting:
    """追问消息格式化。"""

    def test_format_with_questions(self):
        questions = [
            {"text": "你的目标是什么？", "dimension": "purpose", "hint": "越具体越好"},
            {"text": "什么时候完成？", "dimension": "time_constraint", "hint": ""},
        ]
        output = _format_clarification_message(questions, 0.3)
        assert "你的目标是什么？" in output
        assert "什么时候完成？" in output
        assert "30%" in output       # progress percentage

    def test_format_includes_progress(self):
        output = _format_clarification_message([], 0.5)
        assert "50%" in output
