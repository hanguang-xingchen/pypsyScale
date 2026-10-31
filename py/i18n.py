"""文案层：语言由显式参数决定，不靠 URL 路径嗅探。"""
from __future__ import annotations

DEFAULT_LANG = "zh-CN"
SUPPORTED_LANGS = ("zh-CN", "zh-TW")

# 近似回退：zh-HK / zh-MO 这类写法应落到繁体表，不能因为前缀相同被顺手丢给简体。
FALLBACK_ALIAS = {
    "zh-HK": "zh-TW",
    "zh-MO": "zh-TW",
    "zh-Hant": "zh-TW",
    "zh-Hans": "zh-CN",
    "zh": "zh-CN",
}


class I18nError(ValueError):
    pass


def pick_language(requested=None, available=None):
    available = tuple(available or SUPPORTED_LANGS)
    if requested in available:
        return requested
    if requested:
        for candidate in (requested, FALLBACK_ALIAS.get(requested)):
            if candidate in available:
                return candidate
        raise I18nError(f"不支持的语言：{requested}（可用：{', '.join(available)}）")
    return DEFAULT_LANG if DEFAULT_LANG in available else available[0]


class Catalog:
    def __init__(self, tables):
        # tables: {lang: {key: template}}
        self.tables = tables
        for lang, table in tables.items():
            missing = [key for key, value in table.items() if not isinstance(value, str)]
            if missing:
                raise I18nError(f"{lang} 的文案值必须是字符串：{missing}")
        self._check_parity()

    def _check_parity(self):
        langs = list(self.tables)
        if not langs:
            raise I18nError("没有任何语言文案")
        base = set(self.tables[langs[0]])
        for lang in langs[1:]:
            extra = set(self.tables[lang]) - base
            gap = base - set(self.tables[lang])
            if gap or extra:
                raise I18nError(
                    f"文案键不齐平：{lang} 缺 {sorted(gap)}，多 {sorted(extra)}"
                )

    def t(self, key, *, lang=None, **params):
        lang = lang or DEFAULT_LANG
        table = self.tables.get(lang, {})
        template = table.get(key)
        if template is None:
            raise I18nError(f"文案缺失：[{lang}] {key}")
        for name, value in params.items():
            template = template.replace("{" + name + "}", str(value))
        return template

    @classmethod
    def from_json_map(cls, raw):
        return cls({lang: dict(table) for lang, table in raw.items()})
