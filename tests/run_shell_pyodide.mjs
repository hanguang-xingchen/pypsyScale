// 无浏览器的壳层端到端冒烟测试：假 DOM + 真 IndexedDB 语义（fake-indexeddb）+ 真 Pyodide。
//
// 能证明：main.py 装载 → 三视图状态机 → 答题写草稿 → 提交计分 → 结果落库 →
//         刷新后从存储重建 → 导出与图表降级路径，全部在同一条真实代码上跑通。
// 不能证明：PyScript 标签装载、plotly.js 真实渲染、首屏耗时——那三件必须真浏览器。
//
// 用法：node tests/run_shell_pyodide.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import 'fake-indexeddb/auto';
import { loadPyodide } from 'pyodide';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const FAILS = [];
const ok = (cond, name, detail) => {
  console.log(`  ${cond ? '✓' : '✗'} ${name}${cond ? '' : '  ← ' + detail}`);
  if (!cond) FAILS.push(name);
};

// ---------------------------------------------------------------- 假 DOM
let idIndex = new Map();

class FakeEl {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.parentNode = null;
    this._class = '';
    this._text = '';
    this.attrs = {};
    this.style = {};
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.listeners = new Map();
    this.id = '';
  }
  get className() { return this._class; }
  set className(v) { this._class = String(v); }
  get textContent() {
    if (this.children.length === 0) return this._text;
    return this.children.map((c) => c.textContent).join('');
  }
  set textContent(v) { this.children = []; this._text = String(v); }
  get firstChild() { return this.children[0] || null; }
  get classList() {
    return {
      contains: (c) => this._class.split(/\s+/).includes(c),
    };
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === 'id') this._register(v);
  }
  _register(v) { this.id = String(v); idIndex.set(this.id, this); }
  appendChild(node) {
    node.parentNode = this;
    this.children.push(node);
    if (node.id) idIndex.set(node.id, node);
    walk(node, (el) => el.id && idIndex.set(el.id, el));
    return node;
  }
  removeChild(node) {
    const i = this.children.indexOf(node);
    if (i >= 0) this.children.splice(i, 1);
    node.parentNode = null;
    return node;
  }
  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }
  removeEventListener(type, fn) {
    const arr = this.listeners.get(type) || [];
    const i = arr.indexOf(fn);
    if (i >= 0) arr.splice(i, 1);
  }
  fire(type, event = {}) {
    const arr = [...(this.listeners.get(type) || [])];
    arr.forEach((fn) => fn({ type, target: this, preventDefault() {}, ...event }));
    return arr.length;
  }
  find(pred, acc = []) {
    if (pred(this)) acc.push(this);
    this.children.forEach((c) => c.find(pred, acc));
    return acc;
  }
  allText() { return this.textContent; }
}

const mkDoc = () => {
  const root = new FakeEl('html');
  const body = new FakeEl('body');
  const head = new FakeEl('head');
  root.appendChild(body);
  root.appendChild(head);
  const byIdNodes = new Map();
  for (const id of ['engine-badge', 'home-link', 'boot', 'boot-text', 'view', 'dialog',
                    'dialog-text', 'dialog-yes', 'dialog-no', 'footer-note', 'py-error']) {
    const el = new FakeEl(id === 'dialog' ? 'dialog' : 'div');
    el._register(id);
    body.appendChild(el);
    byIdNodes.set(id, el);
  }
  const dialog = byIdNodes.get('dialog');
  dialog.returnValue = '';
  dialog.showModal = () => { dialog.open = true; };
  dialog.close = () => { dialog.open = false; dialog.fire('close'); };
  byIdNodes.get('dialog-yes').addEventListener('click', () => { dialog.returnValue = 'yes'; dialog.close(); });
  byIdNodes.get('dialog-no').addEventListener('click', () => { dialog.returnValue = 'no'; dialog.close(); });

  return {
    documentElement: root,
    body,
    head,
    createElement: (tag) => new FakeEl(tag),
    getElementById: (id) => byIdNodes.get(id) || idIndex.get(id) || null,
  };
};

function walk(node, fn) {
  fn(node);
  node.children.forEach((c) => walk(c, fn));
}

const fakeDoc = mkDoc();
const hashListeners = [];
const location = { _hash: '', pathname: '/pypsyScale/app.html', href: 'http://localhost/pypsyScale/app.html' };
Object.defineProperty(location, 'hash', {
  get() { return this._hash; },
  set(v) {
    const next = v.startsWith('#') ? v : '#' + v;
    if (next === this._hash) return;          // 浏览器同样不会因相同 hash 赋值而触发事件
    this._hash = next;
    [...hashListeners].forEach((fn) => fn({ type: 'hashchange' }));
  },
});
const dispatchHashchange = () => [...hashListeners].forEach((fn) => fn({ type: 'hashchange' }));
const fakeWindow = {
  document: fakeDoc,
  location,
  addEventListener: (type, fn) => { if (type === 'hashchange') hashListeners.push(fn); },
  removeEventListener: (type, fn) => {
    const i = hashListeners.indexOf(fn);
    if (i >= 0) hashListeners.splice(i, 1);
  },
  confirm: () => true,
  Plotly: undefined,
  URL: globalThis.URL,
  Blob: globalThis.Blob,
  setTimeout: globalThis.setTimeout,
  console,
};
globalThis.window = fakeWindow;
globalThis.document = fakeDoc;

// 用真实 shim.js（浏览器桥）跑在假 DOM + fake-indexeddb 上
const shimSrc = read('js/shim.js');
new Function('window', 'document', 'indexedDB', 'Blob', 'URL', 'console', 'setTimeout', shimSrc)(
  fakeWindow, fakeDoc, globalThis.indexedDB, globalThis.Blob, globalThis.URL, console, setTimeout);
ok(!!fakeWindow.PSY, 'shim.js 暴露 window.PSY 桥', '未定义');

const downloads = [];
fakeWindow.PSY.download = (name, mime, text) => { downloads.push({ name, mime, text }); return true; };

const flush = (ms = 30) => new Promise((r) => setTimeout(r, ms));
async function goto(hash) {
  location.hash = hash;
  [...hashListeners].forEach((fn) => fn({ type: 'hashchange' }));
  await flush(120);
}

// ---------------------------------------------------------------- Pyodide
const pyodide = await loadPyodide();
const MODULES = ['schema', 'item_parser', 'scoring', 'i18n', 'charts', 'report',
                 'resources', 'dom', 'draft_store', 'shell', 'main'];
pyodide.FS.mkdir('/app');
pyodide.FS.mkdir('/app/py');
pyodide.FS.mkdir('/app/data');
pyodide.FS.mkdir('/app/data/scales');
pyodide.FS.mkdir('/app/data/scales/phq-9');
pyodide.FS.mkdir('/app/locales');
for (const m of MODULES) pyodide.FS.writeFile(`/app/py/${m}.py`, read(`py/${m}.py`));
for (const f of ['data/scales/index.json', 'data/scales/phq-9/scale.json',
                 'data/scales/phq-9/items.zh-CN.csv', 'data/scales/phq-9/items.zh-TW.csv',
                 'locales/ui.json']) {
  pyodide.FS.writeFile('/app/' + f, read(f));
}
pyodide.setStderr({ batched: (s) => console.error('    [py]', s) });

const boot = await pyodide.runPythonAsync(read('py/main.py'));
void boot;
await flush(150);

const viewText = () => fakeDoc.getElementById('view').textContent;
const badge = () => fakeDoc.getElementById('engine-badge').textContent;

ok(!/启动中/.test(badge()), '引擎启动后状态标记已更新', badge());
ok(fakeDoc.getElementById('boot').hidden === true, '加载态在首个视图渲染后隐藏',
   `hidden=${JSON.stringify(fakeDoc.getElementById('boot').hidden)}`);

// ---------------------------------------------------------------- 须知 → 答题
await goto('#/notice/phq-9?lang=zh-CN');
ok(/PHQ-9/.test(viewText()), '须知视图渲染出量表标题', viewText().slice(0, 60));
ok(/测评须知|所有作答/.test(viewText()), '须知视图包含须知与隐私说明');

const startBtn = fakeDoc.getElementById('btn-start');
ok(!!startBtn, '须知视图存在开始按钮');
startBtn.fire('click');
await flush(200);
ok(location.hash.includes('#/scale/phq-9'), '点击开始后路由切到答题视图', location.hash);
ok(/第 1 题 \/ 共 9 题/.test(viewText()), '答题视图首题进度正确', viewText().slice(0, 80));

const draft0 = await fakeWindow.PSY.store.get('draft:phq-9');
ok(!!draft0 && Object.keys(draft0.answers || {}).length === 0, '进入答题即建立空草稿', JSON.stringify(draft0));

// 逐题作答：构造总分 15（中重度抑郁档）
const target = [3, 3, 3, 3, 2, 1, 0, 0, 0];
for (let q = 0; q < 9; q++) {
  const options = fakeDoc.getElementById('option-list').children;
  options[target[q]].fire('click');
  await flush(60);
  const nextBtn = fakeDoc.getElementById('btn-next');
  ok(nextBtn && nextBtn.disabled === false, `第 ${q + 1} 题选择后下一题可用`);
  if (q < 8) {
    nextBtn.fire('click');
    await flush(60);
  }
}
ok(/第 9 题 \/ 共 9 题/.test(viewText()), '答到最后一题', viewText().slice(0, 60));
ok(fakeDoc.getElementById('btn-next').textContent === '提交', '末题按钮变为提交', fakeDoc.getElementById('btn-next').textContent);

const draftFull = await fakeWindow.PSY.store.get('draft:phq-9');
ok(Object.keys(draftFull.answers).length === 9, '九题答案全部写入草稿', JSON.stringify(draftFull.answers));
ok(draftFull.currentIndex === 8, 'currentIndex 被写回草稿（psyScale 缺这一步）', String(draftFull.currentIndex));

fakeDoc.getElementById('btn-next').fire('click');   // 提交
await flush(300);
ok(location.hash.includes('#/result/phq-9'), '提交后路由切到结果视图', location.hash);

const stored = await fakeWindow.PSY.store.get('result:phq-9');
ok(!!stored && stored.raw_total === 15 && stored.level === '中重度抑郁', '结果已落库且分级正确', JSON.stringify(stored && { t: stored.raw_total, l: stored.level }));
const gone = await fakeWindow.PSY.store.get('draft:phq-9');
ok(gone === null || gone === undefined, '提交后草稿被清理', String(gone));

ok(/中重度抑郁/.test(viewText()), '结果视图渲染等级', viewText().slice(0, 120));
ok(/存在中重度抑郁症状/.test(viewText()), '结果视图渲染建议文案');
ok(/本结果仅供参考/.test(viewText()), '结果视图带免责声明');

// 图表降级：本环境无网络，plotly 装不上时必须仍能给出可读结果
ok(fakeWindow.Plotly === undefined, '本环境确实没有 plotly.js（降级路径的前提）');
const bars = fakeDoc.getElementById('view').find((el) => el.className === 'bar');
ok(bars.length === 9, 'Plotly 不可用时降级为 9 条简化条形', String(bars.length));
ok(/不可用|降级|Error|error/.test(badge() + viewText()), '降级被显式标注而不是静默');

// ---------------------------------------------------------------- 下载
const buttons = fakeDoc.getElementById('view').find((el) => el.tagName === 'BUTTON' && /下载/.test(el.textContent));
ok(buttons.length === 3, '结果页有 3 个导出按钮', String(buttons.length));
buttons.forEach((b) => b.fire('click'));
await flush(80);
ok(downloads.length === 3, '三个导出都真实产出内容', String(downloads.length));
const jsonReport = downloads.find((d) => d.name.endsWith('report-detail-') === false && d.mime === 'application/json' && /"answers"/.test(d.text));
ok(!!jsonReport, '含答卷明细的报告里有 answers 数组');
const csv = downloads.find((d) => d.mime.startsWith('text/csv'));
ok(!!csv && csv.text.startsWith('\ufeff題號') === false && /题号,题目,选项,分值/.test(csv.text), 'CSV 表头跟随简体语言', csv && csv.text.slice(0, 40));

// ---------------------------------------------------------------- 刷新重建（单页壳的门 2）
await goto('#/result/phq-9?lang=zh-CN');
ok(/中重度抑郁/.test(viewText()), '重新进入结果视图仍从存储重建结果', viewText().slice(0, 60));

// ---------------------------------------------------------------- 繁体路径
await goto('#/notice/phq-9?lang=zh-TW');
ok(/_PHQ|PHQ-9 抑鬱症篩檢量表/.test(viewText()), '繁体须知视图使用繁体标题', viewText().slice(0, 60));
ok(/開始作答/.test(viewText()), '繁体按钮文案为繁體', viewText().slice(-40));
const twCsv = fakeDoc.getElementById('view').find((el) => el.className === 'option-item');
twCsv[3] && twCsv[3].fire('click');

console.log(`\n共失败 ${FAILS.length} 项${FAILS.length ? '：' + FAILS.join('、') : ''}`);
process.exit(FAILS.length ? 1 : 0);
