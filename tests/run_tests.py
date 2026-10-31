"""引擎测试：本地 CPython 跑，不依赖 pytest、不依赖浏览器。

覆盖四组：
A 迁移与数据完整性   B 计分与解读命中   C 声明校验的拒绝能力   D 报告与文案
另有一组"对照实验"，用 psyScale 线上的命中写法跑同一份分数，证明边界错位不是猜测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py"))

from i18n import Catalog, I18nError, pick_language  # noqa: E402
from item_parser import ItemDataError, parse_items, score_range  # noqa: E402
from report import detail_csv, report_json  # noqa: E402
from schema import ScaleSchemaError, find_band, validate  # noqa: E402
from scoring import ScoringError, score_scale  # noqa: E402

RESULTS = []


def case(name):
    def deco(fn):
        RESULTS.append((name, fn))
        return fn
    return deco


def load_scale(scale_id="phq-9"):
    folder = ROOT / "data" / "scales" / scale_id
    scale = json.loads((folder / "scale.json").read_text(encoding="utf-8"))
    items = parse_items((folder / "items.zh-CN.csv").read_text(encoding="utf-8"))
    return scale, items


def answers_sum(scale, items, total):
    """构造一份总分恰好为 total 的答卷（从最小分起逐题加）。"""
    values = [min(o.value for o in it.options) for it in items]
    caps = [max(o.value for o in it.options) for it in items]
    remaining = total - sum(values)
    for i, cap in enumerate(caps):
        if remaining <= 0:
            break
        add = min(int(cap - values[i]), int(remaining))
        values[i] += add
        remaining -= add
    assert sum(values) == total, f"造不出总分 {total} 的答卷"
    return {it.q_id: values[i] for i, it in enumerate(items)}


# ---------------------------------------------------------------- A 迁移与数据
@case("schema v2 声明通过校验")
def _():
    scale, items = load_scale()
    lo, hi, step = score_range(items)
    assert validate(scale, score_min=lo, score_max=hi, step=step) is True


@case("简繁题目结构一致且分值非整数不被截断")
def _():
    folder = ROOT / "data" / "scales" / "phq-9"
    cn = parse_items((folder / "items.zh-CN.csv").read_text(encoding="utf-8"))
    tw = parse_items((folder / "items.zh-TW.csv").read_text(encoding="utf-8"))
    assert [i.q_id for i in cn] == [i.q_id for i in tw]
    assert [len(i.options) for i in cn] == [len(i.options) for i in tw]
    assert [[o.value for o in i.options] for i in cn] == [[o.value for o in i.options] for i in tw]
    # 小数分值必须原样保留（psyScale 用 parseInt 会截断）
    dec = parse_items('q_id,text,opt_0,opt_1,val_0,val_1\n1,测试,低,高,1.25,2.5\n')
    assert [o.value for o in dec[0].options] == [1.25, 2.5]


@case("题目文本含逗号与引号能正确解析")
def _():
    text = 'q_id,text,opt_0,opt_1,val_0,val_1\n1,"难受，包括想哭","没有,一点",有,0,1\n'
    items = parse_items(text)
    assert items[0].text == "难受，包括想哭"
    assert items[0].options[0].text == "没有,一点"


@case("CSV 结构异常要被拒")
def _():
    for bad in ('q_id,text\n1,无选项\n', 'text,opt_0,val_0\na,x,1\n'):
        try:
            parse_items(bad)
        except (ItemDataError, Exception):
            continue
        raise AssertionError(f"未拒绝坏 CSV：{bad!r}")


# ---------------------------------------------------------------- B 计分与命中
@case("导入生成的 14 条边界基准全部命中期望档位")
def _():
    scale, items = load_scale()
    golden = json.loads((ROOT / "tests" / "golden" / "phq-9.json").read_text(encoding="utf-8"))
    for c in golden["cases"]:
        result = score_scale(scale, items, c["answers"], language="zh-CN")
        assert result.band_index == c["expect_band"], f"{c['name']} 期望档 {c['expect_band']} 实得 {result.band_index}"


@case("0 到满分每个整数总分都能命中，且关键边界档位正确")
def _():
    scale, items = load_scale()
    expect = {0: 0, 4: 0, 5: 1, 9: 1, 10: 2, 14: 2, 15: 3, 19: 3, 20: 4, 27: 4}
    for total in range(0, 28):
        result = score_scale(scale, items, answers_sum(scale, items, total), language="zh-CN")
        assert result.raw_total == total, f"总分 {total} 算成 {result.raw_total}"
        if total in expect:
            assert result.band_index == expect[total], f"总分 {total} 应落档 {expect[total]}，实得 {result.band_index}"


@case("旧命中写法会把每档上界判成末档（对照实验）")
def _():
    scale, items = load_scale()
    bands = scale["bands"]

    def legacy_find(score):  # 复刻 psyScale scorer.js 的命中写法
        for index, band in enumerate(bands):
            if score >= band["min"] and score < band["max"]:
                return index
        return len(bands) - 1

    # 4 / 9 / 14 / 19 都落在"上一档的 max"上，旧写法全部穿透到兜底末档
    for total, expect in ((4, 0), (9, 1), (14, 2), (19, 3)):
        assert legacy_find(total) == 4, f"对照前提不成立：旧写法在 {total} 分没有走到末档"
        mine = score_scale(scale, items, answers_sum(scale, items, total), language="zh-CN").band_index
        assert mine == expect, f"新引擎在 {total} 分应落档 {expect}，实得 {mine}"
    # 满分 27 要能被正常命中，而不是靠兜底
    assert score_scale(scale, items, answers_sum(scale, items, 27), language="zh-CN").band_index == 4


@case("粗分换算系数生效（预演 SAS/SDS 的标准分路径）")
def _():
    # 合成一个 SAS 形状的量表：20 题、每题 1-4 分，粗分 20-80，报告分 = 粗分 × 1.25
    header = "q_id,text," + ",".join(f"opt_{i}" for i in range(4)) + "," + ",".join(f"val_{i}" for i in range(4))
    rows = "\n".join(f"{q},题{q},没有,偶尔,经常,一直,1,2,3,4" for q in range(1, 21))
    items = parse_items(f"{header}\n{rows}\n")

    scale = {
        "schema": 2,
        "id": "synthetic-sas",
        "title": {"zh-CN": "合成", "zh-TW": "合成"},
        "description": {"zh-CN": "合成", "zh-TW": "合成"},
        "instruction": {"zh-CN": "合成", "zh-TW": "合成"},
        "items": {"files": {}, "option_prefix": "opt_", "value_prefix": "val_", "count": 20},
        "scoring": {"method": "sum", "interval": "closed",
                    "transform": {"raw_factor": 1.25, "report_round": 0}},
        "bands": [
            {"min": 20, "max": 49, "color": "#4caf50",
             "level": {"zh-CN": "正常", "zh-TW": "正常"},
             "advice": {"zh-CN": "无", "zh-TW": "無"}},
            {"min": 50, "max": 100, "color": "#f44336",
             "level": {"zh-CN": "偏高", "zh-TW": "偏高"},
             "advice": {"zh-CN": "无", "zh-TW": "無"}},
        ],
        "flags": [],
    }
    lo, hi, _step = score_range(items)
    validate(scale, score_min=int(lo * 1.25), score_max=int(hi * 1.25), step=1)

    assert score_scale(scale, items, [1] * 20, language="zh-CN").report_score == 25  # 粗分 20
    raw_39 = [2] * 19 + [1]
    raw_40 = [2] * 20
    assert sum(raw_39) == 39 and sum(raw_40) == 40

    low = score_scale(scale, items, raw_39, language="zh-CN")
    assert low.raw_total == 39 and low.report_score == 49 and low.band_index == 0

    high = score_scale(scale, items, [2] * 19 + [2], language="zh-CN")
    assert high.raw_total == 40 and high.report_score == 50 and high.band_index == 1


@case("缺失作答与非法分值必须报错")
def _():
    scale, items = load_scale()
    answers = answers_sum(scale, items, 10)
    answers.pop(3)
    try:
        score_scale(scale, items, answers, language="zh-CN")
    except ScoringError as exc:
        assert "未答题" in str(exc)
    else:
        raise AssertionError("缺答未被拒绝")
    try:
        score_scale(scale, items, answers_sum(scale, items, 10) | {1: 99}, language="zh-CN")
    except ScoringError:
        pass
    else:
        raise AssertionError("非法分值未被拒绝")


@case("第 9 题阳性规则可被检测（flags 通道）")
def _():
    scale, items = load_scale()
    variant = json.loads(json.dumps(scale))
    variant["flags"] = [{"item": 9, "gte": 1, "key": "self_harm"}]
    with_flag = {it.q_id: (1 if it.q_id == 9 else 0) for it in items}
    without = {it.q_id: (0) for it in items}
    assert score_scale(variant, items, with_flag, language="zh-CN").flags == ["self_harm"]
    assert score_scale(variant, items, without, language="zh-CN").flags == []


# ---------------------------------------------------------------- C 声明校验
@case("解读表有缝必须拒")
def _():
    scale, items = load_scale()
    broken = json.loads(json.dumps(scale))
    broken["bands"][1]["min"] = 6  # 5→6，留下 5 的空隙
    lo, hi, step = score_range(items)
    try:
        validate(broken, score_min=lo, score_max=hi, step=step)
    except ScaleSchemaError:
        return
    raise AssertionError("缝隙未被发现")


@case("解读表重叠必须拒")
def _():
    scale, items = load_scale()
    broken = json.loads(json.dumps(scale))
    broken["bands"][1]["min"] = 4  # 与首档 0-4 重叠
    lo, hi, step = score_range(items)
    try:
        validate(broken, score_min=lo, score_max=hi, step=step)
    except ScaleSchemaError:
        return
    raise AssertionError("重叠未被发现")


@case("值域上界未覆盖必须拒")
def _():
    scale, items = load_scale()
    broken = json.loads(json.dumps(scale))
    broken["bands"][-1]["max"] = 20
    lo, hi, step = score_range(items)
    try:
        validate(broken, score_min=lo, score_max=hi, step=step)
    except ScaleSchemaError:
        return
    raise AssertionError("未覆盖上界却通过了校验")


@case("命中不到时抛错而不是静默返回最后一档")
def _():
    scale, items = load_scale()
    try:
        find_band(999, scale["bands"], interval="closed")
    except ScaleSchemaError:
        return
    raise AssertionError("越界分数被静默兜底了")


# ---------------------------------------------------------------- D 报告与文案
@case("报告 JSON 与逐题 CSV 跟随语言，不再是固定简体表头")
def _():
    scale, items = load_scale()
    result = score_scale(scale, items, answers_sum(scale, items, 15), language="zh-TW")
    payload = json.loads(report_json(result, with_answers=True, generated="2026-10-31"))
    assert payload["summary"]["level"] == "中重度抑鬱"
    assert payload["answers"] == result.answers
    csv_text = detail_csv(
        result, items,
        headers=["題號", "題目", "選項", "分數"],
        generated="2026-10-31",
    )
    assert csv_text.splitlines()[0].startswith("題號")
    assert "第" not in csv_text.splitlines()[0]


@case("语言表键不齐平必须拒")
def _():
    try:
        Catalog({"zh-CN": {"a": "甲"}, "zh-TW": {}})
    except I18nError:
        return
    raise AssertionError("缺键未被发现")


@case("语言选择显式且可回退")
def _():
    assert pick_language("zh-TW") == "zh-TW"
    assert pick_language("zh-HK") == "zh-TW"
    assert pick_language(None) == "zh-CN"
    try:
        pick_language("en")
    except I18nError:
        return
    raise AssertionError("不支持的语言应被拒绝")


def main():
    failed = 0
    for name, fn in RESULTS:
        try:
            fn()
            print(f"  ✓ {name}")
        except Exception as exc:
            failed += 1
            print(f"  ✗ {name}\n      {type(exc).__name__}: {exc}")
    print(f"\n共 {len(RESULTS)} 项，失败 {failed} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
