# 任务拆解：PHQ-9 可行性切片

日期：2026-10-31（23:5x 更新）　对应设计：`docs/design/2026-10-31-pyscript-refactor-design.md`
验证清单：`docs/plans/2026-10-31-browser-verification-checklist.md`

## 已完成

| 阶段 | 任务 | 交付物 | 验收 |
|---|---|---|---|
| M0 | 量表声明 schema v2 | `py/schema.py` | 无缝/重叠/越界/未覆盖四类坏配置各有专测拒绝 |
| M0 | 题目解析 | `py/item_parser.py` | 变长选项、浮点分值、含逗号引号题面、坏 CSV 拒绝 |
| M0 | 计分与解读 | `py/scoring.py` | 0–27 全值域扫描 + 关键边界落档断言 |
| M0 | 文案层 | `py/i18n.py`、`locales/ui.json`（43 键齐平） | 键不齐平构造期抛错；zh-HK 回退繁体 |
| M0 | 报告生成 | `py/report.py` | 报告分档文案与 CSV 表头随语言 |
| M0 | 迁移工具 | `tools/import_psyscale.py` | 跨语言结构不一致即停机，并自动产出边界基准 |
| M0 | 边界基准 | `tests/golden/phq-9.json`（14 条） | 引擎测试逐条命中 |
| M0 | 引擎测试 | `tests/run_tests.py` | 本地 CPython 17 项全绿 |
| M0 | 旧实现对照实验 | 同上 | 复现旧写法把 4/9/14/19 判成末档，证明修的是真问题 |
| M1 | 静态首页 | `index.html` + `css/style.css` | 不加载运行时即可打开 |
| M1 | 单页壳三视图 | `app.html`、`py/{main,shell,dom,draft_store,resources}.py`、`js/shim.js` | 端到端 38 项全绿 |
| M1 | 引擎进 WASM | `tools/verify_pyodide.mjs` | Pyodide 314.0.7 内全值域命中与本地一致 |
| M1 | Plotly 出图 | `py/charts.py` + `tools/verify_plotly_wasm.mjs` | WASM 内 import 255 ms、三图构造 737 ms、序列化 13 ms；雷达 `scatterpolar` 结构正确 |
| M1 | 图表降级 | `py/shell.py` `render_bar_fallback` | plotly 不可用时自动简化条形并显式标注 |
| M1 | 草稿恢复修正 | `py/shell.py` `jump()` | `currentIndex` 每步写回，端到端断言通过 |

## 未完成

| 任务 | 卡在哪 | 下一步 |
|---|---|---|
| PyScript 标签能否按异步执行入口脚本 | 沙箱无浏览器 | 按清单门 1 在真浏览器验证；若 `await outside syntax` 则把 `main.py` 包成 `asyncio.ensure_future` |
| 浏览器内 `micropip install plotly` | 沙箱 Node 出站 HTTP 被重置，只能本地 wheel 挂载证明 plotly 本体 | 真浏览器打开一次结果页即可判定 |
| plotly.js 渲染与版本配对 | 同上 | 清单门 3；shim 锁 3.0.1、Python 侧 7.1.0，需确认配对 |
| 门 2/4/5（刷新恢复、前进后退、Esc 收口） | 逻辑已在假 DOM 证过，真实浏览器行为未证 | 按清单逐条走 |
| 首屏体积与逐题切换延迟 | 需真实网络与设备 | 清单"需要回填的结论"表 |
| SCL-90 多维度与雷达接进壳 | M2 | `dimension_sum` 计分 + `radar_figure` 已可用，接 `scoring.py` |

## 需要你拍板

1. PHQ-9 第 9 题阳性提示的文案与当地心理援助热线信息：需权威来源核实，不用记忆值填。
2. 新仓库许可证，以及 `vendor/psyscale-ref/`（源自 AGPL-3.0）是否随仓库公开。
3. 视觉基线是否长期沿用 psyScale 的粉色系。

---

内容由 AI 生成
