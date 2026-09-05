"""架空の一皿を作る(F-09)。

画面のつまみは「まじめ ⇄ 気まぐれ」と書く。中身は本書の**料理名の並び方**を数えた
二重連鎖(bigram)で、学習された何かではない。

## 決定論をどう担保するか(G-10)

生成はブラウザで走る(つまみを動かすたびに作り直すので、ビルド時に焼けない)。
つまり**同じ模型を Python と JavaScript の二つで実装する**ことになる。
二実装が食い違えば、テストで見ている出力と利用者が見る出力が別物になる。

そこで**浮動小数点を一切使わない**設計にした:

- 乱数は mulberry32(32 ビット整数の演算だけ)。`>>> 0` と `& 0xFFFFFFFF` で桁を揃える
- 重みは**整数の冪**。`count ** 3` / `** 2` / `** 1` / 一様 の 4 段で「まじめ ⇄ 気まぐれ」を作る。
  連続的な温度(`count ** (1/T)`)にすると `pow` の最下位桁が処理系で食い違いうるので採らない
- 候補は (出現数の降順, 表記の昇順) で必ず同じ順に並べる

この設計のおかげで、二実装照合は「だいたい同じ」ではなく**完全一致**を要求できる(T-152)。

## 循環していないか

生成物が本書に実在しないこと(G-10)は、生成器とは別に持っている表題の集合で判定する。
生成器はその集合を参照しない —— 参照させると「実在しないものだけを作る生成器」になり、
新奇性の測定が恒等式になる。**測ってから弾く**、の順にする。
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from pipeline.pg_parse import parse_sections

BEGIN = ""
END = ""

# 章をいくつかの「種類」にまとめる。1 品しか無い章(DAIM)では連鎖が作れない
KINDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "potage": ("ポタージュ", ("potages", "maigre")),
    "sauce": ("ソース", ("sauces", "friture", "garnitures", "poivre-de-cayenne")),
    "ragout": ("ラグー", ("ragouts",)),
    "viande": ("肉", ("boeuf", "veau", "mouton", "agneau", "cochon")),
    "gibier": (
        "猟の獣と鳥",
        (
            "sanglier", "chevreuil", "daim", "lievre", "lapereau", "faisan",
            "perdrix-rouges", "becasses-becassines-becasseaux-et-parti", "pluvier",
            "grives", "cailles", "mauviettes-ou-alouettes", "pigeons",
            # 本文が地の文だけでレシピを持たない章(実測 2026-09-05: 0 件)。
            # 連鎖には何も足さないが、割り当てから漏らさない —— 漏れは
            # 「作れない料理名がある」という形でしか現れず、気づきにくい
            "rouges-gorges-ortolans-muriers-et-bec",
        ),
    ),
    "volaille": (
        "家禽",
        ("volaille", "dinde", "pigeons-2", "oies", "canards",
         "oiseaux-de-rivieres-et-sarcelles"),
    ),
}

# つまみの段。値は出現数にかける冪。0 は一様(= 気まぐれ)
STEPS = (3, 2, 1, 0)
STEP_LABELS = ("まじめ", "ややまじめ", "やや気まぐれ", "気まぐれ")

_TOKEN = re.compile(r"[^\s]+")


def tokenize_title(title: str) -> list[str]:
    return _TOKEN.findall(title)


def _key(title: str) -> str:
    s = unicodedata.normalize("NFKD", title.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("œ", "oe").replace("æ", "ae").replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


@dataclass
class Model:
    kinds: dict[str, dict[str, list[tuple[str, int]]]]
    real_titles: frozenset[str]

    def to_json(self) -> dict[str, object]:
        return {
            "kinds": {
                k: {
                    "label": KINDS[k][0],
                    "chain": {
                        state: [[tok, n] for tok, n in cands]
                        for state, cands in chain.items()
                    },
                }
                for k, chain in self.kinds.items()
            },
            "steps": list(STEPS),
            "step_labels": list(STEP_LABELS),
            "real_titles": sorted(self.real_titles),
        }


def build() -> Model:
    sections = {s.sid: s for s in parse_sections()}
    kinds: dict[str, dict[str, list[tuple[str, int]]]] = {}
    real: set[str] = set()
    for kind, (_label, sids) in KINDS.items():
        counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for sid in sids:
            for r in sections[sid].recipes:
                toks = tokenize_title(r.title)
                real.add(_key(r.title))
                if not toks:
                    continue
                prev = BEGIN
                for t in toks:
                    counts[prev][t] += 1
                    prev = t
                counts[prev][END] += 1
        kinds[kind] = {
            state: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))
            for state, c in sorted(counts.items())
        }
    # 全章の表題を実在集合に入れる(生成器が使うのは連鎖だけで、この集合は使わない)
    for s in sections.values():
        for r in s.recipes:
            real.add(_key(r.title))
    return Model(kinds=kinds, real_titles=frozenset(real))


# --- 乱数と抽選(JavaScript 側と同一の実装)-----------------------------------

MASK = 0xFFFFFFFF


def mulberry32(seed: int):
    state = seed & MASK

    def nxt() -> int:
        """0 以上 2^32 未満の整数を返す。浮動小数点を経由しない。"""
        nonlocal state
        state = (state + 0x6D2B79F5) & MASK
        z = state
        z = (z ^ (z >> 15)) * (z | 1) & MASK
        z = (z + ((z ^ (z >> 7)) * (z | 61) & MASK)) & MASK
        return (z ^ (z >> 14)) & MASK

    return nxt


def _pick(cands: list[tuple[str, int]], power: int, draw: int) -> str:
    weights = [1 if power == 0 else n**power for _tok, n in cands]
    total = sum(weights)
    x = draw % total
    for (tok, _n), w in zip(cands, weights):
        if x < w:
            return tok
        x -= w
    return cands[-1][0]


MAX_TOKENS = 12


def generate(model: Model, kind: str, step: int, seed: int) -> str:
    """一つの料理名を作る。同じ (kind, step, seed) なら必ず同じ文字列。"""
    chain = model.kinds[kind]
    power = STEPS[step]
    rnd = mulberry32(seed)
    out: list[str] = []
    state = BEGIN
    for _ in range(MAX_TOKENS):
        cands = chain.get(state)
        if not cands:
            break
        tok = _pick(cands, power, rnd())
        if tok == END:
            break
        out.append(tok)
        state = tok
    return " ".join(out)


def novelty(model: Model, kind: str, step: int, count: int = 200) -> dict[str, object]:
    """G-10。作った名が本書に実在しない割合を測る(弾く前に測る)。"""
    made = [generate(model, kind, step, seed) for seed in range(count)]
    real = [t for t in made if _key(t) in model.real_titles]
    empty = [t for t in made if not t.strip()]
    return {
        "kind": kind,
        "step": step,
        "generated": len(made),
        "novel": len(made) - len(real) - len(empty),
        "already_in_the_book": len(real),
        "empty": len(empty),
        "samples": made[:6],
    }


def report() -> str:
    model = build()
    lines = [f"種類 {len(model.kinds)} / 実在する表題 {len(model.real_titles)}"]
    for kind in model.kinds:
        states = len(model.kinds[kind])
        lines.append(f"\n■ {KINDS[kind][0]}({kind}) 状態 {states}")
        for step, label in enumerate(STEP_LABELS):
            n = novelty(model, kind, step)
            lines.append(
                f"   {label:6s} 新奇 {n['novel']:3d}/{n['generated']}"
                f"  既出 {n['already_in_the_book']:2d}  空 {n['empty']:2d}"
            )
            lines.append(f"      例: {n['samples'][0]} / {n['samples'][1]}")
    return "\n".join(lines)


def write_json(path) -> None:
    path.write_text(
        json.dumps(build().to_json(), ensure_ascii=False), encoding="utf-8"
    )


if __name__ == "__main__":
    print(report())
