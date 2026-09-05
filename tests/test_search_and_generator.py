"""材料から引く索引(F-08 / G-09)と、架空の一皿の生成器(F-09 / G-10)。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import generator, search_index
from pipeline.pg_parse import parse_sections
from tests.conftest import requires_book

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.validation

node = shutil.which("node")
requires_node = pytest.mark.skipif(node is None, reason="node が無い環境では二実装照合を飛ばす")


# --- T-151: 索引(F-08 / G-09)-----------------------------------------------


@requires_book
def test_t151_index_is_verified_without_using_the_index():
    """G-09。索引に載せた材料が、**索引を使わない**素の走査で原文に見つかること。

    語幹化も合字の開きも検算側では再現しない。同じ道具で確かめると恒等式になる(HC-045)。
    実測 2026-09-05: 転置 5,395 項目すべて合格。
    """
    idx = search_index.build()
    assert search_index.verify(idx) == []
    assert sum(len(v) for v in idx["postings"].values()) > 5000  # type: ignore[union-attr]


@requires_book
def test_t151_the_verification_actually_bites():
    """陽性対照(HC-041)。索引に嘘の項目を入れたら検算が落ちること。

    「違反 0」は、索引が正しいときも検算が働いていないときも同じ緑を返す。
    """
    idx = search_index.build()
    idx["postings"]["beurre"].append("maigre-01")  # type: ignore[union-attr]
    bad = search_index.verify(idx)
    assert {"term": "beurre", "rid": "maigre-01"} in bad


@requires_book
def test_t151_chips_are_words_that_really_occur():
    """チップは本書に実際に出る材料に限る。押して 0 件になるチップを出さない。"""
    idx = search_index.build()
    freq: dict[str, int] = idx["freq"]  # type: ignore[assignment]
    for term in idx["chips"]:  # type: ignore[union-attr]
        assert freq[term] >= search_index.MIN_DOC_FREQ
        assert search_index.search(idx, [term]), term


@requires_book
def test_t151_more_matched_ingredients_rank_higher():
    """順位の規則(一致した材料の種類数が第一)が実際に効いていること。"""
    idx = search_index.build()
    hits = search_index.search(idx, ["beurre", "truffe"])
    counts = [len(h["matched"]) for h in hits]  # type: ignore[arg-type]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == 2, "二つとも含む項が一つも無いなら、この検査は何も見ていない"


# --- T-152: 生成器の二実装照合(G-10)----------------------------------------


@requires_node
def test_t152_random_draws_match_between_python_and_javascript():
    """経路の照合(HC-065)。乱数の生の出目が一致すること。

    結論(料理名)だけを比べると、別の理由で同じ答えに着いたときに気づけない。
    """
    for seed in (0, 1, 7, 12345, 0xFFFFFFF0):
        out = subprocess.run(
            [node, str(ROOT / "tests" / "js_generate.mjs"), "draws", str(seed), "64"],
            capture_output=True, text=True, check=True,
        )
        js = json.loads(out.stdout)
        rnd = generator.mulberry32(seed)
        py = [rnd() for _ in range(64)]
        assert js == py, seed


@requires_book
@requires_node
def test_t152_generated_titles_match_between_python_and_javascript():
    """結論の照合。同じ (種類, 段, seed) で**完全に同じ文字列**を返すこと。

    浮動小数点を使わない設計にしてあるので、「だいたい一致」ではなく完全一致を要求できる。
    """
    model = generator.build()
    data = ROOT / "web" / "data" / "generator.json"
    assert data.exists(), "先に python -m pipeline.build_web を実行すること"
    for kind in model.kinds:
        for step in range(len(generator.STEPS)):
            out = subprocess.run(
                [node, str(ROOT / "tests" / "js_generate.mjs"), "titles", kind, str(step), "40"],
                capture_output=True, text=True, check=True,
            )
            js = json.loads(out.stdout)
            py = [generator.generate(model, kind, step, seed) for seed in range(40)]
            assert js == py, (kind, step, [a for a, b in zip(js, py) if a != b][:3])


@requires_book
@requires_node
def test_t152_the_cross_check_would_catch_a_divergence():
    """陽性対照(HC-065)。片方の重みをずらしたら照合が落ちること。

    照合が経路を見ていないなら、重みを変えても同じ結論に着いてしまう場面がある。
    """
    model = generator.build()
    out = subprocess.run(
        [node, str(ROOT / "tests" / "js_generate.mjs"), "titles", "sauce", "1", "40"],
        capture_output=True, text=True, check=True,
    )
    js = json.loads(out.stdout)
    shifted = [generator.generate(model, "sauce", 2, seed) for seed in range(40)]
    assert js != shifted, "段を変えても同じ出力なら、つまみが何も効いていない"


# --- T-153: 決定論と新奇性(G-10)--------------------------------------------


@requires_book
def test_t153_same_seed_same_dish():
    model = generator.build()
    for kind in model.kinds:
        a = [generator.generate(model, kind, 1, s) for s in range(20)]
        b = [generator.generate(model, kind, 1, s) for s in range(20)]
        assert a == b


@requires_book
def test_t153_novelty_is_measured_before_it_is_filtered():
    """新奇性は**弾く前に測る**。生成器は実在表題の集合を参照しない。

    参照させると「実在しないものだけを作る生成器」になり、測定が恒等式になる。
    実測 2026-09-05: 種類・段によって新奇率は 47〜93% で、**つまみと単調な関係にない**。
    つまみが動かすのは「本書の並びにどれだけ忠実か」であって、新奇性ではない。
    """
    import inspect

    src = inspect.getsource(generator.generate)
    assert "real_titles" not in src

    model = generator.build()
    n = generator.novelty(model, "viande", 1, count=100)
    assert n["generated"] == 100
    assert n["novel"] > 0
    assert n["empty"] == 0


@requires_book
def test_t153_every_kind_can_generate():
    """1 品しか無い章(DAIM)を単独の種類にしない。どの種類も名前を作れること。"""
    model = generator.build()
    for kind in model.kinds:
        made = [generator.generate(model, kind, 0, s) for s in range(10)]
        assert all(m.strip() for m in made), kind


@requires_book
def test_t153_kinds_cover_every_section():
    """種類の割り当てから章が漏れていないこと(漏れると作れない料理名が出る)。"""
    covered = {sid for _label, sids in generator.KINDS.values() for sid in sids}
    actual = {s.sid for s in parse_sections()}
    assert covered == actual, (actual - covered, covered - actual)
