"""本文の分割(F-02)。

Project Gutenberg #64976 の plain-text から、章(section)とレシピ(recipe)を取り出す。

**組版の実際**(2026-09-05 実測。全 12,152 行を走査して確かめた):

- 本文の範囲は `L’ART DU CUISINIER.` の見出しから `FIN DU TOME PREMIER.` まで
- 章見出しは大文字だけの行(32 個)。ただし 1 個だけ**読点で終わって次の斜体行へ続く**
  (`BÉCASSES, BÉCASSINES, BÉCASSEAUX,` + `_Et parti qu’on peut tirer…_`)。
  これを見落とすと章見出しの後半がレシピとして数えられる
- レシピ見出しは前後を空行で挟まれた斜体だけの行。1 行が 624 個、2 行に折り返したものが 3 個
- 斜体は本文中にも出る(`_bain-marie_` 等)ので、「行全体が斜体」かつ「前後が空行」の
  両方を要求しないと本文の途中を見出しと取り違える

件数オラクル(HC-012)は巻末の TABLE DES MATIÈRES である。目次は章ごとに項目を並べており、
本文側の抽出結果と章単位で突き合わせられる。目次の `--` は直前項目の頭語の省略、
`_ib._` は ibidem(同前頁)。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.fetch_sources import load_text

ROOT = Path(__file__).resolve().parent.parent

BODY_START = "L’ART DU CUISINIER.\n\n\nPOTAGES."
BODY_END = "FIN DU TOME PREMIER."
TOC_START = "TABLE DES MATIÈRES"
TOC_END = "FIN DE LA TABLE DU PREMIER VOLUME."
FRONT_START = "L’ART\n\n                             DU CUISINIER,"

# 大文字だけで組まれた行。アクセント付き大文字・アポストロフィ・読点・ハイフンを含む
UPPER_LINE = re.compile(r"[A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŒÆ' ’,\.\-]{4,}")
# 見出しの句点は斜体の内側にあるのが普通だが、外側に落ちている行が実在する
# (`_Boudin blanc_.` `_Boudin d’Ecrevisses_.` の 2 件)。閉じ括弧の外の句読点を許さないと、
# その 2 件が見出しとして拾われず、本文が直前のレシピに吸われる(2026-09-05 実測)
ITALIC_LINE = re.compile(r"\s*_([^_]+)_[.,;:]?\s*")
ITALIC_OPEN = re.compile(r"\s*_([^_]+)")
ITALIC_CLOSE = re.compile(r"([^_]+)_[.,;:]?\s*")


@dataclass
class Recipe:
    rid: str
    section_id: str
    title: str
    paragraphs: list[str]
    line: int  # 本文領域内の行番号(0 起点)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)


@dataclass
class Section:
    sid: str
    name: str
    line: int
    lead: list[str] = field(default_factory=list)  # 章の導入文(最初のレシピ見出しの前)
    recipes: list[Recipe] = field(default_factory=list)


def _numbered(counter: dict[str, int], base: str) -> str:
    """同名の章が二度出る(PIGEONS)ので、二度目以降に連番を足す。"""
    counter[base] = counter.get(base, 0) + 1
    return base if counter[base] == 1 else f"{base}-{counter[base]}"


def _slug(text: str) -> str:
    """見出しから ASCII の識別子を作る。同名章(PIGEONS が 2 回ある)は呼び出し側で連番を足す。"""
    s = unicodedata.normalize("NFKD", text.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("œ", "oe").replace("æ", "ae").replace("’", "").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > 40:  # 章の副題まで含む見出しがあるので、語の境界で切り詰める
        s = s[:40].rsplit("-", 1)[0]
    return s or "x"


def body_text() -> str:
    raw = load_text("pg64976")
    start = raw.index(BODY_START)
    end = raw.index(BODY_END)
    return raw[start:end]


def toc_text() -> str:
    raw = load_text("pg64976")
    start = raw.index(TOC_START)
    end = raw.index(TOC_END)
    return raw[start:end]


def _is_upper_heading(line: str) -> bool:
    s = line.strip()
    return bool(s) and len(s) >= 4 and UPPER_LINE.fullmatch(s) is not None


def _italic_block(lines: list[str], i: int) -> tuple[str, int] | None:
    """行 i から始まる斜体見出しを読む。戻り値は (見出し, 消費した行数)。

    見出しの条件は「直前が空行」「行全体が斜体」。2 行に折り返す形も受ける。
    """
    if i > 0 and lines[i - 1].strip():
        return None
    m = ITALIC_LINE.fullmatch(lines[i])
    if m:
        if i + 1 < len(lines) and lines[i + 1].strip():
            return None
        return m.group(1).strip(), 1
    m = ITALIC_OPEN.fullmatch(lines[i])
    if m and i + 1 < len(lines):
        m2 = ITALIC_CLOSE.fullmatch(lines[i + 1])
        if m2 and (i + 2 >= len(lines) or not lines[i + 2].strip()):
            return f"{m.group(1).strip()} {m2.group(1).strip()}", 2
    return None


def parse_sections(trace: set[int] | None = None) -> list[Section]:
    """本文を章とレシピに割る。

    `trace` を渡すと、**出力のどれかに入った行の番号**を書き込む。
    どこにも入らなかった行を数えるための計器で、消費率の検算に使う(HC-164)。
    """
    lines = body_text().split("\n")
    sections: list[Section] = []
    seen_sid: dict[str, int] = {}
    cur: Section | None = None
    pending: list[tuple[int, str]] = []  # 直前の段落バッファ(行番号つき)
    cur_recipe: Recipe | None = None

    def mark(*idx: int) -> None:
        if trace is not None:
            trace.update(idx)

    def flush() -> None:
        nonlocal pending
        block = "\n".join(t for _, t in pending).strip()
        used = [k for k, _ in pending]
        pending = []
        if not block:
            return
        mark(*used)
        para = re.sub(r"\s*\n\s*", " ", block).strip()
        if cur_recipe is not None:
            cur_recipe.paragraphs.append(para)
        elif cur is not None:
            cur.lead.append(para)

    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_upper_heading(line):
            name = line.strip()
            if name == "L’ART DU CUISINIER.":  # 扉の柱。章ではない
                mark(i)
                i += 1
                continue
            flush()
            cur_recipe = None
            mark(i)
            # 読点で終わる章見出しは、続く斜体行までが一つの見出しである
            if name.endswith(","):
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                blk = _italic_block(lines, j)
                if blk is not None:
                    name = f"{name} {blk[0]}"
                    mark(*range(i + 1, j + blk[1]))  # 間に挟まる空行ごと帰属させる
                    i = j + blk[1] - 1
            sid = _numbered(seen_sid, _slug(name.rstrip(".")))
            cur = Section(sid=sid, name=name.rstrip("."), line=i)
            sections.append(cur)
            i += 1
            continue

        blk = _italic_block(lines, i)
        if blk is not None and cur is not None:
            flush()
            title, consumed = blk
            rid = f"{cur.sid}-{len(cur.recipes) + 1:02d}"
            cur_recipe = Recipe(
                rid=rid,
                section_id=cur.sid,
                title=title.rstrip("."),
                paragraphs=[],
                line=i,
            )
            cur.recipes.append(cur_recipe)
            mark(*range(i, i + consumed))
            i += consumed
            continue

        if not line.strip():
            flush()
            mark(i)
        else:
            pending.append((i, line))
        i += 1

    flush()
    return sections


# --- 件数オラクル: 巻末の目次 -------------------------------------------------

TOC_SKIP_HEADS = {
    "SERVICES DE TABLE",
    "PRINTEMPS",
    "PREMIER SERVICE",
    "SECOND SERVICE",
    "SECOND SERVICE.--MILIEU",
    "HIVER",
}

# 頁参照。`_ib._`(同前頁)・`_id._`・`69, 70`(二頁にまたがる項目)の三形がある。
# 区切りの空白が 1 個しかない行が実在する(`Brède-Sauce. 70` 等 5 件)ので `\s+` で受ける。
_PAGE_REF = re.compile(r"\s+(?:_ib\._|_id\._|\d{1,3}(?:,\s*\d{1,3})*)\s*$")


def _strip_page_ref(raw: str) -> tuple[str, bool]:
    """行末の頁参照を落とす。戻り値は (本体, 頁参照があったか)。"""
    m = _PAGE_REF.search(raw.rstrip())
    if m is None:
        return raw.strip(), False
    return raw[: m.start()].strip(), True


def parse_toc(section_names: set[str] | None = None) -> dict[str, list[str]]:
    """目次を章 → 項目名の並びに読む。

    **目次の組みは本文の組みと違う**(2026-09-05 実測):

    - 章見出しにも頁番号が付く(`FRITURE.  77`)。頁参照を落としてから大文字判定しないと、
      章見出しが項目として数えられ、後続の章がすべて手前の章に流れ込む
    - 章見出しが斜体で組まれることがある(`_Dinde._` `_Oies._` `_Canards._`
      `_Oiseaux de Rivières et Sarcelles._` の 4 個)
    - 項目は頁参照で切れる。折り返した項目は次行に続く
    - `--` は直前の完全項目の頭語の省略、`_ib._` は ibidem

    **斜体行の曖昧さ**: 目次の斜体行 7 個のうち 5 個は章見出し
    (`_Friture._` `_Dinde._` `_Pigeons._` `_Oies._` `_Canards._`
    `_Oiseaux de Rivières et Sarcelles._`)だが、`_Des Truffes en général._` は
    本文ではレシピである。**組み方だけでは区別できない**(どちらも斜体で、
    章見出しのはずの `_Friture._,` も読点で終わる)。そこで本文側の章名を渡して
    照合する。これは**項目の総数と表題を動かさない** —— 動くのは章への帰属だけなので、
    件数オラクルとしての独立性は保たれる(G-01)。
    """
    if section_names is None:
        section_names = {_slug(s.name) for s in parse_sections()}
    lines = toc_text().split("\n")
    out: dict[str, list[str]] = {}
    seen: dict[str, int] = {}
    cur_key: str | None = None
    buf: list[str] = []
    last_full: str = ""

    def _toc_key(head: str) -> str:
        key = _numbered(seen, _slug(head))
        out.setdefault(key, [])
        return key

    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = raw.strip()
        if not s:
            continue
        if s == TOC_START or s.startswith("CONTENUES DANS") or s == "Pages":
            continue

        head_text, _had_page = _strip_page_ref(raw)

        # 章見出し(大文字組み)。句点で終わらない見出しは次行へ折り返している
        # (`BÉCASSES, …,` は斜体の副題へ、`ROUGES-GORGES, … ET` は次行の
        #  `BEC-FIGUES.` へ続く)。頁参照が出た行で止める
        if _is_upper_heading(head_text) and not buf:
            head = head_text
            while not head.rstrip().endswith(".") and i < len(lines):
                nxt, had = _strip_page_ref(lines[i])
                i += 1
                head = f"{head} {nxt}".strip()
                if had:
                    break
            head = re.sub(r"\s+", " ", head).strip().strip(".,").replace("_", "").strip(" ,")
            if head_text.rstrip(".") in TOC_SKIP_HEADS:
                cur_key = None
            else:
                cur_key = _toc_key(head)
            continue

        # 章見出し(斜体組み)。本文側で章になっているものだけを見出しとして扱う
        if ITALIC_LINE.fullmatch(head_text) and not buf:
            name = head_text.strip(" ,.").strip("_").rstrip(".")
            if _slug(name) in section_names:
                cur_key = _toc_key(name)
                continue

        if cur_key is None:
            continue
        buf.append(head_text if _had_page else s)
        if not _had_page:
            continue
        entry = re.sub(r"\s+", " ", " ".join(buf)).strip()
        buf = []
        if entry.startswith("--"):
            rest = entry[2:].strip()
            head_word = last_full.split(" ", 1)[0] if last_full else ""
            entry = f"{head_word} {rest}".strip()
        else:
            last_full = entry
        out[cur_key].append(entry.rstrip("."))
    return out


def toc_counts() -> dict[str, int]:
    return {k: len(v) for k, v in parse_toc().items()}


# 目次と本文の食い違いのうち、実物を読んで説明のついたもの(2026-09-05 実測)。
# ここに挙げた以外の食い違いが出たら、抽出器か素材が動いたということなので落とす(G-01)。
EXPLAINED_GAPS: tuple[tuple[str, str], ...] = (
    (
        "friture",
        "本文 14 / 目次 12。目次は『Sauce aux Hatelets』の一行に頁 69, 70 を併記して"
        "本文の 2 件(Sauces aux Hatelets / Autre Sauce aux Hatelets)をまとめており、"
        "章の途中の小見出し『Manière d’opérer en cela』を項目に立てていない",
    ),
    (
        "garnitures",
        "本文 12 / 目次 19。目次には POIVRE DE CAYENNE の章見出しが無く、"
        "その 7 件が GARNITURES の項目として続けて並んでいる(12 + 7 = 19)",
    ),
    (
        "poivre-de-cayenne",
        "目次に章見出しが無い(項目は GARNITURES に合流している)。件数の差ではなく帰属の差",
    ),
)


def reconcile() -> dict[str, object]:
    """目次(件数オラクル)と本文抽出の突合(G-01)。"""
    sections = parse_sections()
    toc = toc_counts()
    explained = {sid for sid, _ in EXPLAINED_GAPS}
    rows = []
    unexplained = []
    for s in sections:
        n = len(s.recipes)
        m = toc.get(s.sid)
        ok = m == n
        rows.append({"sid": s.sid, "name": s.name, "body": n, "toc": m, "match": ok})
        if not ok and s.sid not in explained:
            unexplained.append({"sid": s.sid, "body": n, "toc": m})
    return {
        "body_sections": len(sections),
        "body_recipes": sum(len(s.recipes) for s in sections),
        "toc_sections": len(toc),
        "toc_entries": sum(toc.values()),
        "matched_sections": sum(1 for r in rows if r["match"]),
        "rows": rows,
        "unexplained": unexplained,
    }


def report() -> str:
    sections = parse_sections()
    toc = toc_counts()
    lines = [
        f"本文: 章 {len(sections)} / レシピ {sum(len(s.recipes) for s in sections)}",
        f"目次: 章 {len(toc)} / 項目 {sum(toc.values())}",
        "",
        f"{'章':32s} {'本文':>5s} {'目次':>5s}  差",
    ]
    for s in sections:
        n = len(s.recipes)
        m = toc.get(s.sid)
        mark = "" if m == n else "  <<<"
        lines.append(f"{s.name[:32]:32s} {n:5d} {('-' if m is None else m):>5} {mark}")
    only_toc = sorted(set(toc) - {s.sid for s in sections})
    if only_toc:
        lines.append(f"目次にのみ: {only_toc}")
    rec = reconcile()
    lines += [
        "",
        f"一致した章: {rec['matched_sections']} / {rec['body_sections']}",
        f"説明のつかない食い違い: {rec['unexplained'] or 'なし'}",
    ]
    for sid, why in EXPLAINED_GAPS:
        lines.append(f"  [{sid}] {why}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
