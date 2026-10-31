# 任务拆解：PHQ-9 可行性切片

日期：2026-10-31　对应设计：`docs/design/2026-10-31-pyscript-refactor-design.md`

## 已完成（M0）

| 任务 | 交付物 | 验收方式 |
|---|---|---|
| 量表声明 schema v2 | `py/schema.py` | 无缝/重叠/越界四类坏配置各有专测拒绝 |
| 题目解析 | `py/item_parser.py` | 变长选项、浮点分值、含逗号引号题面、坏 CSV 拒绝 |
| 计分与解读 | `py/scoring.py` | 0–27 全值域扫描 + 关键边界落档断言 |
| 文案层 | `py/i18n.py`、`locales/ui.json` | 简繁键必须齐平；zh-HK 回退到繁体 |
| 报告生成 | `py/report.py` | 报告分档文案随语言；CSV 表头随语言 |
| 迁移工具 | `tools/import_psyscale.py` | 跨语言结构不一致即停机，并产出基准 |
| 边界基准 | `tests/golden/phq-9.json`（14 条） | 由解读表自动生成，随迁移重生成 |
| 引擎测试 | `tests/run_tests.py`（17 项） | 本地 CPython 全绿 |
| 旧实现对照实验 | 同上「旧命中写法会把每档上界判成末档」一项 | 证明修正的是真问题而非臆测 |

## 进行中（M1）

| 任务 | 状态 |
|---|---|
| WASM 内跑通同一份引擎 | **已通过**：Pyodide 314.0.7 内 PHQ-9 全值域命中与本地一致（`tools/verify_pyodide.mjs`） |
| WASM 内 `micropip install plotly` + 构造 figure + 序列化 JSON | **卡住**：本环境 Node 直连 CDN 被重置（`fetch failed / ECONNRESET`），需在放行网络的环境重跑 |
| `app.html` 单页壳（须知/答题/结果三视图 + hash 路由） | 未开始 |
| `py/draft_store.py`（Pyodide 侧 IndexedDB 草稿/结果） | 未开始 |
| `js/shim.js`（Plotly 挂载、Blob 下载、dialog 收口） | 未开始 |
| 三道实测门（刷新恢复 / 结果页刷新 / 返回再前进） | 未开始 |
| 首屏体积、逐题切换延迟、内存实测 | 未开始 |

## 待定项（需要用户拍板）

1. PHQ-9 第 9 题阳性（≥1）的求助提示文案与当地心理援助热线信息 —— 需权威来源核实后再写，不用记忆值填。
2. 新仓库许可证选择，以及 `vendor/psyscale-ref/`（源自 AGPL-3.0 仓库）是否随仓库公开。
3. 视觉基线是否沿用 psyScale 的 `css/style.css`。

## 下一批顺序建议

plotly 链路补验 → 单页壳三视图 → 草稿持久化 → 三道门实测 → 体积与延迟实测 → 出 M1 结论。

---

内容由 AI 生成
