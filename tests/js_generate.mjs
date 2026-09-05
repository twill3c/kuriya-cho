// 二実装照合(T-152)のための JavaScript 側の出口。
//
//   node tests/js_generate.mjs titles <kind> <step> <count>
//   node tests/js_generate.mjs draws <seed> <count>
//
// 前者は生成した料理名、後者は乱数の**生の出目**を JSON で出す。
// 結論(料理名)だけでなく経路(出目)も比べるのは、別々の理由で同じ答えに
// 着いたときに照合が黙って通るのを防ぐため(HC-065)。

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { generate, mulberry32 } from '../web/js/generator.js';

const here = dirname(fileURLToPath(import.meta.url));
const [mode, a, b, c] = process.argv.slice(2);

if (mode === 'draws') {
  const rnd = mulberry32(Number(a));
  const out = [];
  for (let i = 0; i < Number(b); i += 1) out.push(rnd());
  process.stdout.write(JSON.stringify(out));
} else if (mode === 'titles') {
  const model = JSON.parse(
    readFileSync(join(here, '..', 'web', 'data', 'generator.json'), 'utf8'),
  );
  const out = [];
  for (let seed = 0; seed < Number(c); seed += 1) {
    out.push(generate(model, a, Number(b), seed));
  }
  process.stdout.write(JSON.stringify(out));
} else {
  process.stderr.write('usage: js_generate.mjs titles <kind> <step> <count> | draws <seed> <count>\n');
  process.exit(2);
}
