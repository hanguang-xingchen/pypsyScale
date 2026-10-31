# 真浏览器验证清单（M1 收尾）

沙箱里能证的都证了，剩下三件事必须在真浏览器做。下面每条都给了具体动作和判定标准。

## 准备

```bash
npm install
python3 -m http.server 8080          # 或 npm run serve
# 打开 http://localhost:8080/index.html  →  点"开始答题"
```

IndexedDB 与相对路径 fetch 都要求 http(s) 源，直接双击打开 file:// 会失败。

## 门 1：PyScript 能否启动壳

打开 `app.html`，观察 `#engine-badge`。

- 通过：状态变成"引擎已就绪"，须知页出现量表标题与"开始答题"按钮
- 失败要点：控制台里若是 404，说明 `py/*.py` 未被服务；若是 `await outside syntax`，
  说明该版本的 PyScript 未按异步方式执行入口脚本（本仓库 `py/main.py` 用了顶层 await）
- 顺带记录：首次进入的下载量（DevTools → Network，看 wasm + plotly 实际字节）与就绪耗时

## 门 2：答题中途刷新可恢复

答到第 5 题按 F5。

- 通过：回到第 5 题、已选答案仍在（`currentIndex` 每步都写回草稿，这是 psyScale 缺的一步）
- 相关实现：`py/shell.py` 的 `jump()` 写回 `currentIndex`；`view_scale()` 从 store 重建

## 门 3：结果页刷新与图表

提交后看结果页，再按一次 F5。

- 通过：总分、等级、建议、逐题图仍在；分数与刷新前一致
- **Plotly 是否真渲染**：结果页应出现两张图（逐题得分柱状 + 档位条）。
  若看到"图表引擎未就绪，已用简化条形呈现"，说明 `micropip.install('plotly')` 或
  plotly.js 加载失败——把控制台报错原文记下来。WASM 侧的 figure 构造已在
  `tools/verify_plotly_wasm.mjs` 里证过，这里只可能卡在"浏览器取包"与"plotly.js 渲染"
- 版本配对提醒：`js/shim.js` 里锁的是 plotly.js-dist-min **3.0.1**，Python 侧装的是 plotly **7.1.0**。
  两者是否严格配对需在浏览器确认：如果图表能出但 hover/属性异常，优先怀疑这里

## 门 4：前进后退

结果页 → 浏览器返回 → 再前进。

- 通过：不出现空视图、不出现两张重叠的图（`_unmount()` 会 purge 图表并解绑监听）
- 若出现重复图表：说明 Plotly 容器被 Python 重建而 shim 未 purge，检查 `chart_nodes` 回收

## 门 5：对话框与 Esc

在答题未做完时点"提交"，弹层出现后按 Esc。

- 通过：流程不卡死，回到未答题（`js/shim.js` 的 `askConfirm` 把 resolve 挂在 `close` 事件上）
- 这是 psyScale 现行实现的真实缺陷，实验版必须在设计上先堵住

## 门 6：移动端与体积

手机（或 DevTools 设备模拟）走一遍 9 题。

- 关注：逐题切换是否有可感延迟（Pyodide 单线程 + 无跨源隔离，主线程阻塞是本路线最大风险）
- 记录首屏字节数与可交互时间，用来决定"实验版是否只对桌面开放"

## 需要回填的结论

| 项 | 实测值 | 结论 |
|---|---|---|
| 首次加载字节 |  |  |
| 引擎就绪耗时 |  |  |
| 逐题切换延迟 |  |  |
| Plotly 渲染成功 |  |  |
| 三张门 1-5 |  |  |

填完这张表，M1 就可以判"可行/退回多页/放弃全量替换"。

---

内容由 AI 生成
