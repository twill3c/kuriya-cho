// 架空の一皿の生成器(F-09)。pipeline/generator.py と**同じ結果を返す**実装。
//
// 浮動小数点を使わない。乱数は 32 ビット整数だけの mulberry32、重みは整数の冪で、
// 候補の並びは Python 側が JSON に書いた順(出現数の降順 → 表記の昇順)をそのまま使う。
// 二実装照合(T-152)が「だいたい一致」ではなく完全一致を要求できるのはこのためである。

const BEGIN = '';
const END = '';
const MAX_TOKENS = 12;

export function mulberry32(seed) {
  let state = seed >>> 0;
  return function next() {
    state = (state + 0x6d2b79f5) >>> 0;
    let z = state;
    z = Math.imul(z ^ (z >>> 15), z | 1) >>> 0;
    z = (z + (Math.imul(z ^ (z >>> 7), z | 61) >>> 0)) >>> 0;
    return (z ^ (z >>> 14)) >>> 0;
  };
}

function pick(cands, power, draw) {
  const weights = cands.map(([, n]) => (power === 0 ? 1 : Math.pow(n, power)));
  let total = 0;
  for (const w of weights) total += w;
  let x = draw % total;
  for (let i = 0; i < cands.length; i += 1) {
    if (x < weights[i]) return cands[i][0];
    x -= weights[i];
  }
  return cands[cands.length - 1][0];
}

export function generate(model, kind, step, seed) {
  const chain = model.kinds[kind].chain;
  const power = model.steps[step];
  const rnd = mulberry32(seed);
  const out = [];
  let state = BEGIN;
  for (let i = 0; i < MAX_TOKENS; i += 1) {
    const cands = chain[state];
    if (!cands || cands.length === 0) break;
    const tok = pick(cands, power, rnd());
    if (tok === END) break;
    out.push(tok);
    state = tok;
  }
  return out.join(' ');
}

// 本書に実在する表題かどうか。**生成のときは参照しない**(測ってから弾く)
export function normalizeTitle(title) {
  return title
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')  // 結合分音記号
    .replace(/œ/g, 'oe')
    .replace(/æ/g, 'ae')
    .replace(/’/g, "'")
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function isInTheBook(model, title) {
  return model.real_titles.includes(normalizeTitle(title));
}
