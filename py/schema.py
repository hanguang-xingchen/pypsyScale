"""scale.json（schema v2）结构校验 + 解读表连续性校验。

设计要点（对应 psyScale 迁移过来的两类历史问题）：
1. 命中语义必须显式声明（closed / half_open），不允许"没命中就返回最后一档"的静默兜底。
2. 解读表必须无缝、无重叠、完整覆盖值域，导入期与运行期都校验，不合规直接抛错。

纯标准库，浏览器（Pyodide）与本地 CPython 共用同一份实现。
"""
from __future__ import annotations

SUPPORTED_SCHEMA = 2
INTERVALS = ("closed", "half_open")
METHODS = ("sum", "dimension_sum")
REQUIRED_LANGS = ("zh-CN", "zh-TW")

REQUIRED_TOP_KEYS = (
    "schema", "id", "title", "description", "instruction",
    "items", "scoring", "bands",
)
REQUIRED_BAND_KEYS = ("min", "max", "color", "level", "advice")


class ScaleSchemaError(ValueError):
    """量表声明不合规：宁可不给结果，也不要给出一个看起来正常的错误等级。"""


def _check_localized(value, what, langs=REQUIRED_LANGS):
    if not isinstance(value, dict):
        raise ScaleSchemaError(f"{what} 必须是 {{语言码: 文本}} 结构，实际为 {type(value).__name__}")
    missing = [lg for lg in langs if not value.get(lg)]
    if missing:
        raise ScaleSchemaError(f"{what} 缺少语言版本：{', '.join(missing)}")


def validate(scale, *, score_min=None, score_max=None, step=None):
    """校验量表声明。

    score_min / score_max / step 用于检查解读表是否完整覆盖可能分数值域。
    对 sum 计分的整数总分：step=1，值域为各题最小分之和 ~ 最大分之和。
    对连续量（如因子均分）：step 传 None，只检查无缝与不重叠。
    """
    if scale.get("schema") != SUPPORTED_SCHEMA:
        raise ScaleSchemaError(f"schema 版本不支持：期望 {SUPPORTED_SCHEMA}，实际 {scale.get('schema')!r}")

    for key in REQUIRED_TOP_KEYS:
        if key not in scale:
            raise ScaleSchemaError(f"缺少必需字段：{key}")

    for what, key in (("title", "title"), ("description", "description"), ("instruction", "instruction")):
        _check_localized(scale[key], what)

    scoring = scale["scoring"]
    if scoring.get("method") not in METHODS:
        raise ScaleSchemaError(f"未知计分方法：{scoring.get('method')!r}")
    interval = scoring.get("interval")
    if interval not in INTERVALS:
        raise ScaleSchemaError(f"scoring.interval 必须是 {INTERVALS} 之一，实际 {interval!r}")
    
    # dimension_sum 必须有 factors 字段
    if scoring.get("method") == "dimension_sum":
        if "factors" not in scale:
            raise ScaleSchemaError("dimension_sum 计分方法必须有 factors 字段")
        factors = scale["factors"]
        if not isinstance(factors, list) or len(factors) == 0:
            raise ScaleSchemaError("factors 必须是非空数组")
        for i, factor in enumerate(factors):
            if "code" not in factor:
                raise ScaleSchemaError(f"factors[{i}] 缺少 code 字段")
            if "name" not in factor:
                raise ScaleSchemaError(f"factors[{i}] 缺少 name 字段")
            if "expectedCount" not in factor:
                raise ScaleSchemaError(f"factors[{i}] 缺少 expectedCount 字段")
            _check_localized(factor["name"], f"factors[{i}].name")

    bands = scale["bands"]
    if not bands:
        raise ScaleSchemaError("bands 不能为空")

    for i, band in enumerate(bands):
        for key in REQUIRED_BAND_KEYS:
            if key not in band:
                raise ScaleSchemaError(f"bands[{i}] 缺少 {key}")
        if band["min"] > band["max"]:
            raise ScaleSchemaError(f"bands[{i}] 的 min 大于 max")
        _check_localized(band["level"], f"bands[{i}].level")
        _check_localized(band["advice"], f"bands[{i}].advice")

    ordered = sorted(bands, key=lambda b: b["min"])
    if ordered != bands:
        raise ScaleSchemaError("bands 必须按 min 升序排列")

    for prev, nxt in zip(bands, bands[1:]):
        if interval == "closed":
            if step is None:
                if nxt["min"] <= prev["max"]:
                    raise ScaleSchemaError(f"bands 重叠：{prev['max']} 与 {nxt['min']}")
            elif nxt["min"] != prev["max"] + step:
                raise ScaleSchemaError(
                    f"闭区间解读表出现缝隙或重叠：[{prev['min']}, {prev['max']}] 之后应接 "
                    f"min={prev['max'] + step}，实际 min={nxt['min']}"
                )
        else:  # half_open：下一档应正好从上一档的 max 起
            if nxt["min"] != prev["max"]:
                raise ScaleSchemaError(
                    f"半开区间解读表出现缝隙或重叠：[{prev['min']}, {prev['max']}) 之后应接 "
                    f"min={prev['max']}，实际 min={nxt['min']}"
                )

    if score_min is not None and bands[0]["min"] > score_min:
        raise ScaleSchemaError(f"值域下界未覆盖：可能最低分 {score_min}，首档 min={bands[0]['min']}")
    if score_max is not None:
        last = bands[-1]
        # 最后一档可以是闭区间（包含 max），也可以是半开区间（但 max 必须 >= score_max）
        limit = last["max"]
        if score_max > limit:
            raise ScaleSchemaError(f"值域上界未覆盖：可能最高分 {score_max}，末档 max={last['max']}")

    return True


def find_band(score, bands, *, interval="closed"):
    """按声明的区间语义命中解读档位。命中不了就抛错，绝不静默返回最后一档。

    half_open 下除末档外均为 [min, max)；末档按闭区间 [min, max] 处理，
    否则值域上界（如因子均分 5.0）永远落不进最后半开档。
    """
    last_i = len(bands) - 1
    for i, band in enumerate(bands):
        if interval == "closed" or (interval == "half_open" and i == last_i):
            if band["min"] <= score <= band["max"]:
                return i, band
        else:
            if band["min"] <= score < band["max"]:
                return i, band
    raise ScaleSchemaError(
        f"分数 {score} 未落入任何解读档位（interval={interval}）；"
        "这是量表声明的值域覆盖问题，必须修配置而不是兜底猜一档。"
    )
