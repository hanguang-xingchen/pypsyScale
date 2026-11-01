"""TDD: dimension_sum 计分逻辑"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'py'))

from scoring import score_scale
from item_parser import parse_items


def test_dimension_sum_basic():
    """多维度量表按因子分组计分"""
    # 构造一个简化的多维度量表（2个因子，每个因子2题）
    scale = {
        "schema": 2,
        "id": "test-multi",
        "title": {"zh-CN": "测试多维度", "zh-TW": "測試多維度"},
        "description": {"zh-CN": "测试", "zh-TW": "測試"},
        "instruction": {"zh-CN": "测试", "zh-TW": "測試"},
        "meta": {"author": "测试", "year": 2024, "optionCount": 5},
        "items": {
            "files": {"zh-CN": "items.zh-CN.csv", "zh-TW": "items.zh-TW.csv"},
            "option_prefix": "opt_",
            "value_prefix": "val_",
            "count": 4,
        },
        "scoring": {
            "method": "dimension_sum",
            "interval": "half_open",
            "transform": {"raw_factor": 1.0, "report_round": 0},
        },
        "bands": [
            {"min": 1.0, "max": 2.0, "color": "#4caf50", "level": {"zh-CN": "正常", "zh-TW": "正常"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 2.0, "max": 3.0, "color": "#ff9800", "level": {"zh-CN": "轻度", "zh-TW": "輕度"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 3.0, "max": 4.0, "color": "#f44336", "level": {"zh-CN": "中度", "zh-TW": "中度"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 4.0, "max": 5.0, "color": "#b71c1c", "level": {"zh-CN": "重度", "zh-TW": "重度"}, "advice": {"zh-CN": "无", "zh-TW": "無"}},
        ],
        "factors": [
            {"code": "dim_a", "name": {"zh-CN": "维度A", "zh-TW": "維度A"}, "expectedCount": 2},
            {"code": "dim_b", "name": {"zh-CN": "维度B", "zh-TW": "維度B"}, "expectedCount": 2},
        ],
        "flags": [],
    }
    
    # 4道题，每题5个选项（1-5分）
    csv_text = """q_id,text,dimension,opt_0,opt_1,opt_2,opt_3,opt_4,val_0,val_1,val_2,val_3,val_4
1,题1,dim_a,没有,很轻,中等,偏重,严重,1,2,3,4,5
2,题2,dim_a,没有,很轻,中等,偏重,严重,1,2,3,4,5
3,题3,dim_b,没有,很轻,中等,偏重,严重,1,2,3,4,5
4,题4,dim_b,没有,很轻,中等,偏重,严重,1,2,3,4,5
"""
    items = parse_items(csv_text)
    
    # 答题：dim_a 两题都选3分（中等），dim_b 两题都选4分（偏重）
    answers = {1: 3, 2: 3, 3: 4, 4: 4}
    
    result = score_scale(scale, items, answers, language="zh-CN")
    
    # 验证结果
    assert result.method == "dimension_sum"
    assert result.raw_total == 14  # 3+3+4+4
    assert result.mean == 3.5  # 14/4
    
    # 验证因子分数
    assert len(result.dimensions) == 2
    dim_a = next(d for d in result.dimensions if d["code"] == "dim_a")
    dim_b = next(d for d in result.dimensions if d["code"] == "dim_b")
    
    assert dim_a["score"] == 6  # 3+3
    assert dim_a["mean"] == 3.0  # 6/2
    assert dim_a["level"] == "中度"
    
    assert dim_b["score"] == 8  # 4+4
    assert dim_b["mean"] == 4.0  # 8/2
    assert dim_b["level"] == "重度"


if __name__ == "__main__":
    test_dimension_sum_basic()
    print("✓ test_dimension_sum_basic")
    print("\n所有测试通过")
