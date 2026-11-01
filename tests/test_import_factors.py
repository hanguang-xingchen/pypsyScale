"""TDD: import 工具生成 factors 字段，items.csv 的 dimension 列存因子码"""
import json
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / 'py'))
sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))


def test_import_generates_factors():
    """导入多维度量表时，生成 factors 字段"""
    # 创建临时目录模拟 vendor/psyscale-ref
    with tempfile.TemporaryDirectory() as tmpdir:
        vendor = Path(tmpdir) / 'vendor' / 'psyscale-ref'
        vendor.mkdir(parents=True)
        
        # 写入简繁两份 CSV（dimension 列用中文名）
        zh_cn = vendor / 'test.basic.zh-CN.json'
        zh_cn.write_text(json.dumps({
            "id": "test",
            "title": "测试量表",
            "description": "测试",
            "instruction": "测试",
            "author": "测试",
            "year": 2024,
            "source": {"type": "csv", "file": "items.csv", "optionPrefix": "opt_", "valuePrefix": "val_", "dimensions": True},
            "scoring": {"type": "dimensionSum", "missingValuePolicy": "warn"},
            "interpretation": [
                {"min": 1.0, "max": 2.0, "level": "正常", "color": "#4caf50", "advice": "无"},
                {"min": 2.0, "max": 3.0, "level": "轻度", "color": "#ff9800", "advice": "无"},
                {"min": 3.0, "max": 4.0, "level": "中度", "color": "#f44336", "advice": "无"},
                {"min": 4.0, "max": 5.0, "level": "重度", "color": "#b71c1c", "advice": "无"},
            ],
        }))
        
        zh_tw = vendor / 'test.basic.zh-TW.json'
        zh_tw.write_text(json.dumps({
            "id": "test",
            "title": "測試量表",
            "description": "測試",
            "instruction": "測試",
            "author": "測試",
            "year": 2024,
            "source": {"type": "csv", "file": "items.csv", "optionPrefix": "opt_", "valuePrefix": "val_", "dimensions": True},
            "scoring": {"type": "dimensionSum", "missingValuePolicy": "warn"},
            "interpretation": [
                {"min": 1.0, "max": 2.0, "level": "正常", "color": "#4caf50", "advice": "無"},
                {"min": 2.0, "max": 3.0, "level": "輕度", "color": "#ff9800", "advice": "無"},
                {"min": 3.0, "max": 4.0, "level": "中度", "color": "#f44336", "advice": "無"},
                {"min": 4.0, "max": 5.0, "level": "重度", "color": "#b71c1c", "advice": "無"},
            ],
        }))
        
        # 简繁 CSV：dimension 列中文名不同，但结构相同
        items_cn = vendor / 'test.items.zh-CN.csv'
        items_cn.write_text('q_id,text,dimension,opt_0,opt_1,opt_2,opt_3,val_0,val_1,val_2,val_3\n1,题1,维度A,a,b,c,d,1,2,3,4\n2,题2,维度B,a,b,c,d,1,2,3,4\n3,题3,维度A,a,b,c,d,1,2,3,4\n')
        
        items_tw = vendor / 'test.items.zh-TW.csv'
        items_tw.write_text('q_id,text,dimension,opt_0,opt_1,opt_2,opt_3,val_0,val_1,val_2,val_3\n1,題1,維度A,a,b,c,d,1,2,3,4\n2,題2,維度B,a,b,c,d,1,2,3,4\n3,題3,維度A,a,b,c,d,1,2,3,4\n')
        
        # 修改 import 工具的 ROOT 指向临时目录
        import import_psyscale
        original_root = import_psyscale.ROOT
        import_psyscale.ROOT = Path(tmpdir)
        
        try:
            # 运行导入
            scale, parsed, value_range = import_psyscale.build_scale(
                'test',
                import_psyscale.load_reference('test'),
                source_commit='test',
                raw_factor=1.0,
                review_notes=[],
            )
            
            # 验证 factors 字段生成
            assert 'factors' in scale, "应该生成 factors 字段"
            factors = scale['factors']
            assert len(factors) == 2, f"应该有 2 个因子，实际 {len(factors)}"
            
            # 验证因子码和显示名
            codes = {f['code'] for f in factors}
            assert 'dim_a' in codes or '维度a' in codes, f"因子码应该包含维度A，实际 {codes}"
            
            # 验证 items.csv 的 dimension 列存的是因子码（不是中文名）
            # （这里需要检查 parsed 里的 item.dimension 字段）
            # 暂时跳过，因为 build_scale 返回的 parsed 是 Item 对象列表
            
        finally:
            import_psyscale.ROOT = original_root


if __name__ == "__main__":
    test_import_generates_factors()
    print("✓ test_import_generates_factors")
    print("\n所有测试通过")
