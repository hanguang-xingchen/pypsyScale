"""TDD: schema 支持 factors 字段（多维度量表必需）"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'py'))

from schema import validate, ScaleSchemaError


def test_factors_field_required_for_dimension_sum():
    """method=dimension_sum 时，factors 字段必需"""
    scale = {
        "schema": 2,
        "id": "test",
        "title": {"zh-CN": "测试", "zh-TW": "測試"},
        "description": {"zh-CN": "测试", "zh-TW": "測試"},
        "instruction": {"zh-CN": "测试", "zh-TW": "測試"},
        "items": {"files": {}, "option_prefix": "opt_", "value_prefix": "val_", "count": 10},
        "scoring": {"method": "dimension_sum", "interval": "half_open", "transform": {}},
        "bands": [
            {"min": 1.0, "max": 2.0, "color": "#4caf50", "level": {"zh-CN": "正常", "zh-TW": "正常"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 2.0, "max": 3.0, "color": "#ff9800", "level": {"zh-CN": "轻度", "zh-TW": "輕度"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 3.0, "max": 4.0, "color": "#f44336", "level": {"zh-CN": "中度", "zh-TW": "中度"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 4.0, "max": 5.0, "color": "#b71c1c", "level": {"zh-CN": "重度", "zh-TW": "重度"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
        ],
    }
    try:
        validate(scale, score_min=1.0, score_max=5.0, step=None)
        assert False, "应该抛出缺少 factors 字段的错误"
    except ScaleSchemaError as e:
        assert "factors" in str(e)


def test_factors_structure():
    """factors 是数组，每个 factor 有 code/name/expectedCount"""
    scale = {
        "schema": 2,
        "id": "test",
        "title": {"zh-CN": "测试", "zh-TW": "測試"},
        "description": {"zh-CN": "测试", "zh-TW": "測試"},
        "instruction": {"zh-CN": "测试", "zh-TW": "測試"},
        "items": {"files": {}, "option_prefix": "opt_", "value_prefix": "val_", "count": 10},
        "scoring": {"method": "dimension_sum", "interval": "half_open", "transform": {}},
        "bands": [
            {"min": 1.0, "max": 2.0, "color": "#4caf50", "level": {"zh-CN": "正常", "zh-TW": "正常"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 2.0, "max": 5.0, "color": "#f44336", "level": {"zh-CN": "异常", "zh-TW": "異常"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
        ],
        "factors": [
            {"code": "dim1", "name": {"zh-CN": "维度1", "zh-TW": "維度1"}, "expectedCount": 5},
            {"code": "dim2", "name": {"zh-CN": "维度2", "zh-TW": "維度2"}, "expectedCount": 5},
        ],
    }
    validate(scale, score_min=1.0, score_max=5.0, step=None)  # 应该通过


if __name__ == "__main__":
    test_factors_field_required_for_dimension_sum()
    print("✓ test_factors_field_required_for_dimension_sum")
    test_factors_structure()
    print("✓ test_factors_structure")
    print("\n所有测试通过")
