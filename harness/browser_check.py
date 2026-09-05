"""実ブラウザ検品(G-11 / G-12)。

**テストが緑でも動かないことがある。** モジュールの読み込み、`fetch` のパス、
段組みの溢れ、図の切れ —— どれも静的な検査では緑のまま通る(HC-138 / GEN-LAYOUT)。
ここでは本物の Chromium で各画面を開き、次を測る:

- コンソールのエラーと、失敗したネットワーク要求(ここが赤なら、画面は動いていない)
- **横溢れ**: `documentElement.scrollWidth` が `clientWidth` を超えないこと(G-12)。
  溢れている要素も名指しで出す
- **図の収まり**(G-11): SVG の中の要素が `viewBox` に収まっていること。
  図を持たない画面では対象 0 でよいが、**0 だったことを表示する**(黙って通さない)
- 画面ごとのスクリーンショット(手で見るため)

使い方:

    python harness/browser_check.py                # 既定の 7 画面
    python harness/browser_check.py --shot out/    # 画像も保存する
"""

from __future__ import annotations

import argparse
import http.server
import json
import re
import socketserver
import threading
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

PAGES = (
    "index.html",
    "sagasu.html",
    "yomu.html",
    "taku.html",
    "ami.html",
    "asobu.html",
    "shikumi.html",
)

VIEWPORTS = (("wide", 1280, 900), ("narrow", 390, 780))

# 横溢れの判定。**自前で横スクロールする入れ物の中身は溢れではない** ——
# 表や図は `overflow-x: auto` の中で横に流すのが正しい姿なので、そこを数えると
# 検査が常に赤になり、やがて誰も読まなくなる(2026-09-05 に一度そうなった)
OVERFLOW_JS = """
() => {
  const doc = document.documentElement;
  const over = [];
  const limit = doc.clientWidth + 1;
  const scrolls = (el) => {
    const ov = getComputedStyle(el).overflowX;
    return ov === 'auto' || ov === 'scroll';
  };
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.right <= limit) continue;
    let inScroller = false;
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      if (scrolls(a)) { inScroller = true; break; }
    }
    if (inScroller) continue;
    over.push({ tag: el.tagName, cls: el.className, right: Math.round(r.right),
                text: (el.textContent || '').slice(0, 40) });
  }
  return { scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth, over: over.slice(0, 6) };
}
"""

SVG_JS = """
() => {
  const out = [];
  for (const svg of document.querySelectorAll('svg')) {
    const vb = svg.viewBox && svg.viewBox.baseVal;
    if (!vb || (!vb.width && !vb.height)) continue;
    for (const el of svg.querySelectorAll('text, path, rect, line, circle, g')) {
      let b;
      try { b = el.getBBox(); } catch (e) { continue; }
      if (!b || (b.width === 0 && b.height === 0)) continue;
      if (b.x < vb.x - 0.5 || b.y < vb.y - 0.5 ||
          b.x + b.width > vb.x + vb.width + 0.5 ||
          b.y + b.height > vb.y + vb.height + 0.5) {
        out.push({ tag: el.tagName, text: (el.textContent || '').slice(0, 30),
                   bbox: [b.x, b.y, b.width, b.height],
                   viewBox: [vb.x, vb.y, vb.width, vb.height] });
      }
    }
  }
  return out;
}
"""


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *a):  # 静かにする
        pass


@contextmanager
def serve():
    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            httpd.shutdown()


def check(shot_dir: Path | None = None, pages: tuple[str, ...] = PAGES) -> list[dict]:
    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    with serve() as base, sync_playwright() as p:
        browser = p.chromium.launch()
        for name, width, height in VIEWPORTS:
            ctx = browser.new_context(viewport={"width": width, "height": height})
            for page_name in pages:
                page = ctx.new_page()
                errors: list[str] = []
                page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                        if m.type in ("error", "warning") else None)
                page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                page.on("requestfailed",
                        lambda r: errors.append(f"requestfailed: {r.url} {r.failure}"))
                page.goto(f"{base}/{page_name}", wait_until="networkidle")
                page.wait_for_timeout(400)
                overflow = page.evaluate(OVERFLOW_JS)
                svg = page.evaluate(SVG_JS)
                title = page.title()
                if shot_dir is not None:
                    shot_dir.mkdir(parents=True, exist_ok=True)
                    # 問い合わせつきの URL も検品したいので、ファイル名に使えない字を潰す
                    # (Windows は `?` `=` `&` を受け付けず OSError になる)
                    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", page_name.replace(".html", ""))
                    page.screenshot(path=str(shot_dir / f"{stem}-{name}.png"), full_page=True)
                results.append(
                    {
                        "page": page_name,
                        "viewport": name,
                        "title": title,
                        "errors": errors,
                        "overflow": overflow,
                        "svg_out_of_viewbox": svg,
                    }
                )
                page.close()
            ctx.close()
        browser.close()
    return results


def summarise(results: list[dict]) -> tuple[str, bool]:
    lines = []
    ok = True
    for r in results:
        o = r["overflow"]
        overflowed = o["scrollWidth"] > o["clientWidth"] + 1
        bad = bool(r["errors"]) or overflowed or bool(r["svg_out_of_viewbox"])
        ok = ok and not bad
        flag = "NG" if bad else "ok"
        lines.append(
            f"[{flag}] {r['page']:14s} {r['viewport']:6s} "
            f"scroll {o['scrollWidth']}/{o['clientWidth']}  "
            f"err {len(r['errors'])}  はみ出し {len(o['over'])}  図 {len(r['svg_out_of_viewbox'])}"
        )
        for e in r["errors"][:4]:
            lines.append(f"        ! {e[:160]}")
        for x in o["over"][:4]:
            lines.append(f"        > {x['tag']}.{x['cls']} right={x['right']} {x['text']!r}")
        for x in r["svg_out_of_viewbox"][:3]:
            lines.append(f"        # svg {x['tag']} {x['text']!r} bbox={x['bbox']}")
    return "\n".join(lines), ok


def main() -> int:
    ap = argparse.ArgumentParser(description="実ブラウザ検品")
    ap.add_argument("--shot", type=Path, help="スクリーンショットの保存先")
    ap.add_argument("--json", action="store_true", help="生の結果を JSON で出す")
    args = ap.parse_args()
    results = check(shot_dir=args.shot)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    text, ok = summarise(results)
    print(text)
    print("\n判定:", "合格" if ok else "不合格")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
