"""全ソースの構文検査(T-161 / HC-169)。

**編集経路の規範は破られる前提で置く。** 「シェル経由でコードを編集しない」という規範は
フリートで何度も破られており、破ったときに起きるのは構文エラーか、
**構文エラーにならないまま意味が変わること**である。どちらも、そのファイルが
どのテストからも `import` されていなければ、走らせるまで気づけない。

このテストは `import` の有無に関わらず**全ファイル**に当たる。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PY_DIRS = ("pipeline", "tests", "harness")
JS_GLOBS = ("web/js/*.js", "tests/*.mjs")


def python_sources() -> list[Path]:
    out: list[Path] = []
    for d in PY_DIRS:
        out += sorted(p for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)
    return out


def js_sources() -> list[Path]:
    out: list[Path] = []
    for g in JS_GLOBS:
        out += sorted(ROOT.glob(g))
    return out


@pytest.mark.unit
def test_t161_every_python_source_compiles():
    files = python_sources()
    assert len(files) >= 12, f"走査対象が少なすぎる({len(files)} 件)。パスの指定が壊れている"
    for path in files:
        src = path.read_text(encoding="utf-8")
        compile(src, str(path), "exec")


@pytest.mark.unit
def test_t161_every_javascript_source_parses():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が無い環境では飛ばす")
    files = js_sources()
    assert len(files) >= 2, f"走査対象が少なすぎる({len(files)} 件)"
    for path in files:
        r = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        assert r.returncode == 0, f"{path.name}: {r.stderr}"


@pytest.mark.unit
def test_t162_text_hygiene_runs_and_passes():
    """配られた検査器を**実際に走らせる**(HC-172)。

    スキャフォールドは `harness/text_hygiene.py` を全プロジェクトへ配り、
    `scaffoldctl status` は中身が正本と一致していることを見る。しかし
    **走っているかは誰も見ていない**。このループでは、正しく配られ最新で
    一度も実行されていないこの検査器が、手で走らせた途端に 4 件を出した
    (docstring に紛れたハングル 1 件・制御文字の印 3 件)。
    """
    r = subprocess.run(
        [sys.executable, str(ROOT / "harness" / "text_hygiene.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.unit
def test_t162_text_hygiene_self_test_passes():
    """検査器自身の対照。**壊れて何も検出しなくなった検査器は「違反 0」と区別できない。**"""
    r = subprocess.run(
        [sys.executable, str(ROOT / "harness" / "text_hygiene.py"), "--self-test"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.unit
def test_t161_the_check_actually_bites(tmp_path):
    """陽性対照(HC-041)。実際に踏んだ壊し方で、検査が落ちることを確かめる。

    `"\\n"` を書いたつもりが実改行になり、文字列リテラルが閉じない —— これが
    2026-09-05 に `build_web.py` で起きた形そのものである。
    """
    broken = tmp_path / "broken.py"
    broken.write_text('lines = body.split("\n")\n', encoding="utf-8")
    with pytest.raises(SyntaxError):
        compile(broken.read_text(encoding="utf-8"), str(broken), "exec")

    node = shutil.which("node")
    if node is None:
        return
    bad_js = tmp_path / "broken.mjs"
    bad_js.write_text('const s = "abc\n";\n', encoding="utf-8")
    r = subprocess.run([node, "--check", str(bad_js)], capture_output=True, text=True)
    assert r.returncode != 0
