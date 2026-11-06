# 故障记录：SCL-90 因子均分 5.0 落不进任何解读档位

- 日期：2026-11-06
- 影响量表：`data/scales/scl-90/scale.json`（全库唯一 `dimension_sum` + `interval: half_open` 的量表）
- 现象：任一因子所有题都答 5 分时，点击「提交」页面无反应，事件循环反复抛
  `ScaleSchemaError: 分数 5.0 未落入任何解读档位（interval=half_open）`。

## 故障原因

`scl-90` 的解读档位为半开区间 `[1,2) [2,3) [3,4) [4,5)`，末档 `[4.0, 5.0)` **不含** 5.0。
而因子均分的理论上限恰好是 5.0（该因子所有题都选最高分），因此满分因子在
`scoring._score_dimension_sum` 调用 `find_band` 时无档可落，按设计直接抛错。

触发门槛低于直觉预期：无需全卷满分，只要任意一个因子（最短的偏执/敌对仅 6 题）全答 5 分即崩。

## 校验为何没拦住

`schema.validate()` 的上界检查对 `half_open` 语义判断有误：

```python
limit = last["max"]
if score_max > limit:      # 5.0 > 5.0 → False → 放行
    raise ...
```

该判断把末档当闭区间处理，与 `find_band` 的 half_open 语义不一致，导致一份
「导入期、运行期两次 validate 都通过，但用户一答满分就必炸」的量表被放进 `data/scales/`。
同类边界缺口也未被单测覆盖：`tests/test_scoring_dimension.py` 只断言了均分 3.0 与 4.0，从未测 5.0。

## 修复方案

1. `py/schema.py` — `find_band` 在 `half_open` 下把**最后一档按闭区间**处理
   `[min, max]`，前面各档仍为 `[min, max)`。连续量分档的末档必须是闭口，才能覆盖值域上界。
2. `py/shell.py` — `submit()` 捕获 `ScaleSchemaError` / `ScoringError` 并走 `render_error()`，
   避免计分层异常逃逸到事件循环后变成「点了没反应」。此前 `route()` 有兜底，但 `submit()`
   经 `asyncio.ensure_future` 启动，不在该 try 块内。

## 教训

- 连续型分数（因子均分）分档，末档必须明确覆盖值域上界；半开区间 `[a, max)` 对 `max` 天然留洞。
- `validate()` 与 `find_band()` 必须共享同一套区间命中语义：一处按闭区间、一处按半开，等于放行必炸配置。
- 端点值（`score_min` / `score_max`）必须进单测，否则区间 bug 只在满分/零分人群身上暴露。