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


def radar_figure(dims, *, labels, values, levels=None, colors=None, min_value=1.0, max_value=5.0,
                 threshold=None, title=None, hover_suffix=''):
    """极坐标雷达：M2 的 SCL-90 十维图，提前在 WASM 里验证可行性。

    dims/labels：维度名；values：各维因子均分；levels：各维等级文本（进 hover）。
    闭合用首点重复；阈值环是一条恒定半径的虚线，不参与填充。
    """
    go = _require_plotly()
    n = len(labels)
    if n < 3:
        raise ChartError(f"雷达图至少需要 3 个维度，实际 {n}")
    if not (len(values) == n and (levels is None or len(levels) == n)):
        raise ChartError("labels / values / levels 长度必须一致")

    theta = list(labels) + [labels[0]]
    r = [float(v) for v in values] + [float(values[0])]
    hover = [f"<b>{lab}</b><br>{val:.2f}{hover_suffix}"
             + (f"<br>{levels[i]}" if levels else "<extra></extra>")
             for i, (lab, val) in enumerate(zip(labels, values))]
    hover.append(hover[0])

    data = [
        go.Scatterpolar(
            r=r, theta=theta, mode='lines+markers', fill='toself',
            name=title or '', marker=dict(size=7),
            line=dict(color='#f472b6', width=2),
            fillcolor='rgba(244,114,182,0.15)',
            hovertext=hover, hoverinfo='text',
        )
    ]
    if threshold is not None:
        data.append(go.Scatterpolar(
            r=[threshold] * (n + 1), theta=theta, mode='lines',
            name='阈值', line=dict(color='#9ca3af', width=1, dash='dot'), hoverinfo='skip',
        ))

    fig = go.Figure(data=data)
    fig.update_layout(
        polar=dict(
            radialaxis=dict(range=[min_value, max_value], dtick=1, gridcolor='#f3d3e2'),
            angularaxis=dict(gridcolor='#f3d3e2'),
        ),
        showlegend=False,
        margin=dict(l=54, r=54, t=44, b=44),
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=11),
    )
    if colors:
        fig.data[0].marker.color = '#f472b6'  # 单色描边保持与主题一致，等级色走 hover
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
