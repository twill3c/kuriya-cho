"""フランス語の語の切り出し(F-04 / F-05 の土台)。

**綴りの検算をする前に、語の切り出しを正しくしておかなければならない。**
最初に素朴に切って現代語彙集に当てたところ、当たらなかった語の上位は
綴りの古さではなく切り出しの失敗だった(2026-09-05 実測・全 76,814 トークン):

- `d’` `l’` `qu’` の省略形の頭(`d` 1,436 回・`l` 841 回・`qu` 468 回)
- 命令形に付く接語(`faites-les` 272 回・`mettez-y` 167 回)。語彙集はこの形を持たない
- 合字(`œufs` `bœuf`)。語彙集は `oeufs` `boeuf` で持っている

この三つを直さずに「語彙集に載る率」を測ると、綴り規則の効きを大きく取り違える。

ここでの切り出しは**表示のためではなく照合のため**である。原文の見た目は一切変えない
(色分けと三層表示は原文の文字位置をそのまま使う)。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# 語 = 文字の並び。ハイフンとアポストロフィは語の中に含めたまま切り、あとで分解する
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœÆæ]+(?:[-’'][A-Za-zÀ-ÖØ-öø-ÿŒœÆæ]+)*")

# 省略形の頭。`d’huile` の `d’` は語彙集に無いが、古い綴りでもない
ELISION_HEADS = {
    "c": "ce",
    "d": "de",
    "j": "je",
    "l": "le",
    "m": "me",
    "n": "ne",
    "s": "se",
    "t": "te",
    "qu": "que",
    "jusqu": "jusque",
    "lorsqu": "lorsque",
    "puisqu": "puisque",
    "quoiqu": "quoique",
    "presqu": "presque",
    # `aujourd’hui` は入れない。頭を切ると `hui` という語でない断片が残る
    # (語彙集は `aujourd'hui` を一語で持っている)
}

# 命令形に付く接語。`servez-vous-en` のように重なる
CLITICS = (
    "le",
    "la",
    "les",
    "lui",
    "leur",
    "y",
    "en",
    "moi",
    "toi",
    "nous",
    "vous",
    "ce",
    "il",
    "elle",
    "ils",
    "elles",
    "on",
    "je",
    "tu",
    "t",
    "m",
)


@dataclass(frozen=True)
class Token:
    text: str  # 原文どおりの表層
    start: int
    end: int


def tokenize(text: str) -> list[Token]:
    """原文の文字位置つきで語を切り出す。表層は一切変えない。"""
    return [Token(m.group(), m.start(), m.end()) for m in WORD_RE.finditer(text)]


def deligature(word: str) -> str:
    return word.replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")


def strip_accents(word: str) -> str:
    s = unicodedata.normalize("NFKD", word)
    return "".join(c for c in s if not unicodedata.combining(c))


def lookup_forms(surface: str) -> list[str]:
    """語彙集に当てるための形に分解する。

    `servez-vous-en` → `servez` / `vous` / `en`、`d’huile` → `de` / `huile`。
    分解しても照合できない部分は、そのまま 1 語として返す。
    """
    w = deligature(surface.lower()).replace("’", "'")
    forms: list[str] = []

    # 省略形の頭を切る
    if "'" in w:
        head, _, rest = w.partition("'")
        if head in ELISION_HEADS:
            forms.append(ELISION_HEADS[head])
            w = rest
        else:  # `aujourd'hui` のように全体で一語のもの
            return [w]
        if not w:
            return forms

    # 接語を後ろから剥がす
    parts = w.split("-")
    tail: list[str] = []
    while len(parts) > 1 and parts[-1] in CLITICS:
        tail.insert(0, parts.pop())
    stem = "-".join(parts)
    if stem:
        forms.append(stem)
    forms.extend(tail)
    return [f for f in forms if f]
