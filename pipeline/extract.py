"""材料・道具・分量・火・工程を見分ける(F-05)。

画面では「材料と手順を色分け」としか言わない。中でやっているのは**辞書と規則**であって、
学習された何かではない。そのことは「仕組みを見る」に書く。

## 語彙をどう決めたか

レシピ本文 628 件・76,814 語を頻度順に並べ、上位 400 語を目で分類した(2026-09-05)。
思いつきで書いた語を並べたのではなく、**この本に実際に出る語**から採っている。
分類の判断はここに残す:

- **工程**は形で取れる。フランス語の命令形(二人称複数)は `-ez` で終わる。
  本文には `-ez` の語が異なり 411・延べ 8,025 ある。動詞でない `-ez`(`assez` `nez` `chez`)は
  数えるほどしかないので、除外表で押さえる。不定詞(`cuire` `réduire` `servir`)は表で持つ
- **分量**は数詞・数字と単位語の組で取る。単位語は当時のもの(`livre` `once` `gros` `setier`
  `pouce`)を含む。**換算はしない** —— `verre` も `cuillerée` も年代と地域で幅があるので、
  断定できる値が無い(SPEC §6)
- **材料・道具・火**は表である。表を作った以上、**取りこぼしを数える**のが仕事になる(G-06)

## 何を測るか(G-06)

- 全レシピに材料と工程のスパンが 1 つ以上付くこと。付かないレシピは列挙できること
- 本文の語のうち、どれかのスパンに入った割合(被覆率)。**上げることが目的ではない** ——
  接続詞や代名詞に色を付けても読みやすくならない。被覆率は「表がどれだけ薄いか」の目安として出す
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.tokenize_fr import WORD_RE, deligature

CATEGORIES = ("ingredient", "vessel", "quantity", "heat", "action")

CATEGORY_LABEL = {
    "ingredient": "材料",
    "vessel": "道具",
    "quantity": "分量",
    "heat": "火",
    "action": "工程",
}

# --- 表 -----------------------------------------------------------------------

# 材料。単複・性の違いは末尾の s / x を落として照合する
INGREDIENTS = """
beurre sel lard lardons bardes poivre persil oignon ciboule ciboulette echalote échalote ail
truffe champignon carotte navet laurier thym basilic estragon cerfeuil ciboules muscade girofle
clou epice épice safran cannelle macis piment poivrade
citron orange verjus vinaigre vin madere madère champagne malaga eau lait creme crème fromage
oeuf jaune blanc farine pain mie croute croûte pate pâte riz vermicelle macaroni semoule sagou
sucre miel amande pistache marron noix noisette raisin pomme poire cerise abricot pruneau
groseille framboise ananas peche pêche orange truffe
huile graisse saindoux moelle gelee gelée aspic glace roux coulis veloute velouté espagnole
bechamelle béchamelle allemande ravigote mirepoix salpicon farce quenelle godiveau duxelles
boeuf bœuf veau mouton agneau cochon porc jambon sanglier chevreuil daim lievre lièvre lapereau
lapin faisan perdrix perdreau becasse bécasse becassine bécassine pluvier grive caille mauviette
alouette ortolan pigeon ramier tourtereau volaille poulet poularde chapon dinde dindon oie oison
canard caneton sarcelle poule coq
carpe brochet saumon truite sole maquereau merlan anguille turbot cabillaud morue hareng
ecrevisse écrevisse huitre huître anchois cape câpre cornichon olive
pois lentille haricot feve fève chou choufleur laitue chicoree chicorée epinard épinard oseille
concombre artichaut asperge betterave celeri céleri cresson champignon truffe morille mousseron
tomate pomme-de-terre panais poireau cardon salsifis topinambour
bouillon consomme consommé jus blond fumet court-bouillon marinade
ris fraise tetine tétine cervelle langue palais oreille pied queue aile aileron cuisse foie
gesier gésier crete crête rognon animelle
""".split()

# 道具・器
VESSELS = """
casserole marmite sauteuse poele poêle poelon poêlon braisiere braisière daubiere daubière
terrine tourtiere tourtière lechefrite lèchefrite bassine chaudron pot vase moule timbale
plat assiette plafond tamis etamine étamine passoire chinois ecumoire écumoire cuiller cuillere
cuillère fourchette couteau hachoir mortier pilon rouleau coupe-pate coupe-pâte doroir
broche brochette hatelet hâtelet attelet lardoire ficelle soie linge papier couvercle
""".split()

# 火まわり
HEAT = """
feu four fourneau braise braises cendre cendres charbon rechaud réchaud bain-marie ebullition
ébullition fournaise
""".split()

# 単位。**換算しない**(SPEC §6)
UNITS = """
livre livres once onces gros grain grains pincee pincée pincees pincées verre verres setier
litre litres pinte pintes chopine quart quarts quarteron cuilleree cuillerée cuillerees cuillerées
cuiller poignee poignée douzaine douzaines cent pouce pouces ligne lignes doigt doigts tasse
demi demie morceau morceaux tranche tranches lame lames feuille feuilles gousse gousses
""".split()

NUMERALS = """
un une deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize
vingt trente quarante cinquante soixante cent mille demi moitie moitié quart tiers
""".split()

# 不定詞で出る工程語(命令形は -ez で形から取れる)
ACTION_INFINITIVES = """
cuire reduire réduire servir bouillir blanchir refroidir degraisser dégraisser mijoter frire
fondre degorger dégorger dresser passer couper hacher piler mouiller lier braiser rotir rôtir
saisir tremper mariner farcir larder barder glacer paner sauter etuver étuver pocher clarifier
tamiser vanner monter tourner remuer melanger mélanger assaisonner parer flamber ficeler
""".split()

# `-ez` で終わるが動詞でない語(実測 2026-09-05: 本文に出るのはこの 3 語だけ)
NOT_VERBS_EZ = {"assez", "nez", "chez"}


def _norm(word: str) -> str:
    """照合用の形。合字を開き、末尾の s / x を落とす。"""
    w = deligature(word.lower()).replace("’", "'")
    if len(w) > 3 and w[-1] in "sx":
        w = w[:-1]
    return w


def _table(words: list[str]) -> frozenset[str]:
    return frozenset(_norm(w) for w in words)


ING_SET = _table(INGREDIENTS)
VESSEL_SET = _table(VESSELS)
HEAT_SET = _table(HEAT)
UNIT_SET = _table(UNITS)
NUM_SET = _table(NUMERALS)
INF_SET = _table(ACTION_INFINITIVES)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    category: str
    text: str


_NUMBER = re.compile(r"\d+(?:\s*[/⁄]\s*\d+)?")


def _category(word: str) -> str | None:
    w = _norm(word)
    if w in UNIT_SET or w in NUM_SET:
        return "quantity"
    if w in HEAT_SET:
        return "heat"
    if w in VESSEL_SET:
        return "vessel"
    if w in ING_SET:
        return "ingredient"
    if w in INF_SET:
        return "action"
    low = word.lower()
    if low.endswith("ez") and low not in NOT_VERBS_EZ and len(low) > 3:
        return "action"
    return None


def extract(text: str) -> list[Span]:
    """文字位置つきのスパンを返す。原文の文字は一切変えない。"""
    spans: list[Span] = []
    for m in _NUMBER.finditer(text):
        spans.append(Span(m.start(), m.end(), "quantity", m.group()))
    for m in WORD_RE.finditer(text):
        # `mettez-les` は動詞側だけに色を付ける(接語は色を持たない)
        surface = m.group()
        head = surface.split("-")[0].split("’")[-1].split("'")[-1]
        offset = surface.find(head)
        cat = _category(head)
        if cat is None:
            continue
        start = m.start() + offset
        spans.append(Span(start, start + len(head), cat, head))
    spans.sort(key=lambda s: (s.start, s.end))
    # 数字と語が重なることは無いが、念のため重なりを落とす
    out: list[Span] = []
    for s in spans:
        if out and s.start < out[-1].end:
            continue
        out.append(s)
    return out


def coverage() -> dict[str, object]:
    """G-06。レシピごとに材料と工程のスパンが付いているかを数える。"""
    from pipeline.pg_parse import parse_sections

    recipes = [r for s in parse_sections() for r in s.recipes]
    per_cat: dict[str, int] = {c: 0 for c in CATEGORIES}
    missing_ing: list[str] = []
    missing_act: list[str] = []
    words = 0
    tagged = 0
    for r in recipes:
        spans = extract(r.text)
        cats = {s.category for s in spans}
        for c in cats:
            per_cat[c] += 1
        if "ingredient" not in cats:
            missing_ing.append(r.rid)
        if "action" not in cats:
            missing_act.append(r.rid)
        words += len(WORD_RE.findall(r.text))
        tagged += sum(1 for s in spans if s.category != "quantity" or not s.text.isdigit())
    return {
        "recipes": len(recipes),
        "with_category": per_cat,
        "missing_ingredient": missing_ing,
        "missing_action": missing_act,
        "words": words,
        "tagged": tagged,
        "word_coverage": tagged / words if words else 0.0,
    }


if __name__ == "__main__":
    c = coverage()
    print(f"レシピ {c['recipes']}")
    for cat in CATEGORIES:
        n = c["with_category"][cat]  # type: ignore[index]
        print(f"  {CATEGORY_LABEL[cat]}({cat}) が付いたレシピ: {n} / {c['recipes']}")
    print(f"材料が付かないレシピ: {len(c['missing_ingredient'])}  {c['missing_ingredient'][:10]}")  # type: ignore[arg-type]
    print(f"工程が付かないレシピ: {len(c['missing_action'])}  {c['missing_action'][:10]}")  # type: ignore[arg-type]
    print(f"語の被覆: {c['tagged']:,} / {c['words']:,} = {c['word_coverage']:.2%}")
