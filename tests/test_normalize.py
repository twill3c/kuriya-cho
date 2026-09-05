"""綴りの正規化(F-04)と、その効き・巻き添えの測定(G-04 / G-05)。

期待値の出所は、2026-09-05 に本書の地の文 82,987 照合形と現代フランス語の語彙集
344,060 形を突き合わせた実測である(`python -m pipeline.spelling_audit` で再現できる)。
"""

from __future__ import annotations

import pytest

from pipeline import normalize, spelling_audit
from pipeline.fetch_sources import load_modern_lexicon
from pipeline.tokenize_fr import lookup_forms, tokenize
from tests.conftest import requires_book, requires_lexicon

pytestmark = pytest.mark.validation


# --- T-121: 切り出し(照合の土台)---------------------------------------------


@pytest.mark.unit
def test_t121_lookup_forms_splits_elision_and_clitics():
    """省略形と接語を剥がさないと、語彙集への照合が切り出しの失敗を測ってしまう。"""
    assert lookup_forms("d’huile") == ["de", "huile"]
    assert lookup_forms("servez-vous-en") == ["servez", "vous", "en"]
    assert lookup_forms("faites-les") == ["faites", "les"]
    assert lookup_forms("œufs") == ["oeufs"]  # 合字は語彙集の綴りへ
    assert lookup_forms("aujourd’hui") == ["aujourd'hui"]


@pytest.mark.unit
def test_t121_tokenize_keeps_original_offsets():
    """表層と位置は原文どおりでなければならない(色分けと三層表示が位置を使う)。"""
    text = "Ayez d’excellens œufs; mettez-les très-doucement."
    for tok in tokenize(text):
        assert text[tok.start : tok.end] == tok.text


# --- T-122: 正規化の規則と辞書 ------------------------------------------------


@pytest.mark.unit
def test_t122_rules_do_not_consult_a_lexicon():
    """規則が語彙集を引いてはならない(引くと G-04 が恒等式になる)。

    実装の中身を検査する: `normalize` は語彙集の読み込みを import していない。
    """
    import inspect

    src = inspect.getsource(normalize)
    assert "load_modern_lexicon" not in src
    assert "fetch_sources" not in src


@pytest.mark.unit
def test_t122_handles_elision_and_clitics_around_dictionary_words():
    """`d’excellens` `alongez-la` `L’entre-côte` を直せること。

    どれも 2026-09-05 に実際に取り逃していた形である。
    """
    assert normalize.modernize("d’excellens mets") == "d’excellents mets"
    assert normalize.modernize("alongez-la") == "allongez-la"
    assert normalize.modernize("L’entre-côte") == "L’entrecôte"
    assert normalize.modernize("liez l’hatelet") == "liez l’hâtelet"


@pytest.mark.unit
def test_t122_rule_and_dictionary_can_apply_to_one_word():
    """`très-légérement` はハイフンの規則と辞書の両方が当たる。"""
    assert normalize.modernize("très-légérement") == "très légèrement"


@pytest.mark.unit
def test_t122_case_is_preserved():
    assert normalize.modernize("Précédens") == "Précédents"
    assert normalize.modernize("RAGOUTS") == "RAGOÛTS"


@pytest.mark.unit
def test_t122_changes_carry_original_offsets():
    text = "Mettez des présens; ôtez le très-fin."
    for c in normalize.find_changes(text):
        assert text[c.start : c.end] == c.old


# --- T-123: G-04 効きの測定(非循環)------------------------------------------


@requires_book
@requires_lexicon
def test_t123_normalization_halves_the_out_of_lexicon_rate():
    """正規化の前後で、現代語彙集に載らない率が下がること。

    正規化は語彙集を引かない(T-122)ので、この比較は循環しない。
    実測 2026-09-05: 0.8652% → 0.4333%。境界は実測より緩く置く。
    """
    a = spelling_audit.audit()
    before = a["book"]["rate"]  # type: ignore[index]
    after = a["book_normalized"]["rate"]  # type: ignore[index]
    assert before > after, (before, after)
    assert after < before * 0.6, (before, after)
    assert a["changes"] > 300  # type: ignore[operator]


@requires_book
@requires_lexicon
def test_t123_the_1896_control_is_further_from_the_lexicon():
    """対照(綴りが現代の 1896 年の料理書)より、1814 年の本のほうが語彙集に近い。

    これは事前の見込み(「1814 年の綴りが読解の壁」)を**壊した**測定である。
    壊れた見込みを消さずにテストとして残す —— 逆転したら気づけるようにするため。
    実測 2026-09-05: 1814 年 0.8652% / 1896 年 1.6243%。
    """
    a = spelling_audit.audit()
    assert a["control_1896"]["rate"] > a["book"]["rate"]  # type: ignore[index]


# --- T-124: G-05 巻き添えの測定 -----------------------------------------------


@requires_lexicon
def test_t124_rules_break_no_modern_word():
    """陰性対照: 採用した規則を現代語彙集 344,060 形すべてに当てて、壊れる語が 0。"""
    coll = spelling_audit.rule_collateral(load_modern_lexicon())
    for name, _pattern, _repl, _note in normalize.RULES:
        assert coll[name]["breaks"] == 0, (name, coll[name])


@requires_lexicon
def test_t124_the_textbook_rule_would_have_broken_hundreds():
    """陽性対照: 採用しなかった `-ans` → `-ants` は、当てれば大量に壊す。

    この対照が無いと「壊れる語 0」が、規則が安全なのか計測が働いていないのかを言わない。
    実測 2026-09-05: 現代語彙 726 語に当たり 723 語を壊す。
    """
    coll = spelling_audit.rule_collateral(load_modern_lexicon())
    row = coll["ans-to-ants (不採用)"]
    assert row["applies_to"] > 500
    assert row["breaks"] > 500


@requires_lexicon
def test_t124_every_dictionary_target_is_a_modern_word():
    """例外辞書の置換先がすべて現代語彙集に実在すること。"""
    assert spelling_audit.lexicon_targets_are_real(load_modern_lexicon()) == []


@pytest.mark.unit
def test_t124_not_archaic_words_are_never_rewritten():
    """「語彙集に無い = 古い」と決めつけない。料理語と地名は原文のまま残す。"""
    for word in normalize.NOT_ARCHAIC:
        if word.endswith("-"):  # `demi-` は接頭辞としての注記
            continue
        assert word not in normalize.ARCHAIC, word
        assert normalize.modernize(word) == word, word
