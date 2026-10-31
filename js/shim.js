/* js/shim.js — 浏览器能力桥
 *
 * 边界（重要）：这里只做"浏览器 API 的形状适配"，不含任何量表语义、判定或渲染策略。
 *   - IndexedDB 的回调式 API 包装成 Promise，键与值语义由 Python 决定
 *   - Plotly 的挂载/卸载与按需加载脚本
 *   - Blob 下载
 *   - dialog 的 Promise 收口（含 Esc 关闭，避免只绑按钮导致流程永久挂起）
 * 引擎未就绪时 Python 会用到 window.PSY 的缺失，因此本文件必须在 PyScript 之前加载。
 */
(function () {
  'use strict';

  const DB_NAME = 'pysyscale';
  const DB_VERSION = 1;
  const STORE = 'kv';
  const memory = new Map();          // 无 IndexedDB 时的降级容器
  let dbPromise = null;

  function hasIDB() {
    return typeof indexedDB !== 'undefined' && indexedDB !== null;
  }

  function openDB() {
    if (!dbPromise) {
      dbPromise = new Promise((resolve, reject) => {
        try {
          const req = indexedDB.open(DB_NAME, DB_VERSION);
          req.onupgradeneeded = () => req.result.createObjectStore(STORE);
          req.onsuccess = () => resolve(req.result);
          req.onerror = () => reject(req.error);
          req.onblocked = () => reject(new Error('IndexedDB blocked'));
        } catch (err) {
          reject(err);
        }
      });
    }
    return dbPromise;
  }

  async function idbOp(mode, fn) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const req = fn(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(req ? req.result : undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error('transaction aborted'));
    });
  }

  // IDB 不支持结构化克隆 undefined；存 undefined 等价于删除
  async function storePut(key, value) {
    if (!hasIDB()) { memory.set(key, value); return; }
    if (value === undefined || value === null) return storeDelete(key);
    try {
      return await idbOp('readwrite', (s) => s.put(value, key));
    } catch (err) {
      console.warn('IndexedDB 写入失败，降级到内存', err);
      memory.set(key, value);
    }
  }

  async function storeGet(key) {
    if (!hasIDB()) return memory.has(key) ? memory.get(key) : null;
    try {
      const got = await idbOp('readonly', (s) => s.get(key));
      if (got === undefined && memory.has(key)) return memory.get(key);
      return got === undefined ? null : got;
    } catch (err) {
      console.warn('IndexedDB 读取失败，回退内存', err);
      return memory.has(key) ? memory.get(key) : null;
    }
  }

  async function storeDelete(key) {
    if (!hasIDB()) { memory.delete(key); return; }
    try {
      return await idbOp('readwrite', (s) => s.delete(key));
    } catch (err) {
      memory.delete(key);
    }
  }

  async function storeKeys(prefix) {
    if (!hasIDB()) return [...memory.keys()].filter((k) => k.startsWith(prefix));
    try {
      const keys = await idbOp('readonly', (s) => s.getAllKeys());
      const all = new Set([...(keys || []), ...memory.keys()]);
      return [...all].filter((k) => k.startsWith(prefix));
    } catch (err) {
      return [...memory.keys()].filter((k) => k.startsWith(prefix));
    }
  }

  const scriptCache = new Map();
  function loadScript(src) {
    if (!scriptCache.has(src)) {
      scriptCache.set(src, new Promise((resolve, reject) => {
        const el = document.createElement('script');
        el.src = src;
        el.async = true;
        el.onload = () => resolve(true);
        el.onerror = () => { scriptCache.delete(src); reject(new Error('脚本加载失败：' + src)); };
        document.head.appendChild(el);
      }));
    }
    return scriptCache.get(src);
  }

  const PLOTLY_SRC = 'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@3.0.1/plotly.min.js';

  async function ensurePlotly() {
    if (window.Plotly) return true;
    await loadScript(PLOTLY_SRC);
    if (!window.Plotly) throw new Error('Plotly 加载完成但全局对象不存在');
    return true;
  }

  async function renderChart(node, figure) {
    await ensurePlotly();
    // Plotly.react：同一节点重复渲染不会残留旧 trace（视图切走时另有 purge）
    window.Plotly.react(node, figure.data || [], figure.layout || {}, {
      responsive: true,
      displayModeBar: false,
    });
    return true;
  }

  function purgeChart(node) {
    try {
      if (window.Plotly && node && node.data) window.Plotly.purge(node);
    } catch (err) {
      console.warn('Plotly purge 失败', err);
    }
  }

  function download(filename, mime, text) {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return true;
  }

  /* dialog 收口：resolve 挂在 'close' 事件上， returnValue 区分 yes / no / null（Esc 或遮罩关闭）。
     psyScale 现行实现只绑两个按钮，用户按 Esc 后等待按钮的 Promise 永不 resolve。 */
  function askConfirm(text, yesLabel, noLabel) {
    const dlg = document.getElementById('dialog');
    const body = document.getElementById('dialog-text');
    const yes = document.getElementById('dialog-yes');
    const no = document.getElementById('dialog-no');
    if (!dlg || typeof dlg.showModal !== 'function') {
      return Promise.resolve(window.confirm(text) ? 'yes' : 'no');
    }
    body.textContent = text;
    yes.textContent = yesLabel || '确定';
    no.textContent = noLabel || '取消';
    return new Promise((resolve) => {
      const onClose = () => {
        yes.removeEventListener('click', onYes);
        no.removeEventListener('click', onNo);
        dlg.removeEventListener('close', onClose);
        resolve(dlg.returnValue || null);
      };
      const onYes = () => { dlg.returnValue = 'yes'; dlg.close(); };
      const onNo = () => { dlg.returnValue = 'no'; dlg.close(); };
      yes.addEventListener('click', onYes);
      no.addEventListener('click', onNo);
      dlg.addEventListener('close', onClose);
      dlg.showModal();
    });
  }

  function ready() {
    return !!(window.indexedDB || true);
  }

  window.PSY = {
    version: 1,
    hasIDB,
    store: { get: storeGet, put: storePut, delete: storeDelete, keys: storeKeys },
    chart: { ensurePlotly, render: renderChart, purge: purgeChart },
    download,
    askConfirm,
    ready,
  };
})();
