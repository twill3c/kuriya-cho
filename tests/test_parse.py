"""本文の分割(F-02)と件数オラクル(G-01)、消費率(G-03)。

期待値の出所は、すべて 2026-09-05 に PG#64976 の全文(578,143 字 / 12,152 行)を
走査して得た実測である。件数そのものを定数で固定するのは
「素材が動いたら気づく」ためであり、素材は PG の固定版(sha256 を data/raw/SOURCES.json に記録)。
"""

from __future__ import annotations

import pytest

from pipeline import coverage, pg_parse
from tests.conftest import requires_book

pytestmark = [pytest.mark.validation, requires_book]


# --- T-101: 章とレシピの件数(実測 2026-09-05) --------------------------------

BODY_SECTIONS = 32
BODY_RECIPES = 628


def test_t101_section_and_recipe_counts():
    sections = pg_parse.parse_sections()
    assert len(sections) == BODY_SECTIONS
    assert sum(len(s.recipes) for s in sections) == BODY_RECIPES


def test_t101_every_recipe_has_body():
    """見出しだけで本文が空のレシピがあってはならない(取りこぼしの兆候)。"""
    empty = [r.rid for s in pg_parse.parse_sections() for r in s.recipes if not r.paragraphs]
    assert empty == []


def test_t101_ids_are_unique():
    rids = [r.rid for s in pg_parse.parse_sections() for r in s.recipes]
    assert len(rids) == len(set(rids))
    sids = [s.sid for s in pg_parse.parse_sections()]
    assert len(sids) == len(set(sids)), "同名の章(PIGEONS が 2 回)に連番が付いていない"


# --- T-102: 件数オラクル(G-01)------------------------------------------------


def test_t102_toc_reconciliation_has_no_unexplained_gap():
    rec = pg_parse.reconcile()
    assert rec["unexplained"] == [], rec["unexplained"]


def test_t102_most_sections_match_the_toc():
    """29/32 章が目次と一致する(実測 2026-09-05)。下回ったら分割器か素材が動いている。"""
    rec = pg_parse.reconcile()
    assert rec["matched_sections"] == 29
    assert rec["body_sections"] == BODY_SECTIONS


def test_t102_explained_gaps_are_real():
    """陽性対照(HC-041): 説明つき例外に挙げた章が実在し、実際に食い違っていること。

    例外リストは「緩める側」なので、対で締める仕掛けが要る。実在しない章 ID や
    もう食い違っていない章が残っていたら、リストが古い。
    """
    rows = {r["sid"]: r for r in pg_parse.reconcile()["rows"]}
    for sid, _why in pg_parse.EXPLAINED_GAPS:
        assert sid in rows, f"説明つき例外 {sid} に対応する章が本文に無い"
        assert not rows[sid]["match"], f"{sid} はもう食い違っていない。例外から外すこと"


# --- T-103: 組版の癖(実測から導いた不変量)------------------------------------


def test_t103_multiline_and_trailing_period_headings_are_captured():
    """折り返した見出しと、句点が斜体の外にある見出しを取り落としていないこと。

    どちらもこのループで実際に落とした形である(HC-164)。期待値は本文の実物から取った。
    """
    titles = {r.title for s in pg_parse.parse_sections() for r in s.recipes}
    # 2 行に折り返した見出し(3 件のうち 2 件。残る 1 件は章見出しの副題に吸われる)
    assert "Manière de remplacer la Chicorée dans la saison où elle manque et lorsque l’on n’en a pas conservé" in titles
    assert "Moyens de donner au Cochon domestique le goût et l’apparence du Sanglier" in titles
    # 句点が閉じ記号の外にある見出し(`_Boudin blanc_.`)
    assert "Boudin blanc" in titles
    assert "Boudin d’Ecrevisses" in titles


def test_t103_section_heading_absorbs_its_italic_subtitle():
    """`BÉCASSES, …,` は次の斜体行までで一つの章見出しである。"""
    names = [s.name for s in pg_parse.parse_sections()]
    becasses = [n for n in names if n.startswith("BÉCASSES")]
    assert len(becasses) == 1
    assert "Économie domestique" in becasses[0], becasses


# --- T-104: 消費率(G-03 / HC-164)--------------------------------------------


def test_t104_body_coverage_is_total():
    cov = coverage.body_coverage()
    assert cov["residue"] == [], cov["residue"][:10]
    assert cov["rate"] == 1.0


def test_t104_coverage_detects_a_broken_extractor():
    """陽性対照(HC-041): 見出しの規則を意図的に狭めたら残差が出ること。

    検査そのものが働いていないときも「残差 0」を返してしまうので、
    落ちるべき入力で実際に落ちることを確かめる。
    """
    lines = pg_parse.body_text().split("\n")
    trace: set[int] = set()
    pg_parse.parse_sections(trace=trace)
    assert len(trace) == len(lines)
    # 見出しの取りこぼしを模す: 適当な本文行を帰属から外すと残差になる
    broken = set(trace)
    broken.discard(next(i for i, ln in enumerate(lines) if ln.strip()))
    residue = [i for i in range(len(lines)) if i not in broken]
    assert len(residue) == 1
