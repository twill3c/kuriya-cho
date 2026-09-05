"""綴りの遠さを測る(G-04 / G-05)。

**この計測は出荷物には入らない。** 現代フランス語の語彙集は 4.5 MB あり、
配るためのものではなく、規則と例外辞書が効いているかを**外から**判定するための道具である。

三つのことを測る:

- **G-04(効き)**: 1814 年の本文について、正規化の前と後で「現代語彙集に載る率」がどう動くか。
  正規化は語彙集を引かないので(`normalize.py` の規則と閉じた表だけ)、この比較は循環しない
- **G-05(巻き添え)**: 例外辞書の置換先がすべて現代語彙集に実在すること。
  および規則を**現代フランス語の語彙集 344,060 形すべてに当てて**、壊れる語を数えること
- **対照**: 同じジャンルで綴りが現代の本(PG #6966、1896 年)を同じ道具で測った基準線。
  これが無いと「0.85% は遠いのか近いのか」が言えない
"""

from __future__ import annotations

import collections
import json
import re
from dataclasses import dataclass

from pipeline import normalize
from pipeline.fetch_sources import load_modern_lexicon, load_text
from pipeline.pg_parse import parse_sections
from pipeline.tokenize_fr import lookup_forms, tokenize

DISCOURS_START = "DISCOURS PRÉLIMINAIRE."
DISCOURS_END = "SERVICES DE TABLE."


@dataclass
class Rate:
    forms: int
    misses: int
    types: int

    @property
    def rate(self) -> float:
        return self.misses / self.forms if self.forms else 0.0


def book_prose() -> str:
    """本書のうち**地の文**(緒言 + 章の導入 + レシピ本文)。献立と目次は除く。

    献立は皿名の羅列で文になっていないので、綴りの測定から外す。
    """
    raw = load_text("pg64976")
    discours = raw[raw.index(DISCOURS_START) : raw.index(DISCOURS_END)]
    sections = parse_sections()
    parts = [discours]
    parts += [p for s in sections for p in s.lead]
    parts += [r.text for s in sections for r in s.recipes]
    return "\n".join(parts)


def control_prose() -> str:
    """対照コーパス(PG #6966・1896 年)。PG の前口上と巻末は落とす。"""
    raw = load_text("pg6966")
    start = raw.index("*** START")
    start = raw.index("\n", start)
    end = raw.index("*** END")
    return raw[start:end]


def measure(text: str, lexicon: frozenset[str]) -> Rate:
    forms = [f for t in tokenize(text) for f in lookup_forms(t.text)]
    # 1 字の断片(組版の約物・イニシャル)は綴りの問題ではないので数えない
    forms = [f for f in forms if len(f) > 1]
    misses = [f for f in forms if f not in lexicon]
    return Rate(forms=len(forms), misses=len(misses), types=len(set(misses)))


def miss_counter(text: str, lexicon: frozenset[str]) -> collections.Counter[str]:
    forms = [f for t in tokenize(text) for f in lookup_forms(t.text) if len(f) > 1]
    return collections.Counter(f for f in forms if f not in lexicon)


# --- G-05: 巻き添えの測定 -----------------------------------------------------

_ANS = re.compile(r"^(.{3,})(a|e)ns$")


def rule_collateral(lexicon: frozenset[str]) -> dict[str, object]:
    """規則を**現代フランス語の語彙集そのもの**に当てて、壊れる語を数える。"""
    out: dict[str, object] = {}
    for name, pattern, repl, _note in normalize.RULES:
        hit = [w for w in lexicon if pattern.search(w)]
        broken = [w for w in hit if pattern.sub(repl, w) not in lexicon]
        out[name] = {"applies_to": len(hit), "breaks": len(broken), "examples": sorted(broken)[:5]}

    # 教科書的な `-ans` → `-ants` を**規則として書いたら**どうなるかの実測(採用していない)
    hit = [w for w in lexicon if _ANS.match(w)]
    broken = [w for w in hit if _ANS.sub(r"\1\2nts", w) not in lexicon]
    out["ans-to-ants (不採用)"] = {
        "applies_to": len(hit),
        "breaks": len(broken),
        "examples": sorted(broken)[:5],
    }
    return out


def lexicon_targets_are_real(lexicon: frozenset[str]) -> list[str]:
    """例外辞書の置換先が現代語彙に実在するか。実在しない語を返す。

    置換先が複数語になるもの(`tout à fait`)は語ごとに見る。
    """
    bad: list[str] = []
    for old, new in normalize.ARCHAIC.items():
        for token in tokenize(new):
            for w in lookup_forms(token.text):
                if len(w) > 1 and w not in lexicon:
                    bad.append(f"{old} → {new}(`{w}` が語彙集に無い)")
    return bad


def audit() -> dict[str, object]:
    lex = load_modern_lexicon()
    book = book_prose()
    before = measure(book, lex)
    after = measure(normalize.modernize(book), lex)
    control = measure(control_prose(), lex)
    changes = normalize.find_changes(book)
    kinds = collections.Counter(c.kind for c in changes)
    return {
        "lexicon_forms": len(lex),
        "book": {"forms": before.forms, "misses": before.misses, "rate": before.rate,
                 "types": before.types},
        "book_normalized": {"forms": after.forms, "misses": after.misses, "rate": after.rate,
                            "types": after.types},
        "control_1896": {"forms": control.forms, "misses": control.misses, "rate": control.rate,
                         "types": control.types},
        "changes": len(changes),
        "changes_by_kind": dict(kinds),
        "collateral": rule_collateral(lex),
        "unreal_targets": lexicon_targets_are_real(lex),
    }


def report() -> str:
    a = audit()
    b, n, c = a["book"], a["book_normalized"], a["control_1896"]  # type: ignore[index]
    lines = [
        f"現代フランス語の語彙集: {a['lexicon_forms']:,} 形",
        "",
        f"1814 年の本(地の文)   照合形 {b['forms']:>7,}  載らない {b['misses']:>5,}"
        f"  {b['rate']:.4%}  異なり {b['types']}",
        f"  → 正規化した後       照合形 {n['forms']:>7,}  載らない {n['misses']:>5,}"
        f"  {n['rate']:.4%}  異なり {n['types']}",
        f"対照 1896 年の料理書   照合形 {c['forms']:>7,}  載らない {c['misses']:>5,}"
        f"  {c['rate']:.4%}  異なり {c['types']}",
        "",
        f"置き換えた箇所: {a['changes']:,}  内訳 {a['changes_by_kind']}",
        "",
        "規則の巻き添え(現代語彙集そのものに当てて壊れる語):",
    ]
    for name, r in a["collateral"].items():  # type: ignore[union-attr]
        lines.append(f"  {name:24s} 対象 {r['applies_to']:>6,} / 壊す {r['breaks']:>6,}  {r['examples']}")
    lines.append("")
    lines.append(f"例外辞書の置換先で語彙集に無いもの: {a['unreal_targets'] or 'なし'}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
    print()
    print(json.dumps({"note": "この計測は出荷物に入らない"}, ensure_ascii=False))
