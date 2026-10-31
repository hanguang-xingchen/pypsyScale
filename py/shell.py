"""单页壳：须知 / 答题 / 结果 三视图 + hash 路由 + 视图生命周期。

设计约束的落地位置：
- 视图根节点 #view 归本模块独占，元素用 h() 构建，不拼 innerHTML
- 每次切换先 dispose 上一视图的监听器与图表，避免重复绑定与残留 trace
- 状态不依赖内存：路由变化一律从 store 重建（刷新、前进后退都走同一条路）
- 异步对话框只认 close 事件收口，Esc 关闭也能正常返回
"""
from __future__ import annotations

import asyncio
import json
import time

import js
from pyodide.ffi import create_proxy, to_js

import charts
import dom
import report as report_mod
from draft_store import DraftStore
from i18n import Catalog, pick_language
from item_parser import parse_items
from resources import fetch_json, fetch_text
from schema import ScaleSchemaError
from scoring import ScoringError, score_scale

SCALE_BASE = 'data/scales/'
VIEWS = ('notice', 'scale', 'result')


def spawn(coro):
    """事件回调里安全启动异步任务（JS 无法 await Python 协程）。"""
    return asyncio.ensure_future(coro)


def parse_hash(raw):
    """#/result/phq-9?lang=zh-TW → ('result','phq-9',{'lang':'zh-TW'})"""
    text = (raw or '').lstrip('#/').split('?')
    path = [seg for seg in text[0].split('/') if seg]
    params = {}
    if len(text) > 1:
        for pair in text[1].split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                params[key] = value
    view = path[0] if path and path[0] in VIEWS else None
    scale_id = path[1] if len(path) > 1 else None
    return view, scale_id, params


class Shell:
    def __init__(self):
        self.store = DraftStore()
        self.ui = None
        self.scales = []
        self.cache = {}
        self.bag = None
        self.chart_nodes = []
        self.view = None
        self.scale_id = None
        self.lang = 'zh-CN'
        self.current = None

    # ------------------------------------------------------------ 生命周期
    async def start(self):
        self.ui = Catalog.from_json_map(await fetch_json('locales/ui.json'))
        self.scales = await fetch_json(SCALE_BASE + 'index.json')
        js.window.addEventListener('hashchange', create_proxy(lambda *_: spawn(self.route())))
        dom.set_badge('ok', self.t('engine_ready'))
        await self.route()

    def t(self, key, **params):
        return self.ui.t(key, lang=self.lang, **params)

    def goto(self, view, scale_id, **params):
        query = '&'.join(f'{k}={v}' for k, v in params.items()) if params else ''
        js.window.location.hash = f'#/{view}/{scale_id}' + (f'?{query}' if query else '')

    async def route(self, *_):
        view, scale_id, params = parse_hash(js.window.location.hash)
        if not scale_id:
            self.goto(VIEWS[0] if view is None else 'notice', self.scales[0])
            return
        self.lang = pick_language(params.get('lang'))
        dom.doc().documentElement.lang = self.lang
        self.view, self.scale_id = view or 'notice', scale_id
        try:
            await self.render()
        except (ScaleSchemaError, ScoringError) as exc:
            self.render_error(str(exc))
        except Exception as exc:  # 不让单个视图异常把整个壳带崩
            self.render_error(f'{type(exc).__name__}: {exc}')

    async def render(self):
        """视图分发：根节点先解绑上一视图的监听器与图表，再按当前路由渲染。"""
        root = self.root()
        if self.view == 'scale':
            await self.view_scale(root)
        elif self.view == 'result':
            await self.view_result(root)
        else:
            await self.view_notice(root)

    def _unmount(self):
        if self.bag:
            self.bag.dispose()
        bridge = js.window.PSY
        for node in self.chart_nodes:
            try:
                bridge.chart.purge(node)
            except Exception:
                pass
        self.chart_nodes.clear()
        self.bag = dom.ListenerBag()

    def root(self):
        self._unmount()
        by_id = dom.by_id
        by_id('boot').hidden = True
        root = by_id('view')
        dom.clear(root)
        root.hidden = False
        return root

    def render_error(self, message):
        root = self.root()
        dom.set_badge('error', self.t('engine_failed'))
        dom.add(root, dom.h('div', cls='card', text=self.t('load_failed')),
                dom.h('p', cls='hint', text=message),
                dom.h('a', cls='btn btn-ghost', attrs={'href': 'index.html'}, text=self.t('btn_back_home')))

    # ------------------------------------------------------------ 数据装载
    async def load_scale(self, scale_id, lang):
        key = (scale_id, lang)
        if key not in self.cache:
            folder = f'{SCALE_BASE}{scale_id}/'
            scale = await fetch_json(folder + 'scale.json')
            files = scale.get('items', {}).get('files', {})
            csv_name = files.get(lang) or files.get('zh-CN')
            if not csv_name:
                raise ScaleSchemaError(f'{scale_id} 缺少 {lang} 题目文件')
            items = parse_items(await fetch_text(folder + csv_name))
            self.cache[key] = (scale, items)
        return self.cache[key]

    def localized(self, field):
        return field[self.lang] if isinstance(field, dict) else field

    # ------------------------------------------------------------ 须知视图
    async def view_notice(self, root):
        scale, items = await self.load_scale(self.scale_id, self.lang)
        card = dom.h('div', cls='card stack')
        dom.add(card,
                dom.h('h2', text=self.localized(scale['title'])),
                dom.h('p', cls='scale-desc', text=self.localized(scale['description'])),
                dom.h('h2', text=self.t('notice_title')),
                dom.h('p', text=self.localized(scale['instruction'])),
                dom.h('p', cls='hint', text=self.t('notice_privacy')),
                dom.h('p', cls='hint', text=f"{len(items)} {self.t('result_items')} · "
                                            f"{scale.get('meta', {}).get('author', '')} "
                                            f"{scale.get('meta', {}).get('year', '')}"))
        start = dom.h('button', cls='btn btn-primary btn-full', text=self.t('btn_start'), el_id='btn-start')
        self.bag.on(start, 'click', lambda *_: spawn(self.begin()))
        dom.add(card, start)
        dom.add(root, card)

    async def begin(self):
        await self.store.clear_draft(self.scale_id)
        await self.store.save_draft({
            'scaleId': self.scale_id, 'lang': self.lang,
            'answers': {}, 'currentIndex': 0, 'timestamp': int(time.time() * 1000),
        })
        self.goto('scale', self.scale_id, lang=self.lang)

    # ------------------------------------------------------------ 答题视图
    async def view_scale(self, root):
        scale, items = await self.load_scale(self.scale_id, self.lang)
        draft = await self.store.load_draft(self.scale_id)
        if not draft:
            self.goto('notice', self.scale_id, lang=self.lang)
            return
        draft.setdefault('answers', {})
        index = min(int(draft.get('currentIndex') or 0), len(items) - 1)
        self.current = {'scale': scale, 'items': items, 'draft': draft, 'index': index}

        head = dom.h('div', cls='card stack')
        progress = dom.h('div', cls='progress')
        fill = dom.h('div', cls='progress-fill', el_id='progress-fill')
        dom.add(progress, fill)
        q_index = dom.h('p', cls='q-index', el_id='q-index')
        q_text = dom.h('p', cls='q-text', el_id='q-text')
        options = dom.h('div', cls='option-list', el_id='option-list')
        sheet = dom.h('div', cls='sheet', el_id='sheet')
        nav = dom.h('div', cls='btn-row')
        prev = dom.h('button', cls='btn btn-ghost', el_id='btn-prev', text=self.t('btn_prev'))
        nxt = dom.h('button', cls='btn btn-primary', el_id='btn-next', text=self.t('btn_next'))
        dom.add(nav, prev, nxt)
        dom.add(head, q_index, progress, q_text, options, sheet, nav)
        dom.add(root, head)

        self.bag.on(prev, 'click', lambda *_: spawn(self.move(-1)))
        self.bag.on(nxt, 'click', lambda *_: spawn(self.advance()))

        self.render_question()

    def render_question(self):
        state = self.current
        items, draft = state['items'], state['draft']
        idx = state['index']
        item = items[idx]
        selected = draft['answers'].get(str(item.q_id))

        dom.by_id('q-index').textContent = self.t('question_progress', current=idx + 1, total=len(items))
        dom.by_id('q-text').textContent = item.text
        dom.by_id('progress-fill').style.width = f'{int((idx + 1) / len(items) * 100)}%'

        list_node = dom.clear(dom.by_id('option-list'))
        for opt in item.options:
            row = dom.h('label', cls='option-item' + (' selected' if selected == opt.value else ''))
            mark = dom.h('span', text=opt.text)
            dom.add(row, dom.h('input', attrs={'type': 'radio', 'name': f'q_{item.q_id}'}), mark)
            if selected == opt.value:
                row.firstChild.checked = True
            self.bag.on(row, 'click', lambda _ev, value=opt.value, qid=item.q_id: spawn(self.pick(qid, value)))
            dom.add(list_node, row)

        sheet_node = dom.clear(dom.by_id('sheet'))
        for pos, each in enumerate(items):
            answered = str(each.q_id) in draft['answers']
            cell = dom.h('div', cls='sheet-cell' + (' answered' if answered else '') + (' current' if pos == idx else ''),
                         text=str(each.q_id))
            if answered:
                self.bag.on(cell, 'click', lambda _ev, target=pos: spawn(self.jump(target)))
            dom.add(sheet_node, cell)

        last = idx == len(items) - 1
        dom.by_id('btn-next').textContent = self.t('btn_submit') if last else self.t('btn_next')
        dom.by_id('btn-next').disabled = selected is None
        dom.by_id('btn-prev').disabled = idx == 0

    async def pick(self, qid, value):
        state = self.current
        state['draft']['answers'][str(qid)] = value
        state['draft']['timestamp'] = int(time.time() * 1000)
        await self.store.save_draft(state['draft'])
        self.render_question()

    async def move(self, delta):
        state = self.current
        target = max(0, min(state['index'] + delta, len(state['items']) - 1))
        await self.jump(target)

    async def jump(self, target):
        state = self.current
        state['index'] = int(target)
        state['draft']['currentIndex'] = state['index']
        await self.store.save_draft(state['draft'])   # psyScale 从没写回这个字段，恢复时永远回到第 1 题
        self.render_question()

    async def advance(self):
        state = self.current
        if state['index'] < len(state['items']) - 1:
            await self.move(1)
            return
        missing = [it.q_id for it in state['items'] if str(it.q_id) not in state['draft']['answers']]
        if missing:
            answer = await js.window.PSY.askConfirm(
                self.t('error_unanswered', n=len(missing), qids='、'.join(str(q) for q in missing)),
                self.t('btn_next'), self.t('btn_back_home'))
            if answer == 'yes':
                await self.jump(state['items'].index(next(it for it in state['items'] if it.q_id == missing[0])))
            return
        await self.submit()

    async def submit(self):
        state = self.current
        scale, items, answers = state['scale'], state['items'], state['draft']['answers']
        typed = {int(k): v for k, v in answers.items()}
        result = score_scale(scale, items, typed, language=self.lang)
        payload = result.json()
        payload['scaleTitle'] = self.localized(scale['title'])
        await self.store.save_result(self.scale_id, payload)
        await self.store.clear_draft(self.scale_id)
        self.goto('result', self.scale_id, lang=self.lang)

    # ------------------------------------------------------------ 结果视图
    async def view_result(self, root):
        payload = await self.store.load_result(self.scale_id)
        if not payload:
            card = dom.h('div', cls='card stack')
            dom.add(card, dom.h('p', text=self.t('empty_result')),
                    dom.h('a', cls='btn btn-primary',
                          attrs={'href': f'#notice/{self.scale_id}?lang={self.lang}'},
                          text=self.t('btn_start')))
            dom.add(root, card)
            return

        scale, items = await self.load_scale(payload['scaleId'], payload['language'])
        self.lang = payload['language']
        color = payload['color']

        card = dom.h('div', cls='card stack')
        score = dom.h('div', cls='score-big', text=str(payload['report_score']))
        score.style.color = color
        pill = dom.h('span', cls='level-pill', text=payload['level'])
        pill.style.background = color
        meta = dom.h('div', cls='meta-grid')
        for label, value in ((self.t('result_score'), payload['raw_total']),
                             (self.t('result_items'), payload['item_count']),
                             (self.t('result_mean'), payload['mean'])):
            block = dom.h('div')
            dom.add(block, dom.h('b', text=str(value)), dom.h('span', text=label))
            dom.add(meta, block)
        if payload.get('raw_factor', payload) and scale['scoring']['transform']['raw_factor'] != 1:
            pass  # 预留：报告分与粗分不同时并列展示
        dom.add(card,
                dom.h('h2', text=payload['scaleTitle']),
                dom.h('p', cls='q-index', text=self.t('result_score')),
                score, pill, meta,
                dom.h('h2', text=self.t('result_advice')),
                dom.h('p', cls='advice', text=payload['advice']))
        for flag in payload.get('flags', []):
            dom.add(card, dom.h('p', cls='flag-box', text=self.t('flag_' + flag)))
        dom.add(root, card)

        await self.render_charts(root, scale, items, payload)
        self.render_actions(root, scale, items, payload)

    async def render_charts(self, root, scale, items, payload):
        holder = dom.h('div', cls='card stack')
        dom.add(holder, dom.h('h2', text=self.t('chart_item_title')))
        plotly_node = dom.h('div', cls='chart-holder', el_id='chart-items')
        band_node = dom.h('div', cls='chart-holder', el_id='chart-band')
        dom.add(holder, plotly_node, band_node)
        dom.add(root, holder)
        self.chart_nodes.extend([plotly_node, band_node])

        try:
            await self.ensure_plotly_python()
            fig_items = charts.item_bar_figure(self.rehydrate(scale, items, payload), items, t=self.ui.t,
                                               lang_labels={'answered': self.t('chart_item_answered')})
            fig_band = charts.band_position_figure(self.rehydrate(scale, items, payload), scale, t=self.ui.t)
            await js.window.PSY.chart.render(plotly_node, to_js(json.loads(figures_to_json(fig_items)),
                                                               dict_converter=js.Object.fromEntries))
            await js.window.PSY.chart.render(band_node, to_js(json.loads(figures_to_json(fig_band)),
                                                              dict_converter=js.Object.fromEntries))
        except Exception as exc:
            dom.set_badge('warn', self.t('chart_fallback_note'))
            self.render_bar_fallback(holder, items, payload)
            dom.add(holder, dom.h('p', cls='hint', text=f'{type(exc).__name__}: {exc}'))

    def rehydrate(self, scale, items, payload):
        """从存储结果重建 ScoreResult，供图表层使用（不再重复计分）。"""
        from scoring import ScoreResult

        band = scale['bands'][payload['band_index']]
        return ScoreResult(
            scale_id=payload['scaleId'], method=payload['method'], language=payload['language'],
            raw_total=payload['raw_total'], report_score=payload['report_score'], mean=payload['mean'],
            band_index=payload['band_index'], band=band, item_count=payload['item_count'],
            answers=payload['answers'], flags=payload.get('flags', []), extra=payload.get('extra', {}),
        )

    def render_bar_fallback(self, holder, items, payload):
        grid = dom.h('div', cls='chart-fallback')
        cap = max(max(o.value for o in it.options) for it in items)
        for item, value in zip(items, payload['answers']):
            row = dom.h('div', cls='bar')
            track = dom.h('div', cls='bar-track')
            fill = dom.h('div', cls='bar-fill')
            fill.style.width = f'{float(value) / cap * 100}%'
            dom.add(track, fill)
            dom.add(row, dom.h('span', text=f'Q{item.q_id}'), track, dom.h('span', text=str(value)))
            dom.add(grid, row)
        dom.add(holder, grid)

    def render_actions(self, root, scale, items, payload):
        bar = dom.h('div', cls='card stack')
        dom.add(bar, dom.h('h2', text=self.t('download_menu')))
        row = dom.h('div', cls='btn-row')
        result_obj = self.rehydrate(scale, items, payload)
        for label, kind in ((self.t('download_report'), 'std'),
                            (self.t('download_report_detail'), 'detail'),
                            (self.t('download_csv'), 'csv')):
            button = dom.h('button', cls='btn btn-ghost', text=label)
            self.bag.on(button, 'click', lambda *_ , kind=kind: self.download(kind, scale, items, result_obj, payload))
            dom.add(row, button)
        retry = dom.h('button', cls='btn btn-primary', text=self.t('btn_retry'))
        self.bag.on(retry, 'click', lambda *_: spawn(self.begin()))
        dom.add(bar, row, retry, dom.h('p', cls='hint', text=self.t('disclaimer')))
        dom.add(root, bar)

    def download(self, kind, scale, items, result_obj, payload):
        bridge = js.window.PSY
        day = time.strftime('%Y-%m-%d')
        if kind == 'csv':
            text = report_mod.detail_csv(result_obj, items, headers=self.t('csv_headers').split(','), generated=day)
            bridge.download(f"{payload['scaleId']}-detail-{day}.csv", 'text/csv;charset=utf-8', '\ufeff' + text)
        elif kind == 'detail':
            bridge.download(f"{payload['scaleId']}-report-detail-{day}.json", 'application/json',
                            report_mod.report_json(result_obj, with_answers=True, generated=day))
        else:
            bridge.download(f"{payload['scaleId']}-report-{day}.json", 'application/json',
                            report_mod.report_json(result_obj, generated=day))

    # ------------------------------------------------------------ Plotly 惰性准备
    _plotly_ready = False

    async def ensure_plotly_python(self):
        if Shell._plotly_ready:
            return
        import micropip

        await micropip.install('plotly', quiet=True)
        Shell._plotly_ready = True


def figures_to_json(fig):
    return charts.figure_to_json(fig)
