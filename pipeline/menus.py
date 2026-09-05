"""献立(services de table)の分割(F-03)。

巻頭の SERVICES DE TABLE は、季節(PRINTEMPS / HIVER)と饗応の順(PREMIER / SECOND SERVICE)の
下に献立が 13 個並び、各献立は「一皿の組(service)」に分かれる。

    _Seize Entrées._

      1 d’une poularde à la             1 d’une fricassée de poulets
        ravigote.[3]                      aux petits pois.[3]

**この節は自分で件数オラクルを持っている**(G-02)。組の見出しの数詞
(`Seize Entrées` = 16)は、その組に並ぶ皿の**数の合計**と一致しなければならない。
皿の頭の数字は品数で、`2 d’herbes.` は 2 皿を意味する。数詞と合計が合わなければ、
段組みの復元か数詞の読み取りのどちらかが壊れている。**この照合は本文を一切使わない**ので、
抽出器の正しさを抽出器で確かめる循環にならない。

段組みは 2 列(まれに 3 列)で、列の開始位置は献立ごとに違う。列の境界は
「皿の行頭の桁位置」の集合から決める。角括弧の数字(`[3]`)は巻末の卓図で
その皿が置かれる位置を指す(PG 転記者の注記による)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipeline.fetch_sources import load_text

MENU_START = "SERVICES DE TABLE."
MENU_END = "L’ART DU CUISINIER.\n\n\nPOTAGES."

SEASONS = {"PRINTEMPS.", "HIVER."}
# 饗応の順。`MILIEU.` は SECOND SERVICE の下位区分で、単独の行として出る。
# **これらは献立を切らない** —— 同じ献立の第二の饗応が、新しい `MENU DE` を立てずに続く
# ことがある(menu-05 の後の 20 行がそれで、最初に書いた実装はここを丸ごと落としていた。
# 件数オラクルは何も言わず、消費率(HC-164)だけが残差として見せた)
SERVICES = {"PREMIER SERVICE.", "SECOND SERVICE.", "SECOND SERVICE.--MILIEU.", "MILIEU."}

_MENU_HEAD = re.compile(r"^MENU DE .+", re.I)
_COURSE_HEAD = re.compile(r"^\s*_([^_]+)_\.?\s*$")
_DISH_START = re.compile(r"^(\d+)\s+(.+)$")
_PLATE_REF = re.compile(r"\[(\d+)\]")

# 組の見出しに出る数詞(2026-09-05 実測。13 献立・75 組に現れた語を全部数えた)
NUMERALS: dict[str, int] = {
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "treize": 13,
    "quatorze": 14,
    "quinze": 15,
    "seize": 16,
    "dix-sept": 17,
    "dix-huit": 18,
    "dix-neuf": 19,
    "vingt": 20,
    "vingt-quatre": 24,
    "trente-deux": 32,
}


@dataclass
class Dish:
    count: int
    text: str
    plate: int | None  # 巻末の卓図での位置番号


@dataclass
class Course:
    title: str
    declared: frozenset[int]  # 見出しの数詞が許す皿数。読めなければ空集合
    service: str = ""  # 同じ献立の中で饗応が変わることがある(SECOND SERVICE--MILIEU)
    dishes: list[Dish] = field(default_factory=list)

    @property
    def actual(self) -> int:
        return sum(d.count for d in self.dishes)


@dataclass
class Menu:
    mid: str
    title: str
    season: str
    service: str
    courses: list[Course] = field(default_factory=list)


def menus_text() -> str:
    raw = load_text("pg64976")
    return raw[raw.index(MENU_START) : raw.index(MENU_END)]


_WORD = re.compile(r"[A-Za-zÀ-ÿ’'\-]+")


def _segment_counts(segment: str) -> frozenset[int]:
    """一つの組見出しから、許される皿数の集合を読む。

    フランス語の数え方をそのまま規則にする(データに合わせて足した規則ではない):

    - 読点より後ろは但し書き。`Six Plats de Rôt, dont deux gros` は 6 であって 8 ではない
    - `ou` は選択。`Huit ou dix Entrées` は 8 でも 10 でもよい
    - `à` は範囲。`Treize à quinze Assiettes de dessert` は 13〜15 のどれでもよい
    - `et` は加算。`Deux gros et deux moyens Entremets` は 4
    """
    head = segment.split(",")[0]
    tokens = [w.lower() for w in _WORD.findall(head)]
    nums = [(k, NUMERALS[w]) for k, w in enumerate(tokens) if w in NUMERALS]
    if not nums:
        return frozenset()
    if len(nums) == 1:
        return frozenset({nums[0][1]})
    span = range(nums[0][0], nums[-1][0])
    joiners = {tokens[k] for k in span if tokens[k] in {"ou", "et", "à", "a"}}
    if joiners & {"à", "a"}:
        lo, hi = min(v for _, v in nums), max(v for _, v in nums)
        return frozenset(range(lo, hi + 1))
    if "ou" in joiners:
        return frozenset(v for _, v in nums)
    return frozenset({sum(v for _, v in nums)})


def _declared_count(title: str) -> frozenset[int]:
    """組見出しが宣言する皿数。読めなければ空集合。

    一行に組見出しが二つ並ぶことがある(`Huit Hors-d’œuvres d’entrées.  Huit Entrées.`)。
    その場合は両方の合計を宣言値とする。
    """
    segments = [s for s in title.split(".") if s.strip()]
    values = [_segment_counts(s) for s in segments]
    values = [v for v in values if v]
    if not values:
        return frozenset()
    totals = {0}
    for v in values:
        totals = {t + x for t in totals for x in v}
    return frozenset(totals)


# 行の途中に現れる皿の頭。2 個以上の空白のあとに「数字+空白+文字」が来る位置を列頭とみなす
_DISH_HEAD_IN_LINE = re.compile(r"(?:^|\s{2,})(\d+)\s+\S")


def _column_starts(block: list[str]) -> list[int]:
    """皿の頭が現れた桁位置を集めて列の境界にする。

    段組みは行を跨いで揃っているので、**行全体ではなく行内の位置**を見なければならない。
    左端だけを見ると右の列が丸ごと落ちる(2026-09-05 に一度そう書いて、
    宣言数の半分しか取れなかった)。
    """
    starts: set[int] = set()
    for ln in block:
        for m in _DISH_HEAD_IN_LINE.finditer(ln):
            starts.add(m.start(1))
    if not starts:
        return [0]
    starts_sorted = sorted(starts)
    # 同じ列でも数桁ぶれることがあるので、近い開始位置はまとめる
    cols = [starts_sorted[0]]
    for s in starts_sorted[1:]:
        if s - cols[-1] > 8:
            cols.append(s)
    return cols


def _parse_course_block(block: list[str]) -> list[Dish]:
    cols = _column_starts(block)
    bounds = cols + [10**6]
    buckets: list[list[str]] = [[] for _ in cols]
    for line in block:
        if line.lstrip().startswith("["):  # PG 転記者の注記
            continue
        for k in range(len(cols)):
            seg = line[bounds[k] : bounds[k + 1]].strip()
            if seg:
                buckets[k].append(seg)
    dishes: list[Dish] = []
    for bucket in buckets:
        cur: list[str] | None = None
        cur_count = 0
        for seg in bucket:
            m = _DISH_START.match(seg)
            if m:
                if cur is not None:
                    dishes.append(_finish(cur_count, cur))
                cur_count = int(m.group(1))
                cur = [m.group(2)]
            elif cur is not None:
                cur.append(seg)
        if cur is not None:
            dishes.append(_finish(cur_count, cur))
    return dishes


def _finish(count: int, parts: list[str]) -> Dish:
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()
    m = _PLATE_REF.search(text)
    plate = int(m.group(1)) if m else None
    text = _PLATE_REF.sub("", text).strip().rstrip(".")
    return Dish(count=count, text=text, plate=plate)


def parse_menus(trace: set[int] | None = None) -> list[Menu]:
    """献立を読む。`trace` を渡すと、出力のどれかに入った行の番号を書き込む(HC-164)。"""
    lines = menus_text().split("\n")
    menus: list[Menu] = []
    season = ""
    service = ""
    cur: Menu | None = None
    course: Course | None = None
    block: list[str] = []

    def flush_course() -> None:
        nonlocal block
        if course is not None and block:
            course.dishes.extend(_parse_course_block(block))
        block = []

    def mark(idx: int) -> None:
        if trace is not None:
            trace.add(idx)

    for idx, line in enumerate(lines):
        s = line.strip()
        if not s or s == MENU_START:
            mark(idx)
            # 空行は組の切れ目でもある。見出しを立てずに次の組が始まることがあるので
            # (menu-05 の Deux Salades の直後がそれ)、ここで束ねを閉じる
            if not s and block:
                flush_course()
                course = None
            continue
        if s in SEASONS:
            mark(idx)
            flush_course()
            season, service, cur, course = s.rstrip("."), service, None, None
            continue
        if s in SERVICES:
            mark(idx)
            flush_course()
            service = s.rstrip(".") if s != "MILIEU." else f"{service}--MILIEU"
            course = None
            continue
        if _MENU_HEAD.match(s):
            mark(idx)
            flush_course()
            course = None
            cur = Menu(
                mid=f"menu-{len(menus) + 1:02d}",
                title=s.rstrip("."),
                season=season,
                service=service,
            )
            menus.append(cur)
            continue
        m = _COURSE_HEAD.match(line)
        if m and cur is not None:
            mark(idx)
            flush_course()
            title = m.group(1).strip()
            course = Course(title=title, declared=_declared_count(title), service=service)
            cur.courses.append(course)
            continue
        if cur is not None and s:
            if course is None:
                # 組見出しを立てずに皿から始まる献立がある(menu-04)。
                # 落とさないよう見出しなしの組を立てる。数詞が無いのでオラクルの対象外
                course = Course(title="", declared=frozenset(), service=service)
                cur.courses.append(course)
            mark(idx)
            block.append(line)
    flush_course()
    # 見出しなしで立てた組のうち、皿が一つも入らなかったものは捨てる
    # (PG 転記者の注記だけが挟まった箇所に立つ)
    for m_ in menus:
        m_.courses = [c for c in m_.courses if c.title or c.dishes]
    return menus


def check() -> dict[str, object]:
    """数詞オラクル(G-02)。組ごとに宣言された皿数と実際の合計を照合する。"""
    menus = parse_menus()
    courses = [(m, c) for m in menus for c in m.courses]
    unread = [(m.mid, c.title) for m, c in courses if not c.declared]
    mismatched = [
        {"menu": m.mid, "course": c.title, "declared": sorted(c.declared), "actual": c.actual}
        for m, c in courses
        if c.declared and c.actual not in c.declared
    ]
    return {
        "menus": len(menus),
        "courses": len(courses),
        "dishes": sum(c.actual for _, c in courses),
        "unread_numerals": unread,
        "mismatched": mismatched,
    }


if __name__ == "__main__":
    r = check()
    print(f"献立 {r['menus']} / 組 {r['courses']} / 皿 {r['dishes']}")
    print(f"数詞を読めなかった組: {len(r['unread_numerals'])}  {r['unread_numerals'][:5]}")
    print(f"数詞と合わない組: {len(r['mismatched'])}")
    for row in r["mismatched"][:20]:
        print("   ", row)
