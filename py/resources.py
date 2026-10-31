"""资源读取：浏览器走 HTTP，测试环境（Node 里的 Pyodide）退回虚拟文件系统。

统一从这里取文本，避免 shell 与引擎各处直接依赖 pyfetch，也让同一份代码
在没有网络的文件系统镜像下可测。
"""
from __future__ import annotations

from pathlib import Path


class ResourceError(RuntimeError):
    pass


async def fetch_text(relpath: str) -> str:
    relpath = relpath.lstrip('/')
    try:  # 浏览器：相对 app.html 的路径，同源，GitHub Pages 直接可用
        from pyodide.http import pyfetch

        resp = await pyfetch(relpath)
        if resp.status != 200:
            raise ResourceError(f"{relpath} → HTTP {resp.status}")
        return await resp.string()
    except ImportError:
        pass
    except Exception as exc:
        last = exc
    else:
        # pyfetch 在 Node 下也存在，但相对 URL 无法解析，落到文件系统分支
        last = None

    for candidate in (Path('/app') / relpath, Path(relpath)):
        try:
            return candidate.read_text(encoding='utf-8')
        except OSError:
            continue
    raise ResourceError(f"读取失败：{relpath}（{last}）")


async def fetch_json(relpath: str):
    import json

    return json.loads(await fetch_text(relpath))
