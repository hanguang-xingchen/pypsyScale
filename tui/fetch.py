"""TUI 数据源层：从静态 Pages 拉取 JSON/CSV，预留镜像与本地目录切换。

上层只调 fetch_text / fetch_json，不关心数据来自线上还是本地：
- 换镜像：设环境变量 PYSYSCALE_BASE 指向另一个静态根。
- 纯本地：把 LOCAL_ROOT 设成本地目录（未来 --install 用）。
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://hanguangxingchen.top/pypsyScale/"
LOCAL_ROOT = None  # 未来 install / 纯本地模式设成 Path 或 str


def base_url() -> str:
    return os.environ.get("PYSYSCALE_BASE") or DEFAULT_BASE


def fetch_text(relpath: str) -> str:
    relpath = relpath.lstrip("/")
    if LOCAL_ROOT is not None:
        return (Path(LOCAL_ROOT) / relpath).read_text(encoding="utf-8")
    req = urllib.request.Request(
        base_url() + relpath, headers={"User-Agent": "pysyscale-tui"}
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode("utf-8")


def fetch_json(relpath: str):
    return json.loads(fetch_text(relpath))