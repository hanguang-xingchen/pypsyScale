"""报告生成：只产出字符串，下载动作留在浏览器侧。

字段语义延续 psyScale 的三种导出（标准报告 / 含答卷明细 / 逐题 CSV），
但表头与文案改为从语言表取，修掉"繁体用户导出到简体表头"的问题。
"""
from __future__ import annotations

import csv
import io
import json
from datetime import date

REPORT_VERSION = 2


def build_report(result, *, with_answers=False, generated=None):
    payload = {
        "version": REPORT_VERSION,
        "date": generated or date.today().isoformat(),
        "scale": result.level and result.scale_id,
        "scaleId": result.scale_id,
        "language": result.language,
        "summary": {
            "rawTotal": result.raw_total,
            "reportScore": result.report_score,
            "mean": result.mean,
            "itemCount": result.item_count,
            "bandIndex": result.band_index,
            "level": result.level,
            "advice": result.advice,
            "color": result.color,
        },
    }
    if result.flags:
        payload["summary"]["flags"] = result.flags
    if with_answers:
        payload["answers"] = result.answers
    return payload


def report_json(result, *, with_answers=False, indent=2, generated=None):
    return json.dumps(
        build_report(result, with_answers=with_answers, generated=generated),
        ensure_ascii=False,
        indent=indent,
    )


def detail_csv(result, items, *, headers, generated=None):
    """逐题明细 CSV：题号 / 题目 / 所选选项 / 分值。headers 由语言表提供。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for item, value in zip(items, result.answers):
        writer.writerow([item.q_id, item.text, item.option_text(value), value])
    return buffer.getvalue()


def filename(kind, scale_id, *, extension, generated=None):
    return f"{scale_id}-{kind}-{generated or date.today().isoformat()}.{extension}"
