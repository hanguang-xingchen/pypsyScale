"""草稿与结果的存取：键语义在这里定义，浏览器能力靠 shim.js 的 Promise 桥。

Python 决定"存什么、用什么键、什么时候清"，shim 只负责把 IndexedDB 的回调式 API
变成可 await 的 Promise。
"""
from __future__ import annotations

import js
from pyodide.ffi import to_js

DRAFT_PREFIX = 'draft:'
RESULT_PREFIX = 'result:'


def _store():
    bridge = js.window.PSY
    if bridge is None:
        raise RuntimeError('shim.js 未加载，无法存取草稿')
    return bridge.store


def _to_js(value):
    # IndexedDB 只能结构化克隆 JS 原生对象；Python dict 必须转换，不能直接塞代理对象
    return to_js(value, dict_converter=js.Object.fromEntries)


def _from_js(value):
    if value is None:
        return None
    to_py = getattr(value, 'to_py', None)
    return to_py() if to_py else value


class DraftStore:
    async def save_draft(self, draft):
        await _store().put(DRAFT_PREFIX + draft['scaleId'], _to_js(draft))

    async def load_draft(self, scale_id):
        return _from_js(await _store().get(DRAFT_PREFIX + scale_id))

    async def clear_draft(self, scale_id):
        await _store().delete(DRAFT_PREFIX + scale_id)

    async def peek_draft(self):
        keys = _from_js(await _store().keys(DRAFT_PREFIX)) or []
        for key in keys:
            draft = _from_js(await _store().get(key))
            if draft and draft.get('answers'):
                return draft
        return None

    async def save_result(self, scale_id, payload):
        await _store().put(RESULT_PREFIX + scale_id, _to_js(payload))

    async def load_result(self, scale_id):
        return _from_js(await _store().get(RESULT_PREFIX + scale_id))
