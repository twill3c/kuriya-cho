"""献立の分割(F-03)と数詞オラクル(G-02)、消費率(G-03)。

数詞オラクルは**本文をいっさい使わない**。組見出しの数詞(`Seize Entrées` = 16)と、
その組に並ぶ皿の数の合計を突き合わせるだけなので、
分割器の正しさを分割器で確かめる循環にならない(HC-045)。
"""

from __future__ import annotations

import pytest

from pipeline import coverage, menus
from tests.conftest import requires_book

pytestmark = [pytest.mark.validation, requires_book]


# 実測 2026-09-05。SERVICES DE TABLE 全 715 行を走査した値
MENUS = 13
COURSES = 85
DISHES = 488
# 数詞オラクルが説明できない食い違い —— どちらも**原文の側**の性質である
KNOWN_MISMATCH = {
    ("menu-03", "Deux Salades."),  # 組見出しだけあって皿が一つも並んでいない
    ("menu-13", "Six Entremets."),  # 6 と書いて 7 品並ぶ(7 品目は「1 salade.」)
}


def test_t111_menu_counts():
    ms = menus.parse_menus()
    assert len(ms) == MENUS
    assert sum(len(m.courses) for m in ms) == COURSES
    assert sum(c.actual for m in ms for c in m.courses) == DISHES


def test_t112_numeral_oracle():
    """G-02。宣言された皿数と実際の合計が、既知の 2 件を除いて一致すること。"""
    r = menus.check()
    got = {(row["menu"], row["course"]) for row in r["mismatched"]}
    assert got == KNOWN_MISMATCH, got


def test_t112_oracle_actually_bites():
    """陽性対照(HC-041): 段組みの復元を壊したら数詞オラクルが落ちること。

    「食い違い 2 件」は、オラクルが働いているときも、働いていないときも同じ緑を返す。
    列の切り出しを左端 1 列に潰して、実際に赤が出ることを確かめる。
    """
    block = [
        "  1 printanier.                     1 au blé vert.",
        "  1 aux choux nouveaux.             1 de pâte d’Italie.",
    ]
    full = menus._parse_course_block(block)
    assert sum(d.count for d in full) == 4, "陽性対照の入力が 2 列になっていない"

    original = menus._column_starts
    try:
        menus._column_starts = lambda _block: [0]  # 段組みを見ない実装に差し替える
        broken = menus._parse_course_block(block)
    finally:
        menus._column_starts = original
    assert sum(d.count for d in broken) < 4, "列を潰しても皿数が減らない = 復元を見ていない"


def test_t113_declared_counts_follow_french_grammar():
    """数詞の読みは実データではなくフランス語の数え方から来ている(HC-045)。"""
    assert menus._declared_count("Seize Entrées.") == frozenset({16})
    assert menus._declared_count("Quatre gros Entremets.") == frozenset({4})
    # 読点より後ろは但し書き
    assert menus._declared_count("Six Plats de Rôt, dont deux gros.") == frozenset({6})
    # ou は選択 / à は範囲 / et は加算
    assert menus._declared_count("Huit ou dix Entrées.") == frozenset({8, 10})
    assert menus._declared_count("Treize à quinze Assiettes de dessert.") == frozenset({13, 14, 15})
    assert menus._declared_count("Deux gros et deux moyens Entremets.") == frozenset({4})
    # 一行に見出しが二つ並ぶ形は合計
    assert menus._declared_count("Huit Hors-d’œuvres d’entrées.    Huit Entrées.") == frozenset({16})
    # 数詞が無ければ空集合(オラクルの対象外)
    assert menus._declared_count("Potage.") == frozenset()


def test_t114_menu_coverage_is_total():
    cov = coverage.menus_coverage()
    assert cov["residue"] == [], cov["residue"][:10]
    assert cov["rate"] == 1.0


def test_t114_second_service_is_not_dropped():
    """饗応の切り替えで献立を打ち切らないこと(消費率が出した取りこぼし)。"""
    m5 = next(m for m in menus.parse_menus() if m.mid == "menu-05")
    services = {c.service for c in m5.courses}
    assert any("MILIEU" in s for s in services), services
