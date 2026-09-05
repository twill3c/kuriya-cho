"""出荷物を作る(web/data/*.json)。

**実行時に外部を呼ばない。** 画面が使うものはすべてここで焼き込む。
現代フランス語の語彙集(4.5 MB)は**入れない** —— 正規化の判定に使う道具であって、
配るものではない。

出す JSON:

| ファイル | 中身 |
|---|---|
| `book.json` | 章 32・レシピ 628(原文・段落・和訳・綴りの差分・スパン・参照) |
| `menus.json` | 献立 13・組 85・皿 488 |
| `glossary.json` | 用語集 66 語 |
| `search.json` | 材料の転置索引とチップ |
| `generator.json` | 料理名の二重連鎖と実在表題 |
| `meta.json` | 計測値(「仕組みを見る」がそのまま読む) |
"""

from __future__ import annotations

import json
from pathlib import Path

from pipeline import crossref, extract, menus, normalize, search_index, yaku
from pipeline.coverage import body_coverage, menus_coverage
from pipeline.generator import build as build_generator
from pipeline.pg_parse import parse_sections, reconcile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data"


def _dump(name: str, payload: object) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path.stat().st_size


def build_book() -> dict[str, object]:
    sections = parse_sections()
    index = crossref.Index(sections)
    titles_ja = yaku.load_titles()
    sections_ja = yaku.load_sections()
    bodies_ja = yaku.load_bodies()

    out_sections = []
    out_recipes = []
    for s in sections:
        out_sections.append(
            {
                "sid": s.sid,
                "name": s.name,
                "name_ja": sections_ja.get(s.sid, ""),
                "lead": s.lead,
                "count": len(s.recipes),
            }
        )
        for r in s.recipes:
            refs = crossref.references(r.text, index)
            out_recipes.append(
                {
                    "rid": r.rid,
                    "sid": s.sid,
                    "title": r.title,
                    "title_ja": titles_ja.get(r.rid, ""),
                    "paragraphs": r.paragraphs,
                    "paragraphs_ja": bodies_ja.get(r.rid, []),
                    # 綴りの差分・スパン・参照は**段落ごとの文字位置**で持つ。
                    # 画面はこの位置で下線と色を描くので、原文の文字は一切変えない
                    "changes": [
                        [
                            {"s": c.start, "e": c.end, "old": c.old, "new": c.new, "k": c.kind}
                            for c in normalize.find_changes(p)
                        ]
                        for p in r.paragraphs
                    ],
                    "spans": [
                        [
                            {"s": sp.start, "e": sp.end, "c": sp.category}
                            for sp in extract.extract(p)
                        ]
                        for p in r.paragraphs
                    ],
                    "refs": [
                        [
                            {
                                "s": ref.start,
                                "e": ref.end,
                                "name": ref.text,
                                "to": ref.target,
                                "status": ref.status,
                            }
                            for ref in crossref.references(p, index)
                        ]
                        for p in r.paragraphs
                    ],
                    "reference_only": crossref.is_reference_only(r, refs),
                }
            )
    return {"sections": out_sections, "recipes": out_recipes}


def write_book() -> dict[str, int]:
    """本文は**章ごとに分けて**書く。

    1 ファイルに束ねると 1.66 MB になり、料理名の一覧しか要らない画面
    (入口・探す)まで全文を読み込むことになる。索引は軽くしておき、
    本文は開いた章だけ取りに行く。
    """
    book = build_book()
    recipes = book["recipes"]
    by_sid: dict[str, list[dict]] = {}
    for r in recipes:  # type: ignore[union-attr]
        by_sid.setdefault(r["sid"], []).append(r)

    sizes: dict[str, int] = {}
    (OUT / "recipes").mkdir(parents=True, exist_ok=True)
    for sid, rows in by_sid.items():
        path = OUT / "recipes" / f"{sid}.json"
        path.write_text(json.dumps({"recipes": rows}, ensure_ascii=False), encoding="utf-8")
        sizes[f"recipes/{sid}.json"] = path.stat().st_size

    # 索引は表題と目印だけ。本文・スパン・参照は持たない
    light = [
        {
            "rid": r["rid"],
            "sid": r["sid"],
            "title": r["title"],
            "title_ja": r["title_ja"],
            "has_ja": bool(r["paragraphs_ja"]),
            "ref_only": r["reference_only"],
            "chars": sum(len(p) for p in r["paragraphs"]),
        }
        for r in recipes  # type: ignore[union-attr]
    ]
    sizes["index.json"] = _dump(
        "index.json", {"sections": book["sections"], "recipes": light}
    )
    return sizes


def build_menus() -> dict[str, object]:
    out = []
    for m in menus.parse_menus():
        out.append(
            {
                "mid": m.mid,
                "title": m.title,
                "season": m.season,
                "service": m.service,
                "courses": [
                    {
                        "title": c.title,
                        "service": c.service,
                        "declared": sorted(c.declared),
                        "actual": c.actual,
                        "dishes": [
                            {"n": d.count, "text": d.text, "plate": d.plate} for d in c.dishes
                        ],
                    }
                    for c in m.courses
                ],
            }
        )
    return {"menus": out}


def build_search() -> dict[str, object]:
    idx = search_index.build()
    freq: dict[str, int] = idx["freq"]  # type: ignore[assignment]
    return {
        "chips": [{"term": t, "count": freq[t]} for t in idx["chips"]],  # type: ignore[union-attr]
        "postings": idx["postings"],
        "title_terms": {
            rid: sorted(e.title_terms) for rid, e in idx["entries"].items()  # type: ignore[union-attr]
        },
    }


def build_meta() -> dict[str, object]:
    rec = reconcile()
    body = body_coverage()
    mcov = menus_coverage()
    mchk = menus.check()
    ecov = extract.coverage()
    cross = crossref.audit()
    ycov = yaku.coverage()
    return {
        "source": json.loads((ROOT / "data" / "raw" / "SOURCES.json").read_text(encoding="utf-8")),
        "parse": {
            "sections": rec["body_sections"],
            "recipes": rec["body_recipes"],
            "toc_entries": rec["toc_entries"],
            "matched_sections": rec["matched_sections"],
            "unexplained": rec["unexplained"],
            "rows": rec["rows"],
        },
        "coverage": {
            "body_lines": body["lines"],
            "body_rate": body["rate"],
            "menu_lines": mcov["lines"],
            "menu_rate": mcov["rate"],
        },
        "menus": {
            "menus": mchk["menus"],
            "courses": mchk["courses"],
            "dishes": mchk["dishes"],
            "mismatched": mchk["mismatched"],
            "unread": mchk["unread_numerals"],
        },
        "extract": {
            "with_category": ecov["with_category"],
            "recipes": ecov["recipes"],
            "word_coverage": ecov["word_coverage"],
            "missing_ingredient": ecov["missing_ingredient"],
            "missing_action": ecov["missing_action"],
        },
        "crossref": {
            "references": cross["references"],
            "counts": cross["counts"],
            "resolved_rate": cross["resolved_rate"],
            "absent_sections": cross["absent_sections"],
            "reference_only": cross["reference_only"],
            "unresolved_names": cross["unresolved_names"][:40],  # type: ignore[index]
        },
        "yaku": ycov,
        # 綴りの計測は外部の語彙集が要るので、ここでは**測り直さずに**
        # loop_002 の実測値を書き写す。数字の出所を偽らないため、測定日と再現手順を添える
        "spelling": {
            "measured_on": "2026-09-05",
            "how": "python -m pipeline.spelling_audit(現代フランス語の語彙集 344,060 形)",
            "book_forms": 82987,
            "book_misses": 718,
            "book_rate": 718 / 82987,
            "normalized_misses": 360,
            "normalized_rate": 360 / 83081,
            "control_title": "Auguste Hélie『Traité Général de la Cuisine Maigre』(PG #6966・序 1896-12)",
            "control_forms": 61440,
            "control_misses": 998,
            "control_rate": 998 / 61440,
            "changes": 360,
            "textbook_rule_applies_to": 726,
            "textbook_rule_breaks": 723,
        },
    }


def main() -> int:
    sizes = {
        **write_book(),
        "menus.json": _dump("menus.json", build_menus()),
        "glossary.json": _dump("glossary.json", {"terms": yaku.load_glossary()}),
        "search.json": _dump("search.json", build_search()),
        "generator.json": _dump("generator.json", build_generator().to_json()),
        "meta.json": _dump("meta.json", build_meta()),
    }
    total = sum(sizes.values())
    for name, size in sizes.items():
        print(f"  {name:16s} {size:>9,d} B")
    print(f"  {'合計':16s} {total:>9,d} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
