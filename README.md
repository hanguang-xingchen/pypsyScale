# pypsyScale（psyScale 的 PyScript 重构实验）

把 psyScale 的「配置 → 计分 → 解读 → 图表」链路重做成浏览器内 Python（Pyodide/WASM）运行的实验项目。
首版只切一个最简量表（PHQ-9）验证可行性，可行再扩量。

## 现在能跑什么

```bash
python3 tests/run_tests.py          # 引擎测试，17 项，纯本地 CPython，不需要浏览器
node tools/verify_pyodide.mjs       # 把同一份引擎放进 WASM 里跑，并实测 plotly 出图链路
python3 tools/import_psyscale.py --scale <id> --source-commit <sha>   # 从 vendor/psyscale-ref 迁移量表
```

## 目录

| 路径 | 作用 |
|---|---|
| `py/` | 纯 Python 引擎，不含任何 js / pyscript 调用，本地、WASM、未来后端共用同一份 |
| `data/scales/<id>/` | schema v2 量表声明 + 简繁两份题目原文 |
| `locales/ui.json` | 简繁共用的一份文案表（键必须齐平，构造期校验） |
| `tests/golden/` | 由解读表自动生成的边界基准用例 |
| `tools/` | 迁移工具、WASM 可行性验证脚本 |
| `vendor/psyscale-ref/` | psyScale 参照副本（只读输入，迁移的源头） |

## 已验证

- 引擎在本地 CPython 与 Pyodide WASM 内**结论完全一致**（PHQ-9 全值域 0–27 命中同一档位序列）。
- 解读表改为显式闭区间 + 导入期无缝/覆盖校验，修掉了 psyScale 里「每档上界分数穿透到兜底末档」这类判定错位。
- 简繁题目结构（题序、选项数、分值序列、档位 min/max/color）跨语言一致性校验生效；分值改浮点解析，不再截断小数。
- 文案、导出表头跟随语言，不再是固定简体。

## 还没验证 / 还没做

- WASM 内的 plotly 安装与出图：沙箱内 Node 直连 CDN 被重置（`fetch failed / ECONNRESET`），本回合卡在拉包这一步，待在网络放行环境里补完。
- 单页壳（须知 / 答题 / 结果 三视图）、Pyodide 侧 IndexedDB 草稿存取、首屏体积与逐题延迟实测、SCL-90 雷达图（M2）。

## 许可待定

`vendor/psyscale-ref/` 里的题目与解读文案来自 psyScale（AGPL-3.0）。新项目是否沿用 AGPL、
以及各量表原始版权（尤其 SCL-90 类有商业授权要求的量表）如何处理，需在扩量前定下来。

设计依据与任务拆解见 `docs/design/`、`docs/plans/`。
