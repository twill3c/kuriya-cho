"""消費率の検算(HC-164)。

件数オラクル(目次・数詞)は「いくつ取れたか」を言うが、「**何を取り落としたか**」は言わない。
このループで踏んだ二つの取りこぼしは、どちらも出力の形が最後まで妥当なまま数だけが減る形で出た
(斜体見出しの句点が外にある 2 件・段組みの右列 229 皿)。件数が減っても、
それが「もともとその数だった」のか「取り落とした」のかは件数だけでは区別できない。

消費率は素材だけで計算でき、残差をそのまま列挙できる。原文の各行が

- 空行
- 章見出し / 献立の見出し / 組の見出し
- レシピ見出し
- どれかのレシピ本文・皿の並び

のいずれかに帰属していることを要求し、帰属しなかった行を残差として返す。
"""

from __future__ import annotations

from pipeline import menus as menus_mod
from pipeline import pg_parse


def body_coverage() -> dict[str, object]:
    lines = pg_parse.body_text().split("\n")
    trace: set[int] = set()
    pg_parse.parse_sections(trace=trace)
    residue = [(i, lines[i]) for i in range(len(lines)) if i not in trace]
    return {
        "region": "body",
        "lines": len(lines),
        "consumed": len(trace),
        "rate": len(trace) / len(lines) if lines else 1.0,
        "residue": residue,
    }


def menus_coverage() -> dict[str, object]:
    lines = menus_mod.menus_text().split("\n")
    trace: set[int] = set()
    menus_mod.parse_menus(trace=trace)
    residue = [(i, lines[i]) for i in range(len(lines)) if i not in trace]
    return {
        "region": "menus",
        "lines": len(lines),
        "consumed": len(trace),
        "rate": len(trace) / len(lines) if lines else 1.0,
        "residue": residue,
    }


def report() -> str:
    out = []
    for cov in (body_coverage(), menus_coverage()):
        out.append(
            f"{cov['region']:6s} 行 {cov['lines']:6,d} / 帰属 {cov['consumed']:6,d}"
            f" / 消費率 {cov['rate']:.5f} / 残差 {len(cov['residue'])}"  # type: ignore[arg-type]
        )
        for i, text in cov["residue"][:20]:  # type: ignore[index]
            out.append(f"    {i:6d}  {text!r}")
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
