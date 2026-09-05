"""画面(F-10..F-12)と出荷データ。

**テストが緑でも動かないことがある。** ここで見るのは静的な性質だけで、
実際に動くかどうかは `python harness/browser_check.py`(実ブラウザ検品)で見る。
どちらか一方では足りない。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import requires_book

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DATA = WEB / "data"

PAGES = (
    "index.html",
    "sagasu.html",
    "yomu.html",
    "taku.html",
    "ami.html",
    "asobu.html",
    "shikumi.html",
)

# フリート共通フッタ(koho-lens 準拠・5 項目・下部固定)
FOOTER_LINKS = (
    "https://github.com/twill3c/kuriya-cho/blob/main/LICENSE",
    "https://github.com/twill3c/kuriya-cho",
    "https://app-menu-amber.vercel.app/",
)

pytestmark = pytest.mark.integration


def html(page: str) -> str:
    return (WEB / page).read_text(encoding="utf-8")


# --- T-171: フッタ規約(F-12)------------------------------------------------


def test_t171_footer_on_every_page():
    for page in PAGES:
        src = html(page)
        assert 'class="app-footer"' in src, page
        for link in FOOTER_LINKS:
            assert link in src, (page, link)
        assert "© 2026 坂田哲朗" in src, page
        assert 'id="link-howto"' in src and 'id="link-design"' in src, page


def test_t171_footer_is_fixed_and_leaves_room():
    css = (WEB / "style.css").read_text(encoding="utf-8")
    assert "/* fleet: fixed footer */" in css
    assert "position: fixed" in css
    assert "--footer-h" in css
    # 本文がフッタに隠れない逃げがあること
    assert "padding: 0 0 calc(var(--footer-h)" in css


# --- T-172: 画面の骨格 --------------------------------------------------------


def test_t172_every_page_has_the_same_navigation():
    """章立てが画面ごとにずれると、利用者は迷子になる。"""
    navs = []
    for page in PAGES:
        src = html(page)
        start = src.index('<nav class="tabs">')
        end = src.index("</nav>", start)
        navs.append(src[start:end])
        assert f'href="{page}"' in src[start:end], page
    assert len(set(navs)) == 1, "画面ごとに案内の中身が違う"


def test_t172_pages_declare_language_and_viewport():
    for page in PAGES:
        src = html(page)
        assert '<html lang="ja">' in src, page
        assert 'name="viewport"' in src, page
        assert '<meta name="description"' in src, page


def test_t172_no_external_resources():
    """外部のフォント・スクリプトを読み込まない(課金経路と外部依存をゼロにする)。"""
    for page in (*PAGES, "style.css", "js/app.js", "js/generator.js"):
        src = (WEB / page).read_text(encoding="utf-8")
        for needle in ("https://fonts.", "cdn.", "unpkg", "googleapis", "http://"):
            assert needle not in src, (page, needle)


# --- T-173: 出荷データ --------------------------------------------------------


@requires_book
def test_t173_shipped_data_is_complete_and_consistent():
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    assert len(index["recipes"]) == 628
    assert len(index["sections"]) == 32
    for s in index["sections"]:
        assert s["name_ja"], s["sid"]
        path = DATA / "recipes" / f"{s['sid']}.json"
        if s["count"] == 0:
            continue
        assert path.exists(), s["sid"]
        pack = json.loads(path.read_text(encoding="utf-8"))
        assert len(pack["recipes"]) == s["count"], s["sid"]


@requires_book
def test_t173_span_offsets_are_inside_their_paragraph():
    """位置が段落の外を指していたら、画面は文字を切り落とす。"""
    for path in sorted((DATA / "recipes").glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        for r in pack["recipes"]:
            for i, para in enumerate(r["paragraphs"]):
                for group in (r["spans"][i], r["changes"][i], r["refs"][i]):
                    for m in group:
                        assert 0 <= m["s"] < m["e"] <= len(para), (r["rid"], i, m)


@requires_book
def test_t173_change_offsets_quote_the_original_text():
    """綴りの差分が指す位置に、本当にその語があること。"""
    for path in sorted((DATA / "recipes").glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        for r in pack["recipes"]:
            for i, para in enumerate(r["paragraphs"]):
                for c in r["changes"][i]:
                    assert para[c["s"] : c["e"]] == c["old"], (r["rid"], c)


@requires_book
def test_t173_no_lexicon_is_shipped():
    """4.5 MB の語彙集は配らない(判定の道具であって、配るものではない)。"""
    names = {p.name for p in DATA.rglob("*")}
    assert "fr_words.json" not in names
    assert "fr_words_alt.txt" not in names
    total = sum(p.stat().st_size for p in DATA.rglob("*.json"))
    assert total < 3_000_000, f"出荷データが大きすぎる({total:,} B)"


@requires_book
def test_t173_resolved_references_point_at_shipped_recipes():
    """たどれる参照の先が、配ったデータの中に実在すること。

    参照先が無いのに色だけ付いていると、押しても何も起きない。
    """
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    rids = {r["rid"] for r in index["recipes"]}
    sids = {s["sid"] for s in index["sections"]}
    for path in sorted((DATA / "recipes").glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        for r in pack["recipes"]:
            for group in r["refs"]:
                for ref in group:
                    if ref["to"] is not None:
                        assert ref["to"] in rids or ref["to"] in sids, (r["rid"], ref)
