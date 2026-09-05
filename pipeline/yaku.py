"""和訳の読み込みと検査(F-06 / F-07)。

**実行時に翻訳 API を呼ばない。** 訳はビルド前に書いてリポジトリに置き、
出荷物には焼き込む(SPEC §2・§7。課金経路をゼロにする)。

訳文には二つの検査を掛ける:

- **充填率を分子と分母で出す**(F-07)。「和訳あり」ではなく「628 件中 何件」と書く。
  訳していないものを訳したように見せない
- **字種検査**(G-08)。日本語の本文にキリル文字・ギリシア文字・不可視文字が混ざる事故は
  フリートで繰り返し起きている。字形が近く目視では気づけないので、機械で落とす
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YAKU_DIR = ROOT / "data" / "yaku"
GLOSSARY_PATH = ROOT / "data" / "glossary.json"

TITLE_FILES = ("titles-a.json", "titles-b.json", "titles-c.json", "titles-d.json")


def load_titles() -> dict[str, str]:
    """料理名の和訳。複数ファイルに分けてあるので合併する。鍵の重複は事故なので落とす。"""
    out: dict[str, str] = {}
    for name in TITLE_FILES:
        data = json.loads((YAKU_DIR / name).read_text(encoding="utf-8"))
        for rid, ja in data["titles"].items():
            if rid in out:
                raise ValueError(f"料理名の訳が重複している: {rid}({name})")
            out[rid] = ja
    return out


def load_sections() -> dict[str, str]:
    data = json.loads((YAKU_DIR / "sections.json").read_text(encoding="utf-8"))
    return data["sections"]


def load_glossary() -> list[dict[str, str]]:
    return json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))["terms"]


def load_bodies() -> dict[str, list[str]]:
    """レシピ本文の和訳(段落の配列)。未訳のレシピは鍵ごと存在しない。

    **章ごとにファイルを分ける。** 628 篇を一つの JSON に束ねると 1 MB を超え、
    一章だけ直したいときにファイル全体を書き直すことになる。鍵の重複は事故なので落とす。
    """
    out: dict[str, list[str]] = {}
    for path in sorted((YAKU_DIR / "bodies").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for rid, paragraphs in data["bodies"].items():
            if rid in out:
                raise ValueError(f"本文の訳が重複している: {rid}({path.name})")
            out[rid] = paragraphs
    return out


def load_leads() -> dict[str, list[str]]:
    """章の導入文(レシピ見出しの前に置かれた地の文)の和訳。"""
    path = YAKU_DIR / "leads.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))["leads"]


def load_discours() -> list[str]:
    """緒言(Discours préliminaire)の和訳。"""
    path = YAKU_DIR / "discours.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["paragraphs"]


# --- 字種検査(G-08)---------------------------------------------------------

# 和訳の本文に出てよい文字。ラテン文字は原語併記のために許す
ALLOWED_SCRIPTS = ("HIRAGANA", "KATAKANA", "CJK", "LATIN", "COMMON")
INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁯﻿]")


def script_of(ch: str) -> str:
    """文字の系統をおおまかに返す。名前の頭を見るだけの粗い判定で足りる。"""
    if ch.isspace() or not ch.isalnum():
        return "COMMON"
    if ch.isascii():  # 数字と ASCII の英字。原語併記と数値のために許す
        return "LATIN"
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return "UNKNOWN"
    # `々`(U+3005)は Unicode 名が IDEOGRAPHIC ITERATION MARK で始まり、
    # 文字種別は Lm(修飾文字)なので `isalnum()` を通る。前置きを増やさないと
    # **正しい日本語が落ちる** —— 2026-09-05 に「別々」で実際に落ちた
    for script in ("HIRAGANA", "KATAKANA", "CJK", "IDEOGRAPHIC", "LATIN", "GREEK", "CYRILLIC"):
        if name.startswith(script):
            return "CJK" if script == "IDEOGRAPHIC" else script
    return "OTHER"


def bad_characters(text: str) -> list[tuple[int, str, str]]:
    """許されない字種・不可視文字を位置つきで返す。"""
    out: list[tuple[int, str, str]] = []
    for m in INVISIBLE.finditer(text):
        out.append((m.start(), m.group(), "INVISIBLE"))
    for i, ch in enumerate(text):
        s = script_of(ch)
        if s not in ALLOWED_SCRIPTS:
            out.append((i, ch, s))
    return sorted(out)


def check_scripts() -> list[dict[str, object]]:
    """和訳の全文に字種検査を掛ける。違反を返す(空なら合格)。"""
    bad: list[dict[str, object]] = []
    sources: list[tuple[str, str]] = []
    sources += [(f"section:{k}", v) for k, v in load_sections().items()]
    sources += [(f"title:{k}", v) for k, v in load_titles().items()]
    for rid, paragraphs in load_bodies().items():
        sources += [(f"body:{rid}#{i}", p) for i, p in enumerate(paragraphs)]
    for term in load_glossary():
        sources.append((f"glossary:{term['fr']}", term["ja"]))
        if term.get("note"):
            sources.append((f"glossary-note:{term['fr']}", term["note"]))
    for where, text in sources:
        hits = bad_characters(text)
        if hits:
            bad.append({"where": where, "text": text, "hits": hits})
    return bad


# --- 充填率(F-07)-----------------------------------------------------------


def coverage() -> dict[str, object]:
    """訳の充填を**分子と分母で**出す。"""
    from pipeline.pg_parse import parse_sections

    sections = parse_sections()
    rids = [r.rid for s in sections for r in s.recipes]
    sids = [s.sid for s in sections]
    titles = load_titles()
    sec = load_sections()
    bodies = load_bodies()
    return {
        "recipes": len(rids),
        "titles_translated": sum(1 for rid in rids if rid in titles),
        "titles_missing": [rid for rid in rids if rid not in titles],
        "titles_extra": sorted(set(titles) - set(rids)),
        "sections": len(sids),
        "sections_translated": sum(1 for sid in sids if sid in sec),
        "sections_missing": [sid for sid in sids if sid not in sec],
        "bodies_translated": sum(1 for rid in rids if rid in bodies),
        "glossary_terms": len(load_glossary()),
    }


if __name__ == "__main__":
    c = coverage()
    print(f"章名     {c['sections_translated']:>4} / {c['sections']}")
    print(f"料理名   {c['titles_translated']:>4} / {c['recipes']}")
    print(f"本文     {c['bodies_translated']:>4} / {c['recipes']}")
    print(f"用語集   {c['glossary_terms']:>4} 語")
    if c["titles_missing"]:
        print(f"未訳の料理名: {c['titles_missing'][:20]}")  # type: ignore[index]
    if c["titles_extra"]:
        print(f"本文に無い鍵: {c['titles_extra']}")
    bad = check_scripts()
    print(f"字種検査: {'合格' if not bad else bad[:3]}")
