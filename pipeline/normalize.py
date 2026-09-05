"""1814 年の綴りを現代綴りへ寄せる(F-04)。

## 測ってから書いた

規則を書く前に、本書の地の文(緒言 + 章の導入 + レシピ本文)の全語を、現代フランス語の
語彙集(Grammalecte/Dicollecte 系 344,060 形)へ当てて、**何がどれだけ違うのか**を数えた。
実測 2026-09-05・照合形 82,987(1 字の断片は除く)。

結果は事前の見込みと違った:

- 語彙集に載らない形は **718 / 82,987 = 0.87%**(異なり 199)しかない
- 正規化を通すと **360 / 83,081 = 0.43%**(異なり 110)。**半分は綴りの問題**だったが、
  残る半分は料理語・地名・複合語という「語彙集の穴」で、直す対象ではない
- 教科書的に語られる **`-oit` / `-ois` の半過去(`étoit` → `était`)は、この本には無い**。
  命令形で書かれた料理書なので、直説法半過去がそもそも出てこない

対照として、**同じジャンル・綴りが現代のもの**であるフランス語料理書
(PG #6966, Auguste Hélie『Traité Général de la Cuisine Maigre』・序文は 1896 年 12 月)を
同じ道具で測った。1835 年の綴り改革より後の本である。それでも語彙集に載らない率は
**998 / 61,440 = 1.62%** で、**1814 年の本の倍近い**。

つまり **「1814 年の綴りが読解の壁である」という前提は、この本については成り立たない**。
語彙集から外れる語の多寡を決めているのは綴りの古さではなく、**料理語と固有名の密度**である。
この測定結果は画面の「仕組みを見る」にそのまま出す。

## 規則と例外辞書を分ける理由

- **規則**は形だけを見る。語彙集を実行時に引かない。引くと「語彙集が受け入れる形に変える」
  ことになり、効きの測定(G-04)が恒等式になる
- **例外辞書**は語ごとの人手の判断である。載せた置換先が現代語彙に実在することは
  テストで確かめる(G-05)

教科書に必ず載る `-ans` → `-ants` を**規則としては書けない**。現代フランス語の語彙集で
`-ans` / `-ens` で終わる 726 語に当てると **723 語が語でなくなる**(`anciens` → `ancients`、
`chrétiens` → `chrétients`)。この本に出るのは 15 語だけなので、閉じた表にした。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.tokenize_fr import CLITICS, ELISION_HEADS, WORD_RE

# --- 規則(形だけを見る。語彙集を引かない)------------------------------------

# `très-fin` → `très fin`。1814 年は très を副詞にハイフンで繋いだ。
# 陰性対照: 現代語彙集に `très-` で始まる語は **0 語**なので、この規則は何も壊さない(実測)
TRES_HYPHEN = re.compile(r"\btrès-(?=[a-zà-ÿ])")

RULES: tuple[tuple[str, re.Pattern[str], str, str], ...] = (
    (
        "tres-hyphen",
        TRES_HYPHEN,
        "très ",
        "副詞 très のハイフンを外す(現代は分かち書き)",
    ),
)

# --- 例外辞書(語ごとの判断)---------------------------------------------------

# 綴りが古い語。置換先はすべて現代フランス語の語彙集に実在する(G-05 で検査)
ARCHAIC: dict[str, str] = {
    # -ans / -ens の複数(1835 年の綴り改革より前の形)
    "ardens": "ardents",
    "changemens": "changements",
    "croissans": "croissants",
    "diamans": "diamants",
    "différens": "différents",
    "excellens": "excellents",
    "inconvéniens": "inconvénients",
    "ingrédiens": "ingrédients",
    "montans": "montants",
    "opulens": "opulents",
    "précédens": "précédents",
    "présens": "présents",
    "raffinemens": "raffinements",
    "restans": "restants",
    "élémens": "éléments",
    # アクセントの違い
    "légérement": "légèrement",
    "légéreté": "légèreté",
    "crême": "crème",
    "crêmes": "crèmes",
    "crêmier": "crémier",
    "pepins": "pépins",
    "tetine": "tétine",
    "tetines": "tétines",
    "otez": "ôtez",
    "ragouts": "ragoûts",
    "echaudez": "échaudez",
    "ecrevisses": "écrevisses",
    "emincez": "émincez",
    "hatelet": "hâtelet",
    "hatelets": "hâtelets",
    "hatelettes": "hâtelettes",
    # 語形の違い
    "alongé": "allongé",
    "alongée": "allongée",
    "alongés": "allongés",
    "alongez": "allongez",
    "employerez": "emploierez",
    "jeterez": "jetterez",
    "ficelerez": "ficellerez",
    "veuilliez": "veuillez",
    "proportionnément": "proportionnellement",
    "abatis": "abattis",
    "outre-passent": "outrepassent",
    # ハイフンの有無
    "long-temps": "longtemps",
    "tout-à-fait": "tout à fait",
    "à-la-fois": "à la fois",
    "dès-lors": "dès lors",
    "bout-à-bout": "bout à bout",
    "à-plomb": "aplomb",
    "chou-croûte": "choucroute",
    "entre-côte": "entrecôte",
    "entre-côtes": "entrecôtes",
    "maître-d'hôtel": "maître d’hôtel",
    "maîtres-d'hôtel": "maîtres d’hôtel",
    "vols-au-vent": "vol-au-vent",
}

# 語彙集に無いが**古い綴りではない**語。直さない。
# 「語彙集に無い = 古い」と決めつけると、料理語と地名をまとめて壊す
NOT_ARCHAIC: dict[str, str] = {
    "kari": "カレー。当時の綴り。料理名として残す",
    "salmi": "サルミ(猟鳥の煮込み)。現代も使う語だが語彙集に無い",
    "béchamelle": "ベシャメル。現代は béchamel だが、当時の女性形も辞書に載る綴りである",
    "mitonnage": "ミトナージュ。本書の用語",
    "empotage": "アンポタージュ。本書の用語",
    "brichet": "鳥の胸骨。専門語",
    "doroir": "ドロワール(卵を塗る刷毛)。専門語",
    "panuffe": "肉の被膜。精肉の専門語",
    "ducelle": "デュクセル(duxelles)の当時の綴り。料理名として残す",
    "gaudiveau": "ゴディヴォー(挽き肉詰め)。当時の綴り",
    "animelles": "羊の睾丸。料理語",
    "bardière": "背脂。精肉語",
    "effondrilles": "澱(おり)。古語だが綴りは現代と同じ",
    "maniveaux": "小籠。専門語",
    "popiettes": "ポピエット(paupiettes)。当時の綴り",
    "sain-doux": "ラード(saindoux)。当時の分かち書き",
    "cochois": "鳩の品種名",
    "vembre": "バターの産地名(beurre de Vembre)",
    "romesteck": "ランプステーキ。英語からの借用の当時の綴り",
    "corne-bif": "コンビーフ。英語からの借用の当時の綴り",
    "demi-": "demi- の複合語は現代でもハイフンで綴る。語彙集が複合語を持たないだけ",
    "voy": "「voyez(〜を見よ)」の略。組版の約物",
}

_LOWER = str.maketrans({"’": "'"})


@dataclass(frozen=True)
class Change:
    start: int
    end: int
    old: str
    new: str
    kind: str  # "rule:<name>" または "lexicon"


def _match_case(old: str, new: str) -> str:
    if old.isupper() and len(old) > 1:
        return new.upper()
    if old[:1].isupper():
        return new[:1].upper() + new[1:]
    return new


_ELISION_PREFIX = re.compile(
    r"^(?:" + "|".join(sorted(ELISION_HEADS, key=len, reverse=True)) + r")[’']",
    re.IGNORECASE,
)
_CLITIC_SUFFIX = re.compile(
    r"(?:-(?:" + "|".join(sorted(CLITICS, key=len, reverse=True)) + r"))+$",
    re.IGNORECASE,
)


def _dictionary_hit(surface: str) -> tuple[int, int, str] | None:
    """語の表層から例外辞書の項目を探す。戻り値は (語内の開始位置, 長さ, 置換先)。

    表層には省略形の頭と接語がくっついてくる(`d’excellens` `alongez-la` `L’entre-côte`)。
    これを剥がさずに辞書を引くと、**辞書に載っているのに直らない**。
    2026-09-05 の実測で 11 件がこれで残っていた。
    """
    off = 0
    body = surface
    m = _ELISION_PREFIX.match(body)
    if m:
        off += m.end()
        body = body[m.end() :]
    for candidate in (body, _CLITIC_SUFFIX.sub("", body)):
        if not candidate:
            continue
        new = ARCHAIC.get(candidate.lower().translate(_LOWER))
        if new is not None:
            return off, len(candidate), new
    return None


def find_changes(text: str) -> list[Change]:
    """原文の文字位置つきで、現代綴りへの置き換えを列挙する。

    テキストを書き換えず**差分だけ**を返すのは、画面が三層(原文 / 現代綴り / 和訳)を
    切り替えながら「どこが変わったか」に下線を引くためである。
    """
    changes: list[Change] = []
    for name, pattern, repl, _note in RULES:
        for m in pattern.finditer(text):
            changes.append(
                Change(m.start(), m.end(), m.group(), repl, f"rule:{name}")
            )
    # 規則が触った範囲の**外側**で語を引く。`très-légérement` のように
    # 規則の対象と例外辞書の対象が一つの語にまたがることがあるので、
    # 語をまるごと除外すると後半の綴りが直らない(2026-09-05 実測で 6 件取り逃していた)
    covered = sorted((c.start, c.end) for c in changes)
    free: list[tuple[int, int]] = []
    pos = 0
    for s, e in covered:
        if s > pos:
            free.append((pos, s))
        pos = max(pos, e)
    free.append((pos, len(text)))

    for lo, hi in free:
        for m in WORD_RE.finditer(text, lo, hi):
            hit = _dictionary_hit(m.group())
            if hit is None:
                continue
            off, length, new = hit
            start = m.start() + off
            old = text[start : start + length]
            changes.append(Change(start, start + length, old, _match_case(old, new), "lexicon"))
    changes.sort(key=lambda c: c.start)
    return changes


def apply_changes(text: str, changes: list[Change]) -> str:
    out: list[str] = []
    pos = 0
    for c in changes:
        out.append(text[pos : c.start])
        out.append(c.new)
        pos = c.end
    out.append(text[pos:])
    return "".join(out)


def modernize(text: str) -> str:
    return apply_changes(text, find_changes(text))
