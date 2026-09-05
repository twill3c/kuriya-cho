"""本文の相互参照(F-05b)。

この本は**自分自身を絶えず参照する**。「(Voyez _Sauce à l’Italienne_.)」「article précédent」の
形で、628 レシピ中 **238 件が他の項へ送り、27 件は参照しかしていない**
(2026-09-05 実測)。
読む側から見ると、これは 200 年前のハイパーテキストである。

参照先は組版で分かる —— PG の plain-text は参照される項名を斜体(`_…_`)で組んでいる。
ただし斜体は強調にも使われるので、**直前に手がかり語**(`Voyez` / `article`)がある斜体だけを
参照として数える。手がかりを見ないと、松露を論じる長い斜体の一段落まで参照として拾ってしまう
(実測: 手がかりを見ないと 347 件になり、うち 72 件は参照ではない強調である。
その中には 300 字を超える松露の一段落が含まれる)。

## 解決率(G-13)

参照先の項名を、抽出したレシピ表題・章名に突き合わせる。**これは非循環である** ——
参照側は本文、突き合わせ先は見出しで、どちらも同じ分割器から出るが、
一致するかどうかは分割器の都合ではなく**著者が同じ名前で呼んだかどうか**で決まる。

実測 2026-09-05(参照 307 件):

| 判定 | 件数 | 割合 |
|---|---|---|
| 表題と一致 | 164 | 53.4% |
| 表題の一部と一致(略した参照) | 70 | 22.8% |
| 解決しない | 73 | 23.8% |

**解決しない 73 件のうち、行き先が第二巻だと言い切れるものがある。** 大文字組みの参照は
章を指しており、第一巻の章 32 個はすべて分かっている。そこに無い章が 5 つ出てくる ——
`FARCES`(7 件)`PATISSERIE`(3)`ENTREMETS` `POISSON` `SAUTÉ`。
**本が自分で、失われた巻の目次を教えている。**
残りは `Pâte à Pâté` `Feuilletage` `Petites Omelettes` `Bordures de Plats` のように
菓子・アントルメの項で、やはり第一巻に無い。
Project Gutenberg に第二巻は収録されていないので、**この参照は原理的にたどれない**。
画面ではそう表示する(切れたリンクを黙って消さない)。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from pipeline.pg_parse import Recipe, Section, parse_sections

# 参照の手がかり語。斜体の直前 30 字以内に出ること
CUE = re.compile(r"(voyez|voy\.|article|articles)\W*$", re.I)
ITALIC = re.compile(r"_([^_]+)_")
# 章を指す参照は**大文字組み**で、斜体ではない(`(Voyez l’article PATISSERIE)`)。
# 斜体だけを見ていると 32 件を取り落とす —— そのうち FARCES / PATISSERIE / ENTREMETS /
# POISSON は第一巻に無い章で、**第二巻を指している証拠**になる(2026-09-05 実測)
UPPER_REF = re.compile(r"[A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒÆ][A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒÆ'’ -]{3,}")

# 突き合わせのときだけ落とす機能語。表示には使わない
MATCH_STOP = {"de", "du", "des", "la", "le", "les", "a", "au", "aux", "l", "d", "en", "et", "ou"}


def match_key(title: str) -> str:
    """突き合わせ用の鍵。アクセント・合字・機能語・単複の差を落とす。

    `Langues de Bœufs` と `Langues de Bœuf` を同じ鍵にするのが目的で、
    これをしないと単複の違いだけで参照が切れる(実測で 17 件がそれだった)。
    """
    s = unicodedata.normalize("NFKD", title.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("œ", "oe").replace("æ", "ae").replace("’", "'")
    words = [w for w in re.split(r"[^a-z0-9]+", s) if w and w not in MATCH_STOP]
    words = [w[:-1] if len(w) > 3 and w[-1] in "sx" else w for w in words]
    return " ".join(words)


@dataclass(frozen=True)
class Reference:
    start: int
    end: int
    text: str  # 原文どおりの参照先の名
    target: str | None  # 解決したレシピ ID / 章 ID
    status: str  # "exact" | "partial" | "unresolved"


class Index:
    """表題 → ID の索引。参照の解決に使う。"""

    def __init__(self, sections: list[Section] | None = None) -> None:
        sections = sections if sections is not None else parse_sections()
        self.recipes: dict[str, str] = {}
        for s in sections:
            for r in s.recipes:
                self.recipes.setdefault(match_key(r.title), r.rid)
        self.sections: dict[str, str] = {match_key(s.name): s.sid for s in sections}

    def resolve(self, name: str, *, sections_only: bool = False) -> tuple[str | None, str]:
        """参照先を引く。

        `sections_only` は**大文字組みの参照**(章を指す)のためにある。章の名を
        レシピ表題へ部分一致させると静かに誤る —— `ENTREMETS` が
        `Choux brocolis à l’Entremets` のような表題に当たってしまい、
        「第一巻に無い章」だという事実が消える(2026-09-05 に実際そうなっていた)。
        """
        key = match_key(name)
        if not key:
            return None, "unresolved"
        if key in self.sections:
            return self.sections[key], "exact"
        if sections_only:
            return None, "unresolved"
        if key in self.recipes:
            return self.recipes[key], "exact"
        if len(key) >= 5:
            padded = f" {key} "
            for k, rid in self.recipes.items():
                if k.startswith(key + " ") or padded in f" {k} ":
                    return rid, "partial"
        return None, "unresolved"


def references(text: str, index: Index) -> list[Reference]:
    out: list[Reference] = []
    for pattern, group in ((ITALIC, 1), (UPPER_REF, 0)):
        for m in pattern.finditer(text):
            if not CUE.search(text[max(0, m.start() - 30) : m.start()]):
                continue
            name = m.group(group).strip().rstrip(".")
            target, status = index.resolve(name, sections_only=pattern is UPPER_REF)
            out.append(Reference(m.start(), m.end(), name, target, status))
    out.sort(key=lambda r: r.start)
    return out


def is_reference_only(recipe: Recipe, refs: list[Reference]) -> bool:
    """本文が実質「他の項を見よ」だけの項。画面ではその旨を出す。

    長さで切るのは恣意的なので、**参照を除いた残りが 1 文に満たない**ことを条件にする。
    """
    if not refs:
        return False
    rest = recipe.text
    for r in sorted(refs, key=lambda x: -x.start):
        rest = rest[: r.start] + rest[r.end :]
    rest = re.sub(r"[\s(){}\[\].,;:—–-]+", " ", rest).strip()
    return len(rest.split()) <= 12


def audit() -> dict[str, object]:
    sections = parse_sections()
    index = Index(sections)
    recipes = [r for s in sections for r in s.recipes]
    counts = {"exact": 0, "partial": 0, "unresolved": 0}
    unresolved: dict[str, int] = {}
    ref_only: list[str] = []
    with_refs = 0
    for r in recipes:
        refs = references(r.text, index)
        if refs:
            with_refs += 1
        for ref in refs:
            counts[ref.status] += 1
            if ref.status == "unresolved":
                unresolved[ref.text] = unresolved.get(ref.text, 0) + 1
        if is_reference_only(r, refs):
            ref_only.append(r.rid)
    total = sum(counts.values())
    # 解決しない参照のうち**大文字組みのもの**は章を指している。第一巻にその章が無い以上、
    # 指し先は第二巻である(第一巻の章は 32 個で、目次にも本文にも全部載っている)
    absent_sections = sorted(
        {name for name in unresolved if name.isupper() and len(name) >= 4}
    )
    return {
        "absent_sections": absent_sections,
        "recipes": len(recipes),
        "recipes_with_references": with_refs,
        "references": total,
        "counts": counts,
        "resolved_rate": (counts["exact"] + counts["partial"]) / total if total else 0.0,
        "unresolved_names": sorted(unresolved.items(), key=lambda x: (-x[1], x[0])),
        "reference_only": ref_only,
    }


if __name__ == "__main__":
    a = audit()
    c = a["counts"]  # type: ignore[index]
    t = a["references"]
    print(f"レシピ {a['recipes']} / 参照を持つ {a['recipes_with_references']} / 参照 {t} 件")
    for k in ("exact", "partial", "unresolved"):
        print(f"  {k:11s} {c[k]:4d}  {c[k] / t:6.1%}")
    print(f"解決率 {a['resolved_rate']:.1%}")
    print(f"参照しかしていない項: {len(a['reference_only'])}  {a['reference_only'][:8]}")  # type: ignore[arg-type]
    print(f"第一巻に無い章への参照(= 第二巻): {a['absent_sections']}")
    print("解決しない参照先(上位):")
    for name, n in a["unresolved_names"][:12]:  # type: ignore[index]
        print(f"   {name}  x{n}")
