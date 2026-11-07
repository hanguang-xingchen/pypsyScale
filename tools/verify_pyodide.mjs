// 把同一份纯引擎放进 Pyodide(WASM) 里跑一遍：可行性验证的硬证据。
//
// 用法：node tools/verify_pyodide.mjs
// 验证内容：
// 1. 引擎模块能否在 WASM 版 CPython 里原样 import（不含任何 js / pyscript 依赖）
// 2. 导入生成的边界基准在 WASM 里是否与本地 CPython 结论一致
// 3. 0..27 全值域命中结果与简繁双语言标签
// 4. plotly 能否 micropip 装上、构造 figure 并序列化成页面可消费的 JSON
// 5. 各环节耗时实测
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from 'pyodide';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

const ENGINE = ['schema.py', 'item_parser.py', 'scoring.py', 'i18n.py', 'charts.py', 'report.py'];
const DATA = ['data/scales/phq-9/scale.json', 'data/scales/phq-9/items.zh-CN.csv',
              'data/scales/phq-9/items.zh-TW.csv', 'tests/golden/phq-9.json', 'locales/ui.json'];

const PY = `
import json, platform, sys, time

sys.path.insert(0, "/psy")
from i18n import Catalog
from item_parser import parse_items, score_range
from report import detail_csv, report_json
from schema import validate
from scoring import score_scale

t0 = time.perf_counter()

scale = json.loads(open("/data/scales/phq-9/scale.json", encoding="utf-8").read())
items = parse_items(open("/data/scales/phq-9/items.zh-CN.csv", encoding="utf-8").read())
items_tw = parse_items(open("/data/scales/phq-9/items.zh-TW.csv", encoding="utf-8").read())
ui = Catalog.from_json_map(json.loads(open("/locales/ui.json", encoding="utf-8").read()))
lo, hi, step = score_range(items)
validate(scale, score_min=lo, score_max=hi, step=step)


def build(total):
    values = [min(o.value for o in it.options) for it in items]
    caps = [max(o.value for o in it.options) for it in items]
    remaining = total - sum(values)
    for i, cap in enumerate(caps):
        if remaining <= 0:
            break
        add = min(int(cap - values[i]), int(remaining))
        values[i] += add
        remaining -= add
    return {it.q_id: values[i] for i, it in enumerate(items)}


golden = json.loads(open("/tests/golden/phq-9.json", encoding="utf-8").read())
golden_pass, golden_fail = 0, []
for c in golden["cases"]:
    got = score_scale(scale, items, c["answers"], language="zh-CN").band_index
    if got == c["expect_band"]:
        golden_pass += 1
    else:
        golden_fail.append({"name": c["name"], "expect": c["expect_band"], "got": got})

band_seq = []
level_cn, level_tw = {}, {}
for total in range(int(lo), int(hi) + 1):
    res = score_scale(scale, items, build(total), language="zh-CN")
    band_seq.append(res.band_index)
    if total in (0, 4, 5, 9, 14, 15, 19, 20, 27):
        level_cn[total] = res.level
        level_tw[total] = score_scale(scale, items_tw, build(total), language="zh-TW").level

engine_ms = int((time.perf_counter() - t0) * 1000)

# plotly 未内置在 Pyodide，需 micropip 从 PyPI 取纯 Python wheel
import micropip
t1 = time.perf_counter()
await micropip.install("plotly")
install_ms = int((time.perf_counter() - t1) * 1000)

import charts
import plotly
t2 = time.perf_counter()
res15 = score_scale(scale, items, build(15), language="zh-CN")
fig_items = charts.item_bar_figure(res15, items, t=ui.t,
                                   lang_labels={"answered": ui.t("chart_item_answered", lang="zh-CN")})
fig_band = charts.band_position_figure(res15, scale, t=ui.t)
build_ms = int((time.perf_counter() - t2) * 1000)

t3 = time.perf_counter()
json_items = charts.figure_to_json(fig_items)
json_band = charts.figure_to_json(fig_band)
serialize_ms = int((time.perf_counter() - t3) * 1000)

parsed = json.loads(json_items)
render_payload = {
    "data_is_list": isinstance(parsed.get("data"), list) and len(parsed["data"]) == 1,
    "layout_is_dict": isinstance(parsed.get("layout"), dict),
    "trace_type": parsed["data"][0].get("type") if parsed.get("data") else None,
    "x_labels": parsed["data"][0].get("x") if parsed.get("data") else None,
    "hover_sample": (parsed["data"][0].get("hovertext") or [None])[0] if parsed.get("data") else None,
    "band_json_bytes": len(json_band.encode("utf-8")),
    "items_json_bytes": len(json_items.encode("utf-8")),
}

t4 = time.perf_counter()
std_report = json.loads(report_json(res15, generated="2026-10-31"))
detail_report = json.loads(report_json(res15, with_answers=True, generated="2026-10-31"))
csv_text = detail_csv(score_scale(scale, items_tw, build(15), language="zh-TW"), items_tw,
                      headers=ui.t("csv_headers", lang="zh-TW").split(","), generated="2026-10-31")
report_ms = int((time.perf_counter() - t4) * 1000)

json.dumps({
    "python": platform.python_version(),
    "engine_ms": engine_ms,
    "plotly_version": plotly.__version__,
    "plotly_install_ms": install_ms,
    "figure_build_ms": build_ms,
    "serialize_ms": serialize_ms,
    "report_ms": report_ms,
    "golden_pass": golden_pass,
    "golden_total": len(golden["cases"]),
    "golden_fail": golden_fail,
    "band_seq": band_seq,
    "level_cn": level_cn,
    "level_tw": level_tw,
    "render_payload": render_payload,
    "report_summary": std_report["summary"],
    "detail_answers_len": len(detail_report["answers"]),
    "csv_head": csv_text.splitlines()[:2],
})
`;

async function main() {
  const bootStart = Date.now();
  const pyodide = await loadPyodide();
  const bootMs = Date.now() - bootStart;

  const ensureDir = (dir) => {
    const parts = dir.split('/').filter(Boolean);
    let cur = '';
    for (const part of parts) {
      cur += '/' + part;
      try {
        pyodide.FS.mkdir(cur);
      } catch (err) {
        if (err && err.code !== 'EEXIST') throw err;
      }
    }
  };
  for (const dir of ['/psy', '/data/scales/phq-9', '/locales', '/tests/golden']) ensureDir(dir);
  for (const f of ENGINE) pyodide.FS.writeFile('/psy/' + path.basename(f), read('py/' + f));
  for (const f of DATA) pyodide.FS.writeFile('/' + f, read(f));

  const runStart = Date.now();
  await pyodide.loadPackage(['micropip']);
  let stdout = '';
  pyodide.setStdout({ batched: (s) => { stdout += s + '\n'; } });
  let raw;
  try {
    raw = await pyodide.runPythonAsync(PY);
  } catch (err) {
    console.error('WASM 内执行失败：\n' + (err.message || err));
    if (stdout) console.error('已输出：\n' + stdout);
    process.exit(1);
  }
  const runMs = Date.now() - runStart;

  console.log(JSON.stringify({
    host: `node ${process.version}`,
    pyodide_boot_ms: bootMs,
    total_run_ms: runMs,
    wasm: JSON.parse(raw),
  }, null, 2));
}

main().catch((err) => { console.error(err); process.exit(1); });
