"""材料から引く(F-08)。

画面では「材料から探す」としか言わない。中でやっているのは**転置索引**で、
学習された類似度ではない。だから類似度の数値は出さない(SPEC §5)。

## 何を索引にするか

材料のチップは `extract.py` の材料表から作る。ただし**表に載っているだけの語は出さない** ——
本文に一度も出ない材料をチップにすると、押しても 0 件になる。
チップは「本書に実際に出てくる材料」に限り、出現件数の多い順に並べる。

## 循環していないか(G-09)

索引の正しさを索引で測ってはならない。この索引の検算は、**索引をいっさい使わない経路**で行う ——
返ってきたレシピの**原文**を素の正規表現で走査し、その材料の表層が本当に在ることを確かめる。
索引の作り方(語幹化・合字の開き)を検算側で再現しないので、どちらかが壊れれば食い違う。

## 順位の付け方

- 一致した材料の**種類数**が第一の基準。二つ指定したら両方入っている項が上に来る
- 同数なら、料理名に材料が出る項を上に(表題に出るものはその料理の主題である)
- それでも同じなら、本文の短い順(短い項は要点だけを書いているので読みやすい)

数値は画面に出さない。出すのは「なぜ出たか」の一行だけである。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from pipeline.extract import ING_SET, _norm
from pipeline.pg_parse import Recipe, parse_sections
from pipeline.tokenize_fr import WORD_RE

# チップに出す材料の下限。これ未満しか出ない語は、押しても手応えが無いので出さない
MIN_DOC_FREQ = 3


@dataclass
class Entry:
    rid: str
    title_terms: frozenset[str]
    body_terms: frozenset[str]
    length: int


def _terms(text: str) -> set[str]:
    out: set[str] = set()
    for m in WORD_RE.finditer(text):
        head = m.group().split("-")[0].split("’")[-1].split("'")[-1]
        w = _norm(head)
        if w in ING_SET:
            out.add(w)
    return out


def build(recipes: list[Recipe] | None = None) -> dict[str, object]:
    if recipes is None:
        recipes = [r for s in parse_sections() for r in s.recipes]
    entries: list[Entry] = []
    postings: dict[str, list[str]] = defaultdict(list)
    freq: Counter[str] = Counter()
    for r in recipes:
        title_terms = _terms(r.title)
        body_terms = _terms(r.text) | title_terms
        entries.append(
            Entry(rid=r.rid, title_terms=frozenset(title_terms),
                  body_terms=frozenset(body_terms), length=len(r.text))
        )
        for t in body_terms:
            postings[t].append(r.rid)
            freq[t] += 1
    chips = [t for t, n in freq.most_common() if n >= MIN_DOC_FREQ]
    return {
        "entries": {e.rid: e for e in entries},
        "postings": {k: sorted(v) for k, v in postings.items()},
        "freq": dict(freq),
        "chips": chips,
    }


def search(index: dict[str, object], terms: list[str], limit: int = 40) -> list[dict[str, object]]:
    """材料の集合で引く。戻り値には「なぜ出たか」を書ける材料名を含める。"""
    wanted = [_norm(t) for t in terms if _norm(t)]
    entries: dict[str, Entry] = index["entries"]  # type: ignore[assignment]
    hits: list[dict[str, object]] = []
    for rid, e in entries.items():
        matched = [w for w in wanted if w in e.body_terms]
        if not matched:
            continue
        in_title = [w for w in matched if w in e.title_terms]
        hits.append(
            {"rid": rid, "matched": matched, "in_title": in_title, "length": e.length}
        )
    hits.sort(key=lambda h: (-len(h["matched"]), -len(h["in_title"]), h["length"], h["rid"]))  # type: ignore[arg-type]
    return hits[:limit]


# --- G-09 の検算(索引を使わない経路)----------------------------------------

_SURFACE_CACHE: dict[str, re.Pattern[str]] = {}


def surface_pattern(term: str) -> re.Pattern[str]:
    """材料の表層をそのまま探す素の正規表現。

    索引側の語幹化・合字の開きを**再現しない**。合字は原文の綴りをそのまま書き、
    語尾は s / x の有無だけを許す。索引と同じ道具を使ってしまうと、
    照合は恒等式になって何も検査しない(HC-045)。
    """
    if term not in _SURFACE_CACHE:
        base = term.replace("oe", "(?:oe|œ)").replace("ae", "(?:ae|æ)")
        # `\b` は使えない。PG の斜体記号 `_` は正規表現では語の文字なので、
        # `_Bœuf ou…_` の先頭に語境界が立たず、**在る語を無いと言う**
        # (2026-09-05 実測で 5 件がこれで落ちていた)
        letters = "A-Za-zÀ-ÖØ-öø-ÿŒœÆæ"
        _SURFACE_CACHE[term] = re.compile(
            rf"(?<![{letters}]){base}[sx]?(?![{letters}])", re.IGNORECASE
        )
    return _SURFACE_CACHE[term]


def verify(index: dict[str, object], recipes: list[Recipe] | None = None) -> list[dict[str, str]]:
    """索引に載せた材料が、その項の原文に**素の走査で**見つかることを確かめる。

    見つからないものを返す(空なら合格)。アクセント違いは許さない ——
    許してしまうと検算が緩くなり、索引の誤りを見逃す。
    """
    if recipes is None:
        recipes = [r for s in parse_sections() for r in s.recipes]
    by_rid = {r.rid: r for r in recipes}
    bad: list[dict[str, str]] = []
    for term, rids in index["postings"].items():  # type: ignore[union-attr]
        pat = surface_pattern(term)
        for rid in rids:
            r = by_rid[rid]
            if not pat.search(f"{r.title}\n{r.text}"):
                bad.append({"term": term, "rid": rid})
    return bad


def report() -> str:
    idx = build()
    chips = idx["chips"]
    freq: dict[str, int] = idx["freq"]  # type: ignore[assignment]
    bad = verify(idx)
    lines = [
        f"索引した材料: {len(freq)} 種  チップに出す({MIN_DOC_FREQ} 件以上): {len(chips)} 種",
        f"転置の総項目: {sum(len(v) for v in idx['postings'].values()):,}",  # type: ignore[union-attr]
        f"素の走査での検算(G-09): {'合格' if not bad else bad[:5]}",
        "",
        "上位のチップ:",
    ]
    for t in chips[:24]:  # type: ignore[index]
        lines.append(f"  {t:16s} {freq[t]:4d} 件")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
