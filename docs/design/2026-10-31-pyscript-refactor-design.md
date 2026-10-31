# pypsyScale 重构设计（PyScript + Plotly）

日期：2026-10-31　状态：已确认，进入实施
来源：与 psyScale 作者（Hanguang）的设计讨论，非代码逆向结论。

## 1. 目标与非目标

目标：把「配置解析 → 计分 → 等级解读 → 报告/图表数据生成」下沉到浏览器内 Python（Pyodide/WASM），
让判定逻辑有单一事实源，并顺带走通 psyScale 设计文档里"为后端校验预留接口"那条路。

非目标：不引入自建后端、不做账号体系、不改答题交互形态。

四条底线：① 仍可纯静态托管；② 答卷数据不出本机；③ 配置驱动（新增量表 = 加目录 + 加配置）；
④ 移动端可用，不能因体积把首屏拖死。

## 2. 已确认的四个决策

| 议题 | 决策 |
|---|---|
| 重构路线 | 全量替换：所有页面由 PyScript 驱动，答题引擎也用 Python |
| 图表栈 | Plotly 全套（Python 侧正式 `import plotly` 构造 figure） |
| 部署 | 沿用 GitHub Pages（拿不到自定义响应头，多线程/Worker 路线关闭） |
| 项目形态 | 新建独立仓库 pypsyScale，从 psyScale 取可用部分，不在原仓库内改动 |

范围收敛：**先只做 PHQ-9 一个静态简单量表，确认可行再扩量。**

## 3. 架构形态：静态首页 + 单页壳两段式

- `index.html`：纯静态量表列表，秒开，不加载运行时。
- `app.html`：一个 PyScript 壳，内部 hash 路由承载 **须知 / 答题 / 结果** 三个视图。

为什么这三个视图适合同壳：答案草稿、计分结果、已安装的 plotly 都活在同一次解释器生命周期里；
三者是线性流程而非并列导航（3 节点状态机）；数据源本就是 IndexedDB 而不是 URL。

四条必须遵守的约束（否则单页壳会以别的名义翻车）：

1. **DOM 所有权**：每个视图唯一 root 归 Python；Plotly 容器与 dialog 是 shim.js 私有节点，
   Python 只发命令（渲染图表 / 弹框），不伸手进内部。
2. **视图卸载**：切走必须 purge 图表并解绑监听；监听一律事件委托挂在壳根。
3. **刷新与前进后退**：hash 写全 `#view/scaleId`，`hashchange` 时从 IndexedDB 重建状态，不信内存快照。
4. **异步对话框收口**：等待用户决策的 Promise 必须监听 `close` 并按 `returnValue` 收口，
   否则用户按 Esc 会让流程永久挂起（psyScale 现行实现就是这个形状）。

M1 三道实测门，过不了就退回「多页 + Service Worker 缓存」（代价是每次导航一次解释器冷启动，
不是资产重传）：答题中途刷新可恢复；结果页刷新后图表与下载仍在；返回再前进不出现空视图或双份图。

## 4. 技术栈锁定与实测数据

| 项 | 值 | 来源 |
|---|---|---|
| PyScript | 2026.7.3（内含 Pyodide 314.0.3） | release 页实测 |
| Pyodide | 314.0.7 = CPython 3.14.2，abi `2026_0`，platform `emscripten_5_0_3` | `pyodide-lock.json` |
| wheel 标签 | `pyemscripten_2026_0_wasm32`（PEP 783 PyEmscripten） | 同上 |
| 内置包 | matplotlib 3.10.8 / numpy 2.4.6 / pandas 3.0.2 / altair 6.0.0 / bokeh 3.9.0，共 357 包 | 同上 |
| plotly | **未内置**，`micropip` 取 PyPI 纯 Python wheel 9.69 MB；运行依赖 narwhals + packaging 均已在内置包中 | PyPI 元数据 + lock 包表 |
| plotly.js | dist-min 3.0.1 实测 4.65 MB | CDN 实测 |
| 运行时 | pyodide.asm.wasm 实测 9.60 MB；stdlib 体积本回合未取到（记为缺口） | CDN 实测 |
| matplotlib 现状 | `matplotlib-pyodide` 已归档，默认后端 webagg 出静态图，无原生 hover | 该仓库 README |

体积下界 ≈ 24 MB（不含 stdlib），对照 psyScale 全站排除 `.git` 后 464 KB。
缓解：分层加载（plotly 只在结果视图装）、单页常驻解释器、Service Worker 缓存、页面明示适用环境。

不引入 matplotlib / seaborn / bokeh / ipywidgets：Pyodide 314 无 ipywidgets 与 anywidget，
plotly 的 notebook 渲染路径在浏览器不可用；kaleido 是 dev extra，浏览器内不可用，故**不做 PNG/PDF 导出**。

## 5. schema v2 的两处口径修正

1. **命中语义显式化**：`scoring.interval` 必填（`closed` / `half_open`）。psyScale 用 `score < max` 命中，
   却把档位写成连续整数闭区间，于是每个档位上界的分数全部穿透到"返回最后一档"的兜底分支。
   实测对照：PHQ-9 的 4 / 9 / 14 / 19 分在旧写法下都被判成"重度抑郁"。
   新实现：导入期强制无缝 + 无重叠 + 值域全覆盖校验，运行期命中不到直接抛错，绝不静默兜底。
2. **粗分换算显式化**：`scoring.transform.raw_factor`。SAS / SDS 这类"粗分 ×1.25 得标准分"的量表，
   换算系数写进配置而不是藏在代码里；报告同时给出粗分与报告分。已用合成量表验证换算路径生效。

附带修正：分值改浮点解析（整数解析会截断小数分值）、CSV 改用标准库解析（支持题面里的逗号与引号）、
解读档位与文案按 `{zh-CN, zh-TW}` 合入同一份 `scale.json`（取消 psyScale 的整目录双语复制），
导出表头与提示文案全部走语言表（繁体用户不再拿到简体表头）。

## 6. 从 psyScale 取什么、不取什么

取：量表数据集（10 量表 × 简繁，题目/选项/反向题分值已人工校对）、SCL-90 维度与阳性项目语义、
三种导出的字段语义、繁中用语清单、`css/style.css` 的视觉基线。

不取：双 `zh-TW/` 目录复制、靠 URL 路径嗅探语言、JS 的 scorer/report/CSV 实现、
整数解析分值、边界兜底、声明未实现的 `missingValuePolicy`。

迁移必须是**可重复、可验证的动作**：`tools/import_psyscale.py` 只读项目内 `vendor/psyscale-ref/`，
跨语言结构不一致就停机，并顺带产出边界基准用例。psyScale 作为外部对照，不作护栏。

## 7. 风险登记

| 风险 | 处置 |
|---|---|
| 主线程阻塞（无跨源隔离 → 无线程化包） | SCL-90 逐题切换延迟列为 M1 否决性指标 |
| 24 MB 首屏 | 分层加载 + SW 缓存 + 页面明示 |
| plotly Python 与 plotly.js 版本配对 | 待实测核对（本回合取到的是 plotly.js 3.0.1） |
| PyScript 日历版本演进快（含包缓存策略变更） | 锁定 release 版本 |
| 浏览器兼容（外部报告称 Edge 增强安全模式会让 Pyodide 崩溃） | 特性检测失败即引导回轻量版 |
| 隐私口径变化 | 数据仍不出本机，但运行时从 CDN 拉，页面说明需同步 |
| 许可 | 新仓库许可待定；量表原始版权（尤其 SCL-90 类）需核实；上游许可证与 AGPL 的兼容需逐项核对 |

## 8. 里程碑

M0 口径与基准定义 → **已完成**（schema v2、导入工具、14 条自动边界基准、17 项引擎测试全绿）。
M1 单页壳 + PHQ-9 全流程 + 硬指标实测（首屏/逐题延迟/内存）+ plotly 链路打通 → **进行中**，
纯引擎部分已在 WASM 内跑通，plotly 拉包受沙箱网络限制未完。
M2 SCL-90 + Plotly 雷达（阈值环、hover、繁中标签）。
M3 十量表 + 简繁全量 + 与 psyScale 线上版逐分对照出差异清单。
M4 结论：是否值得作为主线，以及升线的前置条件。

---

内容由 AI 生成
