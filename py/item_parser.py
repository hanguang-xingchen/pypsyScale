"""items.csv → 题目模型。

- 选项列数由前缀动态发现（opt_* / val_*），不写死列数。
- 分值用 float 解析（psyScale 用 parseInt，遇到 SAS/SDS 标准分这类小数会截断）。
- 解析交给标准库 csv，遵守 RFC4180，题目文本里可以有逗号和引号。
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field


class ItemDataError(ValueError):
    pass


@dataclass
class Option:
    text: str
    value: float

    def json(self):
        return {"text": self.text, "value": self.value}


@dataclass
class Item:
    q_id: int
    text: str
    dimension: str
    options: list = field(default_factory=list)

    @property
    def allowed_values(self):
        return {opt.value for opt in self.options}

    def option_text(self, value):
        for opt in self.options:
            if opt.value == value:
                return opt.text
        return None

    def json(self):
        return {
            "q_id": self.q_id,
            "text": self.text,
            "dimension": self.dimension,
            "options": [o.json() for o in self.options],
        }


def _number(raw):
    text = (raw or "").strip()
    if text == "":
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise ItemDataError(f"分值不是数字：{raw!r}") from exc
    return int(value) if value.is_integer() else value


def parse_items(csv_text, *, option_prefix="opt_", value_prefix="val_"):
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ItemDataError("CSV 缺少表头")
    if "q_id" not in reader.fieldnames or "text" not in reader.fieldnames:
        raise ItemDataError("CSV 表头必须包含 q_id 与 text")

    opt_cols = [c for c in reader.fieldnames if c.startswith(option_prefix)]
    val_cols = [c for c in reader.fieldnames if c.startswith(value_prefix)]
    # 按前缀后面的序号排序，避免列顺序意外
    opt_cols.sort(key=lambda c: c[len(option_prefix):])
    val_cols.sort(key=lambda c: c[len(value_prefix):])
    if len(opt_cols) != len(val_cols) or not opt_cols:
        raise ItemDataError(f"选项列与分值列数量不一致：{len(opt_cols)} vs {len(val_cols)}")

    items = []
    for row_no, row in enumerate(reader, start=2):
        if not (row.get("q_id") or "").strip():
            continue
        try:
            q_id = int(str(row["q_id"]).strip())
        except ValueError as exc:
            raise ItemDataError(f"第 {row_no} 行 q_id 不是整数：{row['q_id']!r}") from exc

        options = []
        for o_col, v_col in zip(opt_cols, val_cols):
            text = (row.get(o_col) or "").strip()
            value = _number(row.get(v_col))
            if not text and value is None:
                continue  # 该量表选项更少，尾部空列
            if not text or value is None:
                raise ItemDataError(f"第 {row_no} 行选项 {o_col} 与分值 {v_col} 不成对")
            options.append(Option(text=text, value=value))

        if len(options) < 2:
            raise ItemDataError(f"第 {row_no} 行（题 {q_id}）有效选项少于 2 个")

        items.append(Item(
            q_id=q_id,
            text=(row.get("text") or "").strip(),
            dimension=(row.get("dimension") or "").strip(),
            options=options,
        ))

    if not items:
        raise ItemDataError("CSV 没有任何题目数据")

    ids = [it.q_id for it in items]
    if len(set(ids)) != len(ids):
        raise ItemDataError("题目 q_id 有重复")
    if ids != sorted(ids):
        raise ItemDataError("题目 q_id 必须升序")

    return items


def score_range(items):
    """返回 (可能最低总分, 可能最高总分, 总分最小步长)。

    step 取所有题目分值差的最大公约数；整数分值即 step=1。
    """
    import math

    mins, maxs, steps = [], [], []
    for it in items:
        values = [o.value for o in it.options]
        mins.append(min(values))
        maxs.append(max(values))
        distinct = sorted(set(values))
        for a, b in zip(distinct, distinct[1:]):
            steps.append(b - a)

    total_min, total_max = sum(mins), sum(maxs)
    step = 0
    for s in steps:
        step = math.gcd(step, int(round(s * 1000))) if step else int(round(s * 1000))
    step = step / 1000 if step else 1
    return total_min, total_max, step
