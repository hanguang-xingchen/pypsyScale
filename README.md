# pypsyScale

一个基于 PyScript 的心理学量表评估工具，在浏览器内使用 Python（Pyodide / CPython 3.14 WASM）完成计分与解读。

## 这是什么

pypsyScale 是 [psyScale](https://github.com/hanguang-xingchen/psyScale) 的实验性重构版本，探索将量表评估逻辑从 JavaScript 迁移到浏览器内 Python 运行时的可行性。

所有作答与结果只保存在你的设备本地（IndexedDB），不会上传到任何服务器。

## 支持哪些量表

- **PHQ-9**：抑郁症筛查（9 题）
- **GAD-7**：广泛性焦虑筛查（7 题）
- **CES-D**：流调中心抑郁量表（20 题）
- **WHO-5**：幸福感指数（5 题）
- **K10**：心理困扰筛查（10 题）
- **PSS-10**：感知压力量表（10 题）
- **SES**：Rosenberg 自尊量表（10 题）
- **SAS**：焦虑自评量表（20 题，标准分 = 粗分 × 1.25）
- **SDS**：抑郁自评量表（20 题，标准分 = 粗分 × 1.25）

## 如何使用

1. 打开 [在线演示](https://hanguang-xingchen.github.io/pypsyScale/)
2. 选择一个量表，点击"开始答题"
3. 首次加载需要下载运行时（约 10 MB），请耐心等待
4. 完成答题后查看结果，可下载 JSON 或 CSV 报告

## 命令行版本（TUI）

不需要安装任何东西，一条命令即可在终端里启动量表答题（Linux / macOS，需系统自带 Python 3）：

```bash
python3 -c "$(curl -fsSL https://hanguangxingchen.top/pypsyScale/tui/bootstrap.py)"
```

原理：上面的命令只拉一个引导脚本，由它把所需的标准库模块下载到临时目录后启动 TUI；量表定义与题目按需从 `https://hanguangxingchen.top/pypsyScale` 现场请求。作答只保存在当前进程内存里，退出即清，不落盘、不装包。

### 操作

- `↑`/`↓` 或 `j`/`k` 选择量表，`回车` 进入；
- 数字键 `1-9` 选择选项（选完自动进入下一题）；
- `←`/`→` 或 `P`/`N` 切换题目，末题按 `回车` 提交出结果；
- `b` 返回列表，`q` 随时退出。

### 界面示意

```text
pypsyScale 量表（终端版）

   1. PHQ-9 抑郁症筛查量表
 ► 2. GAD-7 广泛性焦虑筛查
   3. CES-D 流调中心抑郁量表
        ...

↑/↓ 或 j/k 选择   回车 进入   q 退出
```

> **换源 / 本地运行**：设置环境变量 `PYSYSCALE_BASE` 指向另一个静态根（镜像）即可。

## 隐私说明

- 所有数据仅保存在你的浏览器本地（IndexedDB）
- 不会上传到任何服务器
- 清除浏览器数据会删除所有作答记录

## 免责声明

本工具仅供参考，不构成医学诊断。如有疑虑请咨询专业人士。

## 许可证

本项目采用 GNU AGPL-3.0 许可证开源。

量表题目与解读文案来源于 [psyScale](https://github.com/hanguang-xingchen/psyScale)（同样采用 AGPL-3.0）。

---

**技术细节**：开发文档、验证清单、架构设计等见 [docs/](docs/) 目录。
