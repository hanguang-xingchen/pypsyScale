"""计分与解读引擎（纯函数，不碰 DOM、不碰存储）。

这套模块同时跑在三个地方，行为必须完全一致：
本地 CPython（测试）/ Pyodide WASM（浏览器实验版）/ 未来的真实后端。
所以这里不允许出现任何 js / pyscript / 浏览器 API。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from schema import find_band, validate
from item_parser import score_range


class ScoringError(ValueError):
    pass


@dataclass
class ScoreResult:
    scale_id: str
    method: str
    language: str
    raw_total: float
    report_score: float
    mean: float
    band_index: int
    band: dict
    item_count: int
    answers: list = field(default_factory=list)
    flags: list = field(default_factory=list)
    dimensions: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def level(self):
        return self.band["level"][self.language]

    @property
    def advice(self):
        return self.band["advice"][self.language]

    @property
    def color(self):
        return self.band["color"]

    def json(self):
        return {
            "scale_id": self.scale_id,
            "method": self.method,
            "language": self.language,
            "raw_total": self.raw_total,
            "report_score": self.report_score,
            "mean": self.mean,
            "item_count": self.item_count,
            "band_index": self.band_index,
            "level": self.level,
            "advice": self.advice,
            "color": self.color,
            "flags": self.flags,
            "answers": self.answers,
            "dimensions": self.dimensions,
            "extra": self.extra,
        }


def _normalize_answers(scale, items, answers):
    """允许 dict{q_id: value} 或 list（按题序）两种入参，统一成 {q_id: value}。"""
    ids = [it.q_id for it in items]
    by_id = {}
    if isinstance(answers, dict):
        for key, value in answers.items():
            by_id[int(key)] = value
    elif isinstance(answers, (list, tuple)):
        if len(answers) != len(ids):
            raise ScoringError(f"答卷长度 {len(answers)} 与题目数 {len(ids)} 不一致")
        by_id = {qid: value for qid, value in zip(ids, answers)}
    else:
        raise ScoringError("answers 必须是 dict 或按题序的 list")

    missing = [qid for qid in ids if qid not in by_id]
    if missing:
        raise ScoringError(f"存在未答题：{missing}")

    item_by_id = {it.q_id: it for it in items}
    for qid, value in by_id.items():
        allowed = item_by_id[qid].allowed_values
        if value is None or float(value) not in {float(v) for v in allowed}:
            raise ScoringError(f"第 {qid} 题的分值 {value!r} 不在允许集合 {sorted(allowed)} 内")
        by_id[qid] = float(value)
    return by_id


def _apply_transform(raw_total, transform):
    factor = float(transform.get("raw_factor", 1.0))
    digits = transform.get("report_round", 0)
    score = raw_total * factor
    if isinstance(score, float) and score.is_integer():
        score = int(score)
    return round(score, digits) if digits else int(round(score, 0))


def _detect_flags(scale, answers_by_id):
    hit = []
    for rule in scale.get("flags", []):
        qid = int(rule["item"])
        value = answers_by_id.get(qid)
        if value is None:
            continue
        if "gte" in rule and value >= float(rule["gte"]):
            hit.append(rule["key"])
        elif "equals" in rule and value == float(rule["equals"]):
            hit.append(rule["key"])
    return hit


def score_scale(scale, items, answers, *, language="zh-CN", check_schema=True):
    """按 scale.scoring 声明计分并命中解读档位。"""
    if language not in scale["title"]:
        raise ScoringError(f"量表缺少 {language} 语言版本")

    if check_schema:
        total_min, total_max, step = score_range(items)
        validate(scale, score_min=total_min, score_max=total_max, step=step)

    method = scale["scoring"]["method"]
    if method != "sum":
        raise ScoringError(f"本版切片只实现 sum，dimension_sum 属于下一里程碑：{method}")

    interval = scale["scoring"]["interval"]
    by_id = _normalize_answers(scale, items, answers)
    raw_total = sum(by_id[it.q_id] for it in items)
    transform = scale["scoring"].get("transform", {})
    report_score = _apply_transform(raw_total, transform)

    band_index, band = find_band(report_score, scale["bands"], interval=interval)

    ordered = [by_id[it.q_id] for it in items]
    if all(float(v).is_integer() for v in ordered):
        ordered = [int(v) for v in ordered]

    return ScoreResult(
        scale_id=scale["id"],
        method=method,
        language=language,
        raw_total=int(raw_total) if float(raw_total).is_integer() else raw_total,
        report_score=report_score,
        mean=round(raw_total / len(items), 2),
        band_index=band_index,
        band=band,
        item_count=len(items),
        answers=ordered,
        flags=_detect_flags(scale, by_id),
        extra={"interval": interval, "raw_factor": float(transform.get("raw_factor", 1.0))},
    )
