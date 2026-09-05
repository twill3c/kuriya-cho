// 画面が共通で使う道具。
//
// 原則:
// - **原文の文字を書き換えない。** 色分けも綴りの差分も参照も、すべて文字位置で描く。
//   位置は Python 側(pipeline/build_web.py)が段落ごとに焼き込んでいる
// - 数値(類似度・信頼度)は画面に出さない。出すのは「なぜ出たか」の一行だけ

const cache = new Map();

export async function loadJSON(path) {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(path).then((r) => {
        if (!r.ok) throw new Error(`${path}: ${r.status}`);
        return r.json();
      }),
    );
  }
  return cache.get(path);
}

export const loadIndex = () => loadJSON('data/index.json');
export const loadSearch = () => loadJSON('data/search.json');
export const loadMeta = () => loadJSON('data/meta.json');
export const loadMenus = () => loadJSON('data/menus.json');
export const loadGlossary = () => loadJSON('data/glossary.json');
export const loadSection = (sid) => loadJSON(`data/recipes/${sid}.json`);

export function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

export const CATEGORY_LABEL = {
  ingredient: '材料',
  vessel: '道具',
  quantity: '分量',
  heat: '火',
  action: '工程',
};

// 段落 1 つを描く。marks は {s, e, tag, attrs, text} の配列(重ならないこと)。
function renderMarks(text, marks) {
  const sorted = [...marks].sort((a, b) => a.s - b.s);
  let out = '';
  let pos = 0;
  for (const m of sorted) {
    if (m.s < pos) continue; // 重なりは捨てる(位置の整合は Python 側で保証している)
    out += esc(text.slice(pos, m.s));
    const attrs = Object.entries(m.attrs || {})
      .map(([k, v]) => ` ${k}="${esc(v)}"`)
      .join('');
    out += `<${m.tag}${attrs}>${esc(m.text ?? text.slice(m.s, m.e))}</${m.tag}>`;
    pos = m.e;
  }
  out += esc(text.slice(pos));
  return out;
}

/**
 * レシピ本文を層ごとに描く。
 * layer: 'orig'(1814 年の綴り)/ 'modern'(現代の綴り)/ 'ja'(日本語)
 */
export function renderBody(recipe, layer, { highlight = true } = {}) {
  if (layer === 'ja') {
    if (!recipe.paragraphs_ja || recipe.paragraphs_ja.length === 0) return null;
    return recipe.paragraphs_ja.map((p) => `<p>${esc(p)}</p>`).join('');
  }
  return recipe.paragraphs
    .map((text, i) => {
      const marks = [];
      if (highlight) {
        for (const sp of recipe.spans[i] || []) {
          marks.push({ s: sp.s, e: sp.e, tag: 'mark', attrs: { class: 'sp', 'data-c': sp.c } });
        }
      }
      for (const ref of recipe.refs[i] || []) {
        marks.push({
          s: ref.s,
          e: ref.e,
          tag: 'span',
          attrs:
            ref.to
              ? { class: 'xref', 'data-to': ref.to, title: `${ref.name} へ` }
              : { class: 'xref dead', title: `${ref.name} —— この巻には無い(第二巻の項)` },
          text: ref.name,
        });
      }
      if (layer === 'modern') {
        for (const c of recipe.changes[i] || []) {
          marks.push({
            s: c.s,
            e: c.e,
            tag: 'span',
            attrs: { class: 'chg', title: `${c.old} → ${c.new}` },
            text: c.new,
          });
        }
      }
      // 参照 > 綴りの差分 > 色分け の順で優先し、重なったら後ろを捨てる
      const order = { span: 0, mark: 1 };
      marks.sort((a, b) => a.s - b.s || order[a.tag] - order[b.tag]);
      const kept = [];
      let end = -1;
      for (const m of marks) {
        if (m.s < end) continue;
        kept.push(m);
        end = m.e;
      }
      return `<p>${renderMarks(text, kept)}</p>`;
    })
    .join('');
}

export function cardHTML(r, { why = null } = {}) {
  const badges = [];
  if (r.has_ja) badges.push('<span class="badge ja">和訳あり</span>');
  if (r.ref_only) badges.push('<span class="badge ref">参照だけの項</span>');
  return `
    <div class="fr">${esc(r.title)}</div>
    <div class="ja">${esc(r.title_ja || '')}</div>
    <div class="meta">${badges.join('')}${esc(r.sectionName || '')}</div>
    ${why || ''}`;
}

export function setActiveTab() {
  const here = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('nav.tabs a').forEach((a) => {
    if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page');
  });
}

export function param(name) {
  return new URLSearchParams(location.search).get(name);
}
