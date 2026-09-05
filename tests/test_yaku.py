"""和訳(F-06 / F-07)と字種検査(G-08)。

充填率は**分子と分母**で押さえる。「和訳あり」で通してしまうと、
訳していないものを訳したように見せる余地が残る。
"""

from __future__ import annotations

import re

import pytest

from pipeline import yaku
from pipeline.pg_parse import parse_sections
from tests.conftest import requires_book

pytestmark = pytest.mark.validation


# --- T-141: 充填(F-06 / F-07)------------------------------------------------


@requires_book
def test_t141_every_recipe_title_is_translated():
    """料理名は全件訳す(F-06)。本文に無い鍵が残っていないことも見る。"""
    c = yaku.coverage()
    assert c["titles_missing"] == [], c["titles_missing"][:10]
    assert c["titles_extra"] == [], c["titles_extra"]
    assert c["titles_translated"] == c["recipes"] == 628


@requires_book
def test_t141_every_section_name_is_translated():
    c = yaku.coverage()
    assert c["sections_missing"] == []
    assert c["sections_translated"] == c["sections"] == 32


@requires_book
def test_t141_body_coverage_is_reported_as_a_fraction():
    """本文の訳は途中である。**途中であることが数で出る**ことを要求する。

    実測 2026-09-05: 12 / 628。ここは増える方向にしか動かない。
    """
    c = yaku.coverage()
    assert 0 < c["bodies_translated"] <= c["recipes"]
    assert c["bodies_translated"] >= 12


@requires_book
def test_t141_translated_bodies_point_at_real_recipes():
    rids = {r.rid for s in parse_sections() for r in s.recipes}
    assert set(yaku.load_bodies()) <= rids


@requires_book
def test_t141_translated_bodies_have_the_same_paragraph_count():
    """段落の数を原文と揃える。段落が落ちたまま訳し終えたことにしない。"""
    recipes = {r.rid: r for s in parse_sections() for r in s.recipes}
    for rid, paragraphs in yaku.load_bodies().items():
        assert len(paragraphs) == len(recipes[rid].paragraphs), rid


# --- T-142: 字種検査(G-08)---------------------------------------------------


def test_t142_no_foreign_script_or_invisible_characters():
    """和訳の全文にキリル・ギリシア文字と不可視文字が無いこと。"""
    assert yaku.check_scripts() == []


@pytest.mark.unit
def test_t142_the_check_actually_bites():
    """陽性対照(HC-041)。検査が働いていないときも「違反 0」を返すので、確かめる。

    キリル文字の `а`(U+0430)はラテン文字の `a` と字形が同じで、目視では捕まらない。
    """
    assert yaku.bad_characters("ソース а のこと"), "キリル文字を捕まえられていない"
    assert yaku.bad_characters("見えない​文字"), "ゼロ幅空白を捕まえられていない"
    # 陰性対照: 正常な和訳文・原語併記・数値は落とさない
    assert yaku.bad_characters("褐色のイタリアンヌ(sauce italienne rousse)") == []
    assert yaku.bad_characters("約 490 g とされる") == []


# --- T-143: 用語集(F-06)-----------------------------------------------------


@pytest.mark.unit
def test_t143_glossary_entries_are_complete():
    for term in yaku.load_glossary():
        assert term["fr"] and term["ja"] and term["kind"], term


@pytest.mark.unit
def test_t143_units_are_never_given_a_hard_conversion():
    """単位の注に**現代の単位への断定的な換算**を書かない(SPEC §6)。

    当時の verre / cuillerée は器が決まっておらず、換算できない。
    現代の単位(g / cm / ℓ 等)を数値つきで出すなら「約」「とされる」を必ず伴うこと。

    **当時の体系の内部の比は換算ではない** —— `once` は定義上 `livre` の 16 分の 1 で、
    これは正確な値である。ここを一緒くたに禁じると、正しい記述まで落ちる
    (2026-09-05 に一度そう書いて `gros` の注で赤になった)。
    """
    modern = re.compile(r"\d+(?:\.\d+)?\s*(?:g|kg|mg|cm|mm|m|ml|l|ℓ|グラム|センチ|リットル)\b")
    for term in yaku.load_glossary():
        if term["kind"] != "unit":
            continue
        note = term.get("note", "")
        if modern.search(note):
            assert "約" in note or "とされる" in note, term
