"""一次性迁移工具：psyScale 配置 → 本项目 schema v2。

只读项目内副本 vendor/psyscale-ref/，不碰任何外部拉取目录。

产出：
- data/scales/<id>/scale.json      合并简繁两份声明后的单一事实源
- data/scales/<id>/items.<lang>.csv 题目原文逐字保留（不重新排版）
- data/scales/index.json            量表清单
- tests/golden/<id>.json            由解读表自动生成的边界基准用例

同时做跨语言一致性校验：题序、选项数、分值序列、档位 min/max/color 必须完全一致，
不一致就停，不做"看起来差不多就通过"的处理。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py"))

from item_parser import parse_items, score_range  # noqa: E402
from schema import ScaleSchemaError, validate  # noqa: E402

LANGS = ("zh-CN", "zh-TW")
METHOD_MAP = {"sum": "sum", "dimensionSum": "dimension_sum"}


def load_reference(scale_id: str):
    base = ROOT / "vendor" / "psyscale-ref"
    refs = {}
    for lang in LANGS:
        basic = base / f"{scale_id}.basic.{lang}.json"
        items = base / f"{scale_id}.items.{lang}.csv"
        if not basic.exists() or not items.exists():
            raise SystemExit(f"缺少参照文件：{basic} 或 {items}（请先搬到 vendor/psyscale-ref/）")
        refs[lang] = {
            "basic": json.loads(basic.read_text(encoding="utf-8")),
            "csv": items.read_text(encoding="utf-8"),
            "basic_path": str(basic.relative_to(ROOT)),
            "csv_path": str(items.relative_to(ROOT)),
        }
    return refs


def fingerprint_items(items):
    return [(it.q_id, len(it.options), [o.value for o in it.options], it.dimension) for it in items]


def build_scale(scale_id, refs, *, source_commit, raw_factor, review_notes):
    cn, tw = refs["zh-CN"]["basic"], refs["zh-TW"]["basic"]
    parsed = {lang: parse_items(refs[lang]["csv"]) for lang in LANGS}

    # 1) 跨语言题目结构必须一致
    fp_cn, fp_tw = fingerprint_items(parsed["zh-CN"]), fingerprint_items(parsed["zh-TW"])
    if fp_cn != fp_tw:
        diffs = [i for i, (a, b) in enumerate(zip(fp_cn, fp_tw)) if a != b]
        raise SystemExit(f"简繁题目结构不一致（题索引 {diffs[:5]}），停止导入")

    # 2) 分值值域
    total_min, total_max, step = score_range(parsed["zh-CN"])

    # 3) 档位：以简体为骨架，检查繁体的 min/max/color 完全一致后合并文案
    bands_cn, bands_tw = cn["interpretation"], tw["interpretation"]
    if len(bands_cn) != len(bands_tw):
        raise SystemExit("简繁解读表档位数量不一致，停止导入")
    bands = []
    for i, (a, b) in enumerate(zip(bands_cn, bands_tw)):
        if (a["min"], a["max"], a["color"]) != (b["min"], b["max"], b["color"]):
            raise SystemExit(f"第 {i+1} 档的 min/max/color 在简繁之间不一致，停止导入")
        bands.append({
            "min": a["min"],
            "max": a["max"],
            "color": a["color"],
            "level": {"zh-CN": a["level"], "zh-TW": b["level"]},
            "advice": {"zh-CN": a["advice"], "zh-TW": b["advice"]},
        })

    scoring_type = cn.get("scoring", {}).get("type", "sum")
    scale = {
        "schema": 2,
        "id": scale_id,
        "title": {"zh-CN": cn["title"], "zh-TW": tw["title"]},
        "description": {"zh-CN": cn["description"], "zh-TW": tw["description"]},
        "instruction": {"zh-CN": cn["instruction"], "zh-TW": tw["instruction"]},
        "meta": {
            "author": cn.get("author"),
            "year": cn.get("year"),
            "optionCount": len(parsed["zh-CN"][0].options),
        },
        "items": {
            "files": {lang: f"items.{lang}.csv" for lang in LANGS},
            "option_prefix": cn["source"]["optionPrefix"],
            "value_prefix": cn["source"]["valuePrefix"],
            "count": len(parsed["zh-CN"]),
        },
        "scoring": {
            "method": METHOD_MAP.get(scoring_type, scoring_type),
            # 闭区间 + 无缝校验：psyScale 用 score<max 命中却在配置里写成 min..max 连续整数，
            # 导致每档上界落入兜底分支。这里把语义显式写进配置并强制校验。
            "interval": "closed",
            "transform": {"raw_factor": raw_factor, "report_round": 0},
        },
        "bands": bands,
        "flags": [],
        "provenance": {
            "source_project": "psyScale",
            "source_snapshot": "vendor/psyscale-ref",
            "source_commit": source_commit,
            "imported_at": date.today().isoformat(),
            "imported_by": "tools/import_psyscale.py",
            "review_notes": review_notes,
        },
    }

    validate(scale, score_min=total_min, score_max=total_max, step=step)
    return scale, parsed, (total_min, total_max, step)


def gen_golden(scale, parsed, value_range):
    """从解读表结构自动生成边界基准：每档上下界、以及每个边界 ±1。"""
    total_min, total_max, step = value_range
    bands = scale["bands"]
    cases = []

    def answers_for(target, items):
        """用最小分起步、逐题加到最大值的方式凑出尽量接近 target 的答卷。"""
        values = [min(o.value for o in it.options) for it in items]
        caps = [max(o.value for o in it.options) for it in items]
        remaining = target - sum(values)
        for i, cap in enumerate(caps):
            room = int(cap - values[i])
            if remaining <= 0:
                break
            add = min(room, int(remaining))
            values[i] += add
            remaining -= add
        return [int(v) for v in values]

    for i, band in enumerate(bands):
        for probe in {band["min"], band["max"]}:
            cases.append({
                "name": f"band{i}-{probe}",
                "answers": answers_for(probe, parsed["zh-CN"]),
                "expect_band": i,
            })
    # 每个档位边界 ±1，这是最容易错位的点
    for i in range(len(bands) - 1):
        edge = bands[i]["max"]
        for probe in (edge - 1, edge, edge + 1):
            if total_min <= probe <= total_max:
                cases.append({
                    "name": f"edge-{probe}",
                    "answers": answers_for(probe, parsed["zh-CN"]),
                    "expect_band": i if probe <= edge else i + 1,
                })

    # 去重（同一份答卷只留一条）
    seen, unique = set(), []
    for case in cases:
        key = tuple(case["answers"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(case)

    return {
        "scale_id": scale["id"],
        "generated_by": "tools/import_psyscale.py",
        "score_range": [total_min, total_max, step],
        "cases": unique,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", required=True)
    parser.add_argument("--source-commit", default="unknown")
    parser.add_argument("--raw-factor", type=float, default=1.0,
                        help="粗分→报告分换算系数；量表若按标准分解读需显式给出（如 SAS/SDS 的 1.25）")
    parser.add_argument("--note", action="append", default=[], dest="notes")
    args = parser.parse_args()

    refs = load_reference(args.scale)
    scale, parsed, value_range = build_scale(
        args.scale, refs, source_commit=args.source_commit,
        raw_factor=args.raw_factor, review_notes=args.notes,
    )

    out = ROOT / "data" / "scales" / args.scale
    out.mkdir(parents=True, exist_ok=True)
    (out / "scale.json").write_text(json.dumps(scale, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for lang in LANGS:
        (out / f"items.{lang}.csv").write_text(refs[lang]["csv"], encoding="utf-8")

    index_path = ROOT / "data" / "scales" / "index.json"
    ids = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    if args.scale not in ids:
        ids.append(args.scale)
    index_path.write_text(json.dumps(ids, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    golden = gen_golden(scale, parsed, value_range)
    golden_path = ROOT / "tests" / "golden" / f"{args.scale}.json"
    golden_path.parent.mkdir(parents=True, exist_ok=True)
    golden_path.write_text(json.dumps(golden, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[导入] {args.scale}  →  {out.relative_to(ROOT)}")
    print(f"  题目数 {scale['items']['count']}，选项数 {scale['meta']['optionCount']}")
    print(f"  粗分值域 {value_range[0]}–{value_range[1]}（步长 {value_range[2]}），换算系数 {args.raw_factor}")
    print(f"  解读档位 {len(scale['bands'])}，无缝校验通过（interval=closed）")
    print(f"  基准用例 {len(golden['cases'])} 条 → {golden_path.relative_to(ROOT)}")
    if args.notes:
        print("  待人工复核：" + "；".join(args.notes))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScaleSchemaError as exc:
        print(f"[导入失败] {exc}", file=sys.stderr)
        raise SystemExit(2)
