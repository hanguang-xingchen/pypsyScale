"""Plotly 出图（Python 侧正式 import plotly，按既定选型）。

M1 只要求证明两件事：
1. plotly 能在 Pyodide 里 micropip 装上并构造 figure；
2. figure 能序列化成 JSON，交给页面侧 plotly.js 渲染。

雷达图（SCL-90 Scatterpolar）属于 M2，这里先不放，避免一次改太多变量。
"""
from __future__ import annotations


class ChartError(RuntimeError):
    pass


def _require_plotly():
    try:
        import plotly.graph_objects as go  # noqa: F401  (在 Pyodide 里由 micropip 提供)
    except Exception as exc:  # pragma: no cover - 环境缺包时的可读报错
        raise ChartError(
            "plotly 不可用：浏览器里需先 micropip.install('plotly')，"
            f"本地需 pip install plotly。原始错误：{exc}"
        ) from exc
    import plotly.graph_objects as go
    return go


def item_bar_figure(result, items, *, t, lang_labels):
    """逐题得分柱状图：hover 出题目原文 + 所选选项文本。"""
    go = _require_plotly()

    labels, values, hovers, colors = [], [], [], []
    for item, value in zip(items, result.answers):
        labels.append(f"Q{item.q_id}")
        values.append(value)
        option_text = item.option_text(value)
        hovers.append(
            f"<b>第 {item.q_id} 题</b><br>{item.text}<br>"
            f"{lang_labels['answered']}: {option_text}（{value}）"
        )
        colors.append(result.color if value >= max(o.value for o in item.options) * 0.66 else "#f9a8d4")

    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=values,
                marker_color=colors,
                hovertext=hovers,
                hoverinfo="text",
                hoverlabel=dict(align="left"),
            )
        ]
    )
    fig.update_layout(
        title=t("chart_item_title", lang=result.language),
        xaxis_title=t("chart_item_axis", lang=result.language),
        yaxis_title=t("chart_item_score", lang=result.language),
        yaxis=dict(range=[0, max(max(o.value for o in it.options) for it in items) + 0.5]),
        margin=dict(l=40, r=20, t=54, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12),
    )
    return fig


def band_position_figure(result, scale, *, t):
    """横向档位条：一眼看出这次分数落在解读表的哪一档。"""
    go = _require_plotly()

    names, mins, widths, colors, current = [], [], [], [], result.band_index
    for band in scale["bands"]:
        names.append(band["level"][result.language])
        mins.append(band["min"])
        widths.append(band["max"] - band["min"] + (1 if scale["scoring"]["interval"] == "closed" else 0))
        colors.append(band["color"])

    fig = go.Figure(
        data=[
            go.Bar(
                x=widths,
                y=names,
                base=mins,
                orientation="h",
                marker_color=colors,
                hovertext=[f"{n}: {b['min']}–{b['max']}" for n, b in zip(names, scale["bands"])],
                hoverinfo="text",
            )
        ]
    )
    fig.update_layout(
        title=t("chart_band_title", lang=result.language),
        barmode="stack",
        xaxis=dict(range=[scale["bands"][0]["min"], scale["bands"][-1]["max"] + 1], showgrid=True),
        height=220,
        margin=dict(l=40, r=20, t=54, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        annotations=[
            dict(
                x=result.report_score,
                y=names[current],
                text=t("chart_here", lang=result.language),
                showarrow=True,
                arrowhead=2,
                ax=0,
                ay=-38,
                font=dict(size=11),
            )
        ],
    )
    return fig


def figure_to_json(fig):
    """序列化成页面侧 Plotly.newPlot(el, figure.data, figure.layout) 可直接消费的形状。"""
    try:
        return fig.to_json()
    except Exception as exc:  # pragma: no cover
        raise ChartError(f"figure 序列化失败：{exc}") from exc


def figure_to_render_payload(fig):
    """不依赖 to_json 的兜底路径：手工拆 data/layout，供 to_json 在 WASM 下异常时使用。"""
    import json

    data = json.loads(json.dumps(fig.data, default=str)) if hasattr(fig, "data") else None
    layout = json.loads(json.dumps(fig.layout, default=str)) if hasattr(fig, "layout") else None
    return {"data": data, "layout": layout}
