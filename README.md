# pypsyScale（psyScale 的 PyScript 重构实验）

把 psyScale 的「配置 → 计分 → 解读 → 图表」链路重做成浏览器内 Python（Pyodide/WASM）运行的实验项目。
首版只切一个最简量表（PHQ-9）验证可行性，可行再扩量。

## 现在能跑什么

```bash
npm install
npm run test:engine         # 引擎单元测试，17 项，纯本地 CPython，不需要浏览器
npm run test:shell          # 壳层端到端冒烟：假 DOM + fake-indexeddb + 真 Pyodide，38 项
npm run verify:plotly-wasm  # 在 WASM 里装 plotly 并构造 figure（需 cache/wheels/*.whl）
npm run serve               # 起本地服务，真浏览器打开 http://localhost:8080/index.html

python3 tools/import_psyscale.py --scale <id> --source-commit <sha>   # 从 vendor/psyscale-ref 迁移量表
```

`cache/wheels` 不入库。取包（PyPI 官方源在本沙箱极慢，用镜像）：

```bash
mkdir -p cache/wheels && cd cache/wheels
curl -sSL -O https://mirrors.aliyun.com/pypi/packages/e5/7d/905a3a3d51087515719058c94cfbda2ff0fc14417c20d557ae3e82d8b250/plotly-7.1.0-py3-none-any.whl
```
（narwhals、packaging、micropip 同理，从 `https://mirrors.aliyun.com/pypi/simple/<包名>/` 里取 py3-none-any wheel）

## 目录

| 路径 | 作用 |
|---|---|
| `index.html` | 静态首页，不加载运行时，秒开 |
| `app.html` | PyScript 单页壳：须知 / 答题 / 结果 三视图，hash 路由 |
| `py/` | 纯 Python 引擎与壳逻辑；引擎模块不含任何 js/pyscript 调用，本地、WASM、未来后端共用 |
| `js/shim.js` | 浏览器能力桥：IndexedDB→Promise、Plotly 挂载、Blob 下载、对话框收口 |
| `css/style.css` | 沿用 psyScale 治愈粉基调的响应式样式 |
| `data/scales/<id>/` | schema v2 量表声明 + 简繁两份题目原文 |
| `locales/ui.json` | 简繁共用的一份文案表（键必须齐平，构造期校验） |
| `tests/` | 引擎测试、壳层端到端、边界基准 |
| `tools/` | 迁移工具、两项 WASM 可行性验证脚本 |
| `vendor/psyscale-ref/` | psyScale 参照副本（只读输入） |
| `docs/` | 设计依据、任务拆解、真浏览器验证清单 |

引擎模块清单：`schema`（声明校验与区间命中）、`item_parser`（CSV→题目）、`scoring`（计分）、
`charts`（Plotly figure）、`report`（JSON/CSV 生成）、`i18n`（文案）、`resources`（取资源）、
`dom`（DOM 与监听器生命周期）、`draft_store`（草稿/结果存取）、`shell`（三视图状态机）、`main`（入口）。

## 已验证（实测，非推断）

| 结论 | 依据 |
|---|---|
| 引擎在本地 CPython 与 Pyodide WASM 内结论完全一致 | PHQ-9 全值域 0–27 档位命中序列逐位相同（Pyodide 314.0.7 / CPython 3.14.2） |
| 三视图状态机可用 | 假 DOM + 真 Pyodide 端到端 38 项全绿：开始 → 9 题逐题作答（每题选择后"下一题"解禁）→ 提交 → 结果落库 → 草稿清理 → 刷新重建 → 三个导出 |
| 解读档位口径修正生效 | 闭区间 + 无缝/覆盖校验；对照实验复现了旧写法把 4/9/14/19 分判成"重度抑郁"的错位 |
| `currentIndex` 写回草稿 | psyScale 从未写回，恢复时永远回到第 1 题；实验版已修 |
| **Plotly 能在 WASM 里出图** | plotly 7.1.0 在 WASM CPython 内 import 255 ms、构造三图 737 ms、序列化 13 ms；雷达图 `scatterpolar` 11 点闭合、`fill=toself`、径向 range [1,5]、中文 hover 正常 |
| 图表降级不白屏 | plotly 不可用时结果页自动出 9 条简化条形并显式标注 |
| 繁简文案一致 | 语言表键齐平校验；导出表头随语言变化 |

## 还没验证（必须真浏览器）

见 `docs/plans/2026-10-31-browser-verification-checklist.md`。核心是四件：
PyScript 标签能否按异步方式执行入口（`py/main.py` 用了顶层 await）、浏览器里 `micropip install plotly`
能否取到包（本沙箱 Node 出站 HTTP 被重置，只能用本地 wheel 证明 plotly 本体可行）、
plotly.js 真实渲染与 Python 侧版本配对、首屏体积与逐题切换延迟。

## 许可待定

`vendor/psyscale-ref/` 的题目与解读文案来自 psyScale（AGPL-3.0）。新项目许可、
以及各量表原始版权（尤其 SCL-90 类可能有商业授权要求）需在扩量前定下来。

设计依据见 `docs/design/`，任务与验证清单见 `docs/plans/`。
