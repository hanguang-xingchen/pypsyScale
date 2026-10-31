"""壳的入口：由 PyScript 以 <script type="py" src="py/main.py"> 加载。

为什么还要自己装模块：PyScript 只负责执行入口脚本，兄弟模块的 import 路径在不同
版本里语义不一致（file mount / packages / files 行为都变过）。这里显式把 py/*.py
取进虚拟文件系统的 /psy 并插入 sys.path，行为可控、可测，也不依赖某个版本的糖。
"""
from __future__ import annotations

import pathlib
import sys

MODULES = [
    'schema', 'item_parser', 'scoring', 'i18n', 'charts', 'report',
    'resources', 'dom', 'draft_store', 'shell',
]
INSTALL_DIR = '/psy'


def _announce(message, state='warn'):
    try:
        from js import document

        badge = document.getElementById('engine-badge')
        if badge is not None:
            badge.textContent = message
            badge.className = f'badge badge-engine is-{state}' if state != 'ok' else 'badge badge-engine'
        boot = document.getElementById('boot-text')
        if boot is not None and state != 'ok':
            boot.textContent = message
    except Exception:
        pass


async def _fetch(relpath):
    try:
        from pyodide.http import pyfetch

        resp = await pyfetch(relpath)
        if resp.status == 200:
            return await resp.string()
    except Exception:
        pass
    return (pathlib.Path('/app') / relpath).read_text(encoding='utf-8')


async def bootstrap():
    pathlib.Path(INSTALL_DIR).mkdir(exist_ok=True)
    for name in MODULES:
        source = await _fetch(f'py/{name}.py')
        pathlib.Path(f'{INSTALL_DIR}/{name}.py').write_text(source, encoding='utf-8')
    if INSTALL_DIR not in sys.path:
        sys.path.insert(0, INSTALL_DIR)


try:
    await bootstrap()
    # 必须在 bootstrap 完成后动态导入，否则 shell.py 的顶层 import 会在 /psy 准备好之前触发
    import importlib
    _shell = importlib.import_module('shell')

    app = _shell.Shell()
    await app.start()
except Exception as exc:  # 启动失败要把话说清楚，而不是留一个转圈的加载态
    _announce(f"{type(exc).__name__}: {exc}", 'error')
    raise
