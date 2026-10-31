"""DOM 层薄封装 + 监听器生命周期管理。

约定（对应设计里的"DOM 所有权"约束）：
- 视图根节点内的元素一律用本模块的 h() 构建，不用 innerHTML 拼串（避免注入与解析歧义）
- 每个视图的监听器登记在 ListenerBag 里，视图卸载时统一 removeEventListener + proxy.destroy()
- Plotly 容器与 dialog 归 shim.js 私有，本模块只负责把它们挂到树上，不碰内部
"""
from __future__ import annotations

import js
from pyodide.ffi import create_proxy


def doc():
    return js.document


def by_id(element_id):
    return doc().getElementById(element_id)


def h(tag, *, cls=None, el_id=None, text=None, attrs=None, hidden=None):
    node = doc().createElement(tag)
    if cls:
        node.className = cls
    if el_id:
        node.id = el_id
    if text is not None:
        node.textContent = str(text)
    if hidden:
        node.hidden = True
    for key, value in (attrs or {}).items():
        node.setAttribute(key, str(value))
    return node


def add(parent, *children):
    for child in children:
        if child is not None:
            parent.appendChild(child)
    return parent


def clear(node):
    while node.firstChild:
        node.removeChild(node.firstChild)
    return node


def set_badge(state, text):
    badge = by_id('engine-badge')
    if badge is None:
        return
    badge.textContent = text
    badge.className = 'badge badge-engine' + ('' if state == 'ok' else f' is-{state}')


class ListenerBag:
    """当前视图的监听器登记表。"""

    def __init__(self):
        self._items = []

    def on(self, node, event, handler):
        proxy = create_proxy(handler)
        node.addEventListener(event, proxy)
        self._items.append((node, event, proxy))
        return proxy

    def dispose(self):
        for node, event, proxy in self._items:
            try:
                node.removeEventListener(event, proxy)
            except Exception:
                pass
            try:
                proxy.destroy()
            except Exception:
                pass
        self._items.clear()
