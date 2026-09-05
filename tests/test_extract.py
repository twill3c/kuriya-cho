"""スパン抽出(F-05)・相互参照(F-05b)と、その被覆(G-06 / G-13)。

期待値は 2026-09-05 に本文 628 レシピ・73,563 語を走査した実測から取っている。
"""

from __future__ import annotations

import pytest

from pipeline import crossref, extract
from pipeline.pg_parse import parse_sections
from tests.conftest import requires_book

pytestmark = pytest.mark.validation


# --- T-131: スパンの性質 ------------------------------------------------------


@pytest.mark.unit
def test_t131_spans_point_at_the_original_text():
    """スパンは原文の文字位置でなければならない(色分けが位置で描かれる)。"""
    text = "Mettez deux livres de beurre dans une casserole sur un feu doux."
    for s in extract.extract(text):
        assert text[s.start : s.end] == s.text


@pytest.mark.unit
def test_t131_categories_on_a_hand_checked_sentence():
    """陽性対照。例文が主張したい性質を実際に持つことを、期待値の前に確かめる(HC-068)。

    この 1 文には材料(beurre)・道具(casserole)・分量(deux / livres)・火(feu)・
    工程(Mettez)がすべて含まれる —— 本文 `veau-01` から取った語の組み合わせである。
    """
    text = "Mettez deux livres de beurre dans une casserole sur un feu doux."
    got = {s.text.lower(): s.category for s in extract.extract(text)}
    assert got["mettez"] == "action"
    assert got["beurre"] == "ingredient"
    assert got["casserole"] == "vessel"
    assert got["feu"] == "heat"
    assert got["livres"] == "quantity"
    assert got["deux"] == "quantity"


@pytest.mark.unit
def test_t131_clitics_are_not_coloured():
    """`mettez-les` は動詞だけを色づけする。接語に色は付かない。"""
    spans = extract.extract("mettez-les")
    assert [(s.text, s.category) for s in spans] == [("mettez", "action")]


@pytest.mark.unit
def test_t131_ez_words_that_are_not_verbs():
    """陰性対照。`-ez` で終わる非動詞に工程の色を付けない。"""
    for word in sorted(extract.NOT_VERBS_EZ):
        assert extract.extract(word) == [] or all(
            s.category != "action" for s in extract.extract(word)
        ), word


@pytest.mark.unit
def test_t131_spans_never_overlap():
    text = "Mettez deux livres de beurre; ôtez-les du feu et servez-les."
    spans = extract.extract(text)
    for a, b in zip(spans, spans[1:]):
        assert a.end <= b.start


# --- T-132: 被覆(G-06)------------------------------------------------------


@requires_book
def test_t132_almost_every_recipe_gets_ingredients_and_actions():
    """実測 2026-09-05: 材料 620/628・工程 611/628。付かない項は列挙できること。"""
    c = extract.coverage()
    assert c["recipes"] == 628
    assert c["with_category"]["ingredient"] >= 615  # type: ignore[index]
    assert c["with_category"]["action"] >= 605  # type: ignore[index]
    assert len(c["missing_ingredient"]) <= 12  # type: ignore[arg-type]
    assert len(c["missing_action"]) <= 22  # type: ignore[arg-type]


@requires_book
def test_t132_uncovered_recipes_are_cross_references_not_extractor_gaps():
    """材料が付かない項は、抽出器の穴ではなく**参照だけの項**であること。

    「被覆が足りない」と「そもそも書かれていない」は別物なので、区別できないと
    表を無駄に太らせることになる。実測 2026-09-05: 材料の付かない 8 件はすべて
    他の項へ送るだけの本文だった。
    """
    recipes = {r.rid: r for s in parse_sections() for r in s.recipes}
    index = crossref.Index()
    for rid in extract.coverage()["missing_ingredient"]:  # type: ignore[union-attr]
        r = recipes[rid]
        refs = crossref.references(r.text, index)
        assert refs or "précédent" in r.text.lower(), (rid, r.text[:120])


# --- T-133: 相互参照(G-13)---------------------------------------------------


@requires_book
def test_t133_reference_resolution_rate():
    """実測 2026-09-05: 参照 307 件・一致 164・部分 70・未解決 73(解決率 76.2%)。"""
    a = crossref.audit()
    assert a["references"] == 307
    assert a["counts"]["exact"] == 164  # type: ignore[index]
    assert a["resolved_rate"] > 0.72


@requires_book
def test_t133_the_book_names_the_chapters_of_the_missing_volume():
    """大文字組みの参照のうち、第一巻に無い章が第二巻の目次になる。

    章の参照をレシピ表題へ部分一致させると、この事実が消える(`ENTREMETS` が
    別の表題に当たってしまう)。**誤って解決してしまうと、発見そのものが無くなる**
    という形の失敗なので、名指しで押さえる。
    """
    absent = crossref.audit()["absent_sections"]
    assert set(absent) == {"ENTREMETS", "FARCES", "PATISSERIE", "POISSON", "SAUTÉ"}, absent
    known = {s.name for s in parse_sections()}
    for name in absent:
        assert name not in known, name


@pytest.mark.unit
def test_t133_emphasis_is_not_a_reference():
    """陰性対照: 手がかり語の無い斜体は参照ではない。

    これが効いていないと、松露を論じる長い斜体まで参照として拾う(実測で 72 件)。
    """
    index = crossref.Index.__new__(crossref.Index)
    index.recipes = {}
    index.sections = {}
    assert crossref.references("faites cuire au _bain-marie_ doucement", index) == []
    got = crossref.references("(Voyez _Mitonnage_.)", index)
    assert [r.text for r in got] == ["Mitonnage"]


@pytest.mark.unit
def test_t133_match_key_absorbs_number_and_accent():
    assert crossref.match_key("Langues de Bœufs") == crossref.match_key("Langues de Bœuf")
    assert crossref.match_key("Sauce à l’Italienne") == crossref.match_key("sauce a l'italienne")


@requires_book
def test_t133_unresolved_references_are_listed_not_hidden():
    """切れた参照を黙って消さない。名前を出せること(多くは第二巻を指す)。"""
    a = crossref.audit()
    names = [n for n, _ in a["unresolved_names"]]  # type: ignore[index]
    assert names, "未解決が 0 なら、解決器か手がかり語のどちらかが働いていない"
    assert "Farce cuite" in names
