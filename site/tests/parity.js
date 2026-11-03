// Uso: node site/tests/parity.js data.json  → imprime JSON com números do motor JS
const fs = require("fs");
const Engine = require("../src/engine.js");
const eng = new Engine(JSON.parse(fs.readFileSync(process.argv[2], "utf8")));
const out = [];
for (const y of eng.years) for (const r of eng.edition(y)) {
  const d = eng.diagnose(y, r.team_key).map((x) => [x.field, x.status, x.bench.rank, +x.meta.toFixed(6), +x.gain.toFixed(4), x.gained, x.conf]);
  const p = eng.priorities(y, r.team_key).map((x) => x.field);
  out.push({ year: y, key: r.team_key, podium: +eng.podium(y, r.team_key).toPodium.toFixed(4), d, p });
}
process.stdout.write(JSON.stringify(out));
