"""LangGraph 图 + Agent 单元测试。"""

from core.graph import (
    _rule_based_extract_dimensions,
    _merge_dimensions,
    _calculate_completeness,
    _generate_questions,
)
from prompts.templates import MODULE_DIMENSIONS


class TestDimensionExtraction:

    def test_extract_purpose_with_colon(self):
        dims = MODULE_DIMENSIONS["prompt_refiner"]
        expressed = _rule_based_extract_dimensions(
            "目的是：生成产品文案，推广新产品",
            dims,
        )
        assert "purpose" in expressed

    def test_extract_style_with_colon(self):
        dims = MODULE_DIMENSIONS["prompt_refiner"]
        expressed = _rule_based_extract_dimensions(
            "输出风格：简洁实用，不要太啰嗦",
            dims,
        )
        assert "output_style" in expressed

    def test_extract_time_number(self):
        dims = MODULE_DIMENSIONS["work_arranger"]
        expressed = _rule_based_extract_dimensions(
            "这个项目2周内完成",
            dims,
        )
        assert len(expressed) > 0

    def test_extract_model_name(self):
        dims = MODULE_DIMENSIONS["prompt_refiner"]
        expressed = _rule_based_extract_dimensions(
            "用 Qwen3 模型，style 简洁",
            dims,
        )
        assert "target_model" in expressed

    def test_empty_input(self):
        dims = MODULE_DIMENSIONS["info_retention"]
        expressed = _rule_based_extract_dimensions("hi", dims)
        assert isinstance(expressed, dict)


class TestDimensionMerging:

    def test_merge_preserves_existing(self):
        existing = {"purpose": "写代码", "purpose_confidence": 0.8}
        new = {"output_style": "简洁"}
        merged = _merge_dimensions(existing, new)
        assert merged["purpose"] == "写代码"
        assert merged["output_style"] == "简洁"

    def test_merge_overwrites_lower_confidence(self):
        existing = {"purpose": "模糊描述", "purpose_confidence": 0.3}
        new = {"purpose": "清晰描述", "purpose_confidence": 0.9}
        merged = _merge_dimensions(existing, new)
        assert merged["purpose"] == "清晰描述"


class TestCompleteness:

    def test_empty_score_zero(self):
        expressed = {}
        dims = MODULE_DIMENSIONS["prompt_refiner"]
        score, gaps = _calculate_completeness(expressed, dims)
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
        score, gaps = _calculate_completeness(expressed, dims)
        assert 0.3 < score < 0.8

    def test_full_score(self):
        expressed = {}
        for key in MODULE_DIMENSIONS["info_retention"]:
            expressed[key] = "填好了"
            expressed[f"{key}_confidence"] = 1.0
        dims = MODULE_DIMENSIONS["info_retention"]
        score, gaps = _calculate_completeness(expressed, dims)
        assert score > 0.9


class TestQuestionGeneration:

    def test_generates_three_questions(self):
        _, gaps = _calculate_completeness({}, MODULE_DIMENSIONS["prompt_refiner"])
        questions = _generate_questions(gaps, clarify_round=0, max_q=3)
        assert len(questions) == 3
        assert all("text" in q for q in questions)

    def test_first_round_required_first(self):
        _, gaps = _calculate_completeness({}, MODULE_DIMENSIONS["work_arranger"])
        questions = _generate_questions(gaps, clarify_round=0, max_q=3)
        if questions:
            first_dim = questions[0]["dimension"]
            gap_info = next((g for g in gaps if g["key"] == first_dim), None)
            if gap_info:
                assert gap_info["is_required"]
