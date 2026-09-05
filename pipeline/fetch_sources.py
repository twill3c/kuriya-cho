"""外部素材の取得(F-01)。

取得するのは二種類:

1. **本文** — Project Gutenberg #64976 『L'Art du Cuisinier, tome I』(Beauvilliers 1814)。
   底本は BnF/Gallica の画像。PG の plain-text UTF-8 版を使う。
2. **現代フランス語の語彙集** — 正規化(1814 年綴り → 現代綴り)の**非循環オラクル**。
   自分で書いた規則の正しさを、自分の規則で判定してはならない(G-02)。
   外部の権威(Grammalecte/Dicollecte 由来の屈折形リスト)に照らす。

いずれも `data/raw/` にキャッシュし、二度目以降はネットワークに触れない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

UA = "kuriya-cho/1.0 (fleet research build; contact via github.com/twill3c)"


@dataclass(frozen=True)
class Source:
    key: str
    url: str
    filename: str
    note: str


SOURCES: tuple[Source, ...] = (
    Source(
        key="pg64976",
        url="https://www.gutenberg.org/cache/epub/64976/pg64976.txt",
        filename="pg64976.txt",
        note="Beauvilliers, L'Art du Cuisinier, tome I (1814). Public domain (PG #64976).",
    ),
    Source(
        key="fr_words",
        url="https://raw.githubusercontent.com/words/an-array-of-french-words/master/index.json",
        filename="fr_words.json",
        note="現代フランス語の屈折形リスト(Grammalecte/Dicollecte 由来)。正規化の外部オラクル。",
    ),
    Source(
        key="fr_words_alt",
        url="https://raw.githubusercontent.com/Taknok/French-Wordlist/master/francais.txt",
        filename="fr_words_alt.txt",
        note="現代フランス語の第二の語彙集。オラクルを一本に頼らないための突合用。",
    ),
)

BY_KEY = {s.key: s for s in SOURCES}


def path_of(key: str) -> Path:
    return RAW / BY_KEY[key].filename


def fetch(source: Source, *, force: bool = False) -> Path:
    dest = RAW / source.filename
    if dest.exists() and not force:
        return dest
    RAW.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(source.url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()
    if not payload:
        raise RuntimeError(f"{source.key}: 空の応答")
    dest.write_bytes(payload)
    return dest


def load_text(key: str) -> str:
    """取得済みの素材をテキストとして読む。未取得なら明示的に落とす。"""
    p = path_of(key)
    if not p.exists():
        raise FileNotFoundError(
            f"{key} が未取得です。`python pipeline/fetch_sources.py` を先に実行してください。"
        )
    return p.read_text(encoding="utf-8")


def load_modern_lexicon() -> frozenset[str]:
    """現代フランス語の語形集合(小文字化・アポストロフィ正規化済み)。

    二つの出所を**合併**して使う。片方にしか無い語で「規則が効かなかった」と
    判定するのを避けるためで、合併は判定を甘くする方向にしか働かない
    (= 規則の効きを過大評価しない)。
    """
    words: set[str] = set()
    primary = json.loads(load_text("fr_words"))
    words.update(w.lower() for w in primary)
    for line in load_text("fr_words_alt").splitlines():
        w = line.strip().lower()
        if w:
            words.add(w)
    return frozenset(words)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="外部素材の取得")
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して取り直す")
    ap.add_argument("--only", help="key をカンマ区切りで限定")
    args = ap.parse_args(argv)

    keys = args.only.split(",") if args.only else [s.key for s in SOURCES]
    manifest = []
    for key in keys:
        src = BY_KEY[key]
        dest = fetch(src, force=args.force)
        size = dest.stat().st_size
        digest = sha256_of(dest)
        manifest.append(
            {"key": key, "url": src.url, "bytes": size, "sha256": digest, "note": src.note}
        )
        print(f"{key:14s} {size:>9,d} B  {digest[:16]}  {dest.relative_to(ROOT)}")

    (RAW / "SOURCES.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
