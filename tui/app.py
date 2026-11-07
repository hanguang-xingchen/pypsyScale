"""零依赖 curses TUI：量表选择 → 须知 → 逐题答题 → 结果。

数据现场请求（fetch 层），计分复用项目 py/scoring.py 同一套引擎，保证与
浏览器版行为一致。只用标准库，供 curl 单行拉起到临时目录后运行。
"""
from __future__ import annotations

import curses
import locale
import unicodedata

import fetch
from item_parser import parse_items
from scoring import score_scale

SCALE_BASE = "data/scales/"
LANG = "zh-CN"


# ---------------------------------------------------------------- 文本排版
def cell_width(text: str) -> int:
    """按终端列宽统计（CJK 全角计 2 列）。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def clip(text: str, width: int) -> str:
    """截断到不超过 width 列，避免 addstr 越界，也不把中文字符截一半。"""
    out = ""
    cw = 0
    for ch in text:
        chw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if cw + chw > width:
            break
        out += ch
        cw += chw
    return out


def wrap(text: str, width: int) -> "list[str]":
    """按显示宽度折行，中文字符占 2 列。"""
    lines = []
    cur = ""
    cw = 0
    for ch in text or "":
        if ch == "\n":
            lines.append(cur)
            cur = ""
            cw = 0
            continue
        chw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if cw + chw > width:
            lines.append(cur)
            cur = ch
            cw = chw
        else:
            cur += ch
            cw += chw
    if cur or not lines:
        lines.append(cur)
    return lines


class App:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.scales = []      # [(scale_id, title_zh)]
        self.cursor = 0
        self.mode = "select"  # select | notice | quiz | result
        self.scale = None     # 当前 scale.json（dict）
        self.items = []       # 当前题目（list[Item]）
        self.answers = {}     # {q_id: value}
        self.idx = 0
        self.result = None    # ScoreResult
        self.error = None

    # ------------------------------------------------------------ 主循环
    def run(self):
        self._flash("应用加载中，请稍候")
        self._load_scales()
        while True:
            self._draw()
            key = self.stdscr.getch()
            if not self._handle(key):
                return

    def _load_scales(self):
        try:
            for sid in fetch.fetch_json(SCALE_BASE + "index.json"):
                try:
                    scale = fetch.fetch_json(SCALE_BASE + sid + "/scale.json")
                    title = scale["title"][LANG]
                except Exception:
                    title = sid
                self.scales.append((sid, title))
        except Exception as exc:
            self.error = "加载量表列表失败：" + type(exc).__name__ + ": " + str(exc)

    # ------------------------------------------------------------ 按键分发
    def _handle(self, key):
        if key in (ord("q"), ord("Q")):
            return False
        if self.mode == "select":
            return self._handle_select(key)
        if self.mode == "notice":
            return self._handle_notice(key)
        if self.mode == "quiz":
            return self._handle_quiz(key)
        if self.mode == "result":
            return self._handle_result(key)
        return True

    def _handle_select(self, key):
        n = len(self.scales)
        if n == 0:
            return True
        if key in (curses.KEY_UP, ord("k")):
            self.cursor = (self.cursor - 1) % n
        elif key in (curses.KEY_DOWN, ord("j")):
            self.cursor = (self.cursor + 1) % n
        elif key in (curses.KEY_ENTER, 10, 13):
            self._enter_scale()
        return True

    def _handle_notice(self, key):
        if key in (curses.KEY_ENTER, 10, 13, ord(" ")):
            self._start_quiz()
        elif key in (ord("b"), ord("B")):
            self.mode = "select"
        return True

    def _handle_quiz(self, key):
        item = self.items[self.idx]
        for i, opt in enumerate(item.options):
            if key == ord(str(i + 1)):
                self.answers[item.q_id] = opt.value
                if self.idx < len(self.items) - 1:
                    self.idx += 1
                return True
        if key in (curses.KEY_LEFT, ord("p"), ord("P")):
            self.idx = max(0, self.idx - 1)
        elif key in (curses.KEY_RIGHT, ord("n"), ord("N")):
            self.idx = min(len(self.items) - 1, self.idx + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            if self.idx == len(self.items) - 1:
                self._submit()
        return True

    def _handle_result(self, key):
        if key in (ord("r"), ord("R")):
            self._start_quiz()
        elif key in (ord("b"), ord("B")):
            self.mode = "select"
        return True

    # ------------------------------------------------------------ 状态流转
    def _enter_scale(self):
        self._flash("量表加载中，请稍候")
        sid = self.scales[self.cursor][0]
        try:
            self.scale = fetch.fetch_json(SCALE_BASE + sid + "/scale.json")
            csv_name = self.scale["items"]["files"][LANG]
            self.items = parse_items(fetch.fetch_text(SCALE_BASE + sid + "/" + csv_name))
            self.answers = {}
            self.idx = 0
            self.result = None
            self.error = None
            self.mode = "notice"
        except Exception as exc:
            self.error = "加载量表失败：" + type(exc).__name__ + ": " + str(exc)

    def _start_quiz(self):
        self.answers = {}
        self.idx = 0
        self.result = None
        self.mode = "quiz"

    def _submit(self):
        missing = [it.q_id for it in self.items if it.q_id not in self.answers]
        if missing:
            for i, it in enumerate(self.items):
                if it.q_id == missing[0]:
                    self.idx = i
                    break
            return
        try:
            self.result = score_scale(self.scale, self.items, dict(self.answers), language=LANG)
            self.mode = "result"
        except Exception as exc:
            self.error = "计分失败：" + type(exc).__name__ + ": " + str(exc)

    # ------------------------------------------------------------ 绘制
    def _flash(self, text):
        """加载期间的一屏居中提示。"""
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        title = "pypsyScale-TUI"
        self._add(h // 2 - 1, max(0, (w - cell_width(title)) // 2), title, curses.A_BOLD)
        self._add(h // 2, max(0, (w - cell_width(text)) // 2), text, curses.A_BOLD)
        self.stdscr.refresh()

    def _draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if w < 20 or h < 5:
            try:
                self.stdscr.addstr(0, 0, "窗口太小")
            except curses.error:
                pass
            self.stdscr.refresh()
            return
        if self.mode == "select":
            self._draw_select(h, w)
        elif self.mode == "notice":
            self._draw_notice(h, w)
        elif self.mode == "quiz":
            self._draw_quiz(h, w)
        else:
            self._draw_result(h, w)
        self.stdscr.refresh()

    def _add(self, y, x, text, attr=0):
        maxy, maxx = self.stdscr.getmaxyx()
        if y < 0 or y >= maxy:
            return
        try:
            self.stdscr.addstr(y, x, clip(text, maxx - x - 1), attr)
        except curses.error:
            pass

    def _draw_error(self, w):
        if self.error:
            self._add(0, 0, "⚠ " + self.error)
            return 1
        return 0

    def _draw_select(self, h, w):
        top = self._draw_error(w)
        self._add(top, 0, "pypsyScale 量表（终端版）", curses.A_BOLD)
        top += 1
        if not self.scales:
            self._add(top, 0, "（暂无量表，按 q 退出）")
            self._add(h - 1, 0, "q 退出")
            return
        for i, (_sid, title) in enumerate(self.scales):
            y = top + i
            if y >= h - 1:
                break
            line = "  " + str(i + 1) + ". " + title
            if i == self.cursor:
                self._add(y, 0, line, curses.A_REVERSE)
            else:
                self._add(y, 0, line)
        self._add(h - 1, 0, "↑/↓ 或 j/k 选择   回车 进入   q 退出")

    def _draw_notice(self, h, w):
        top = self._draw_error(w)
        scale = self.scale
        self._add(top, 0, scale["title"][LANG], curses.A_BOLD)
        y = top + 1
        rows = []
        rows += wrap(scale["description"][LANG], w - 1)
        rows.append("")
        rows.append("【指导语】")
        rows += wrap(scale["instruction"][LANG], w - 1)
        rows.append("")
        meta = scale.get("meta", {})
        author_year = (meta.get("author") or "") + (
            (" " + str(meta.get("year"))) if meta.get("year") else ""
        )
        tail = "共 " + str(len(self.items)) + " 题"
        if author_year:
            tail += " · " + author_year
        rows.append(tail)
        for line in rows:
            if y >= h - 1:
                break
            self._add(y, 0, line)
            y += 1
        self._add(h - 1, 0, "回车 开始答题   b 返回   q 退出")

    def _draw_quiz(self, h, w):
        top = self._draw_error(w)
        item = self.items[self.idx]
        total = len(self.items)
        self._add(top, 0, f"第 {self.idx + 1} / {total} 题", curses.A_BOLD)
        y = top + 1
        for line in wrap(item.text, w - 1):
            if y >= h - 1:
                break
            self._add(y, 0, line)
            y += 1
        y += 1
        selected = self.answers.get(item.q_id)
        for i, opt in enumerate(item.options):
            if y >= h - 1:
                break
            mark = "*" if opt.value == selected else " "
            line = f" {mark} {i + 1}. {opt.text}"
            if opt.value == selected:
                self._add(y, 0, line, curses.A_REVERSE)
            else:
                self._add(y, 0, line)
            y += 1
        self._add(h - 1, 0,
                  f"数字键 1-{len(item.options)} 选择   ←/→ 或 P/N 切题   末题回车提交   q 退出")

    def _draw_result(self, h, w):
        top = self._draw_error(w)
        r = self.result
        self._add(top, 0, self.scale["title"][LANG] + " —— 结果", curses.A_BOLD)
        y = top + 1
        rows = [
            f"报告分 {r.report_score}（等级：{r.level}）",
            f"粗分 {r.raw_total} · 题数 {r.item_count} · 均分 {r.mean}",
            "",
            "【解读建议】",
        ]
        rows += wrap(r.advice, w - 1)
        for line in rows:
            if y >= h - 1:
                break
            self._add(y, 0, line)
            y += 1
        if r.method == "dimension_sum" and r.dimensions:
            y += 1
            if y < h - 1:
                self._add(y, 0, "【因子明细】", curses.A_BOLD)
            y += 1
            for d in r.dimensions:
                if y >= h - 1:
                    break
                self._add(y, 0, f"  {d['name']}  均分 {d['mean']:.2f}  {d['level']}")
                y += 1
        self._add(h - 1, 0, "r 重测   b 返回列表   q 退出")


def main():
    try:
        locale.setlocale(locale.LC_ALL, "")
    except Exception:
        pass
    curses.wrapper(_run)


def _run(stdscr):
    try:
        curses.curs_set(0)
    except Exception:
        pass
    App(stdscr).run()


if __name__ == "__main__":
    main()