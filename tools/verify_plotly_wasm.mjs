// 在 WASM 里真跑 Plotly：验证"浏览器内 Python 出图"这条核心假设。
//
// 用法：node tools/verify_plotly_wasm.mjs        （需 cache/wheels/*.whl）
// 说明：本沙箱 Node 的出站 HTTP 被重置，无法走 micropip → PyPI。
//       这里把 wheel 直接解压进虚拟 FS 再 import，验证的是 plotly 本体在
//       WASM CPython 3.14 里能否构造 figure 并序列化；
//       浏览器里那层 micropip 安装仍需在正常网络下补验一次。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from 'pyodide';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WHEEL_DIR = path.join(ROOT, 'cache', 'wheels');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const wheels = fs.existsSync(WHEEL_DIR) ? fs.readdirSync(WHEEL_DIR).filter((f) => f.endsWith('.whl')) : [];
if (!wheels.length) {
  console.error('cache/wheels 下没有 wheel，先按 README 取 plotly/narwhals/packaging');
  process.exit(1);
}

const PY = `
import json, os, platform, sys, time

os.makedirs('/site', exist_ok=True)
t0 = time.perf_counter()
import zipfile
for name in os.listdir('/wheels'):
    if name.endswith('.whl'):
        zipfile.ZipFile('/wheels/' + name).extractall('/site')
unzip_ms = int((time.perf_counter() - t0) * 1000)
sys.path.insert(0, '/site')
sys.path.insert(0, '/psy')

t1 = time.perf_counter()
import plotly
import plotly.graph_objects as go
plotly_ms = int((time.perf_counter() - t1) * 1000)

from i18n import Catalog
from item_parser import parse_items
from resources import fetch_json
from scoring import score_scale
from schema import validate
from resources import fetch_text
from item_parser import score_range
import charts

scale = await fetch_json('data/scales/phq-9/scale.json')
items = parse_items(await fetch_text('data/scales/phq-9/items.zh-CN.csv'))
ui = Catalog.from_json_map(await fetch_json('locales/ui.json'))
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


result = score_scale(scale, items, build(15), language='zh-CN')

t2 = time.perf_counter()
fig_bar = charts.item_bar_figure(result, items, t=ui.t, lang_labels={'answered': ui.t('chart_item_answered', lang='zh-CN')})
fig_band = charts.band_position_figure(result, scale, t=ui.t)
build_ms = int((time.perf_counter() - t2) * 1000)

# 合成十维数据：结构与 SCL-90 一致（因子均分 1-5、阈值 2），数值为构造样本
dims = ['躯体化', '强迫症状', '人际关系敏感', '抑郁', '焦虑', '敌对', '恐怖', '精神病性', '偏执', '其他']
vals = [1.42, 2.80, 1.78, 2.15, 2.60, 1.33, 1.10, 1.90, 2.45, 1.65]
lvls = ['正常' if v < 2 else '轻度' if v < 3 else '中度' for v in vals]
t3 = time.perf_counter()
fig_radar = charts.radar_figure(labels=dims, values=vals, levels=lvls, threshold=2.0,
                                title='症状总览', hover_suffix='（因子均分）')
radar_ms = int((time.perf_counter() - t3) * 1000)

t4 = time.perf_counter()
payloads = {k: charts.figure_to_json(f) for k, f in
            (('bar', fig_bar), ('band', fig_band), ('radar', fig_radar))}
serialize_ms = int((time.perf_counter() - t4) * 1000)

parsed = {k: json.loads(v) for k, v in payloads.items()}
radar = parsed['radar']

json.dumps({
    'python': platform.python_version(),
    'wheels': sorted(os.listdir('/wheels')),
    'unzip_ms': unzip_ms,
    'plotly_version': plotly.__version__,
    'plotly_import_ms': plotly_ms,
    'figure_build_ms': build_ms,
    'radar_build_ms': radar_ms,
    'serialize_ms': serialize_ms,
    'json_bytes': {k: len(v.encode()) for k, v in payloads.items()},
    'trace_types': {k: [d.get('type') for d in v.get('data', [])] for k, v in parsed.items()},
    'radar_points': len(radar['data'][0]['theta']),
    'radar_fill': radar['data'][0].get('fill'),
    'radar_theta_head': radar['data'][0]['theta'][:3],
    'radar_r_head': radar['data'][0]['r'][:3],
    'radar_hover_head': radar['data'][0]['hovertext'][0],
    'radar_range': radar['layout']['polar']['radialaxis']['range'],
    'band_hover_sample': parsed['band']['data'][0]['hovertext'][0],
    'bar_hover_sample': parsed['bar']['data'][0]['hovertext'][0],
    'result': {'total': result.raw_total, 'level': result.level},
})
`;

async function main() {
  const pyodide = await loadPyodide();
  const ensureDir = (dir) => {
    const parts = dir.split('/').filter(Boolean);
    let cur = '';
    for (const part of parts) {
      cur += '/' + part;
      if (!pyodide.FS.analyzePath(cur).exists) pyodide.FS.mkdir(cur);
    }
  };
  ensureDir('/wheels'); ensureDir('/site'); ensureDir('/psy');
  ensureDir('/app/data/scales/phq-9'); ensureDir('/app/locales');
  for (const w of wheels) pyodide.FS.writeFile('/wheels/' + w, fs.readFileSync(path.join(WHEEL_DIR, w)));
  for (const m of ['schema', 'item_parser', 'scoring', 'i18n', 'charts', 'report', 'resources']) {
    pyodide.FS.writeFile('/psy/' + m + '.py', read('py/' + m + '.py'));
  }
  pyodide.FS.writeFile('/app/data/scales/phq-9/scale.json', read('data/scales/phq-9/scale.json'));
  pyodide.FS.writeFile('/app/data/scales/phq-9/items.zh-CN.csv', read('data/scales/phq-9/items.zh-CN.csv'));
  pyodide.FS.writeFile('/app/locales/ui.json', read('locales/ui.json'));

  try {
    const out = await pyodide.runPythonAsync(PY);
    console.log(JSON.stringify(JSON.parse(out), null, 2));
  } catch (err) {
    console.error('WASM 内 Plotly 验证失败：\n' + (err.message || err));
    process.exit(1);
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
