/* Interface do site. Sem frameworks: estado simples + render por visão. */
(function () {
  "use strict";
  const eng = new Engine(window.AERO_DATA);
  const { fmt, pct, median, isNum } = Engine;
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const SERIES = ["var(--c-team)", "var(--c-top5)", "var(--c-champ)", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];
  const STATUS = { forte: "✔ Forte", "atenção": "▲ Atenção", "crítico": "✖ Crítico" };
  const VIEWS = ["equipe", "comparar", "ranking", "historico", "prioridades", "metodo"];

  const store = {
    get(k, d) { try { const v = localStorage.getItem("aero:" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("aero:" + k, JSON.stringify(v)); } catch (e) { /* sem armazenamento */ } },
  };

  const teams = eng.teams();
  const teamByKey = Object.fromEntries(teams.map((t) => [t.key, t]));
  const latest = eng.years[eng.years.length - 1];
  const S = {
    team: store.get("team", teamByKey.megazord ? "megazord" : teams[0].key),
    year: null, compare: store.get("compare", null), crit: "notas_rel_apres", rankYear: latest,
    sort: { col: "pos", dir: 1 }, effort: {}, histCrit: "notas_rel_apres",
  };
  if (!teamByKey[S.team]) S.team = teams[0].key;
  const yearsOf = (k) => teamByKey[k].years;
  S.year = store.get("year:" + S.team, yearsOf(S.team).slice(-1)[0]);
  if (!yearsOf(S.team).includes(S.year)) S.year = yearsOf(S.team).slice(-1)[0];

  $("#years-span").textContent = eng.years.join(", ");
  $("#gen").textContent = new Date(eng.meta.generated + "T12:00:00").toLocaleDateString("pt-BR");

  // ------------------------------------------------------------ busca de equipe
  const input = $("#team-search"), list = $("#team-list");
  const norm = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  let active = 0, hits = [];
  function search(q) {
    const n = norm(q).trim();
    hits = !n ? teams.slice() : teams.filter((t) => norm(t.name).includes(n) || norm(t.school).includes(n) || norm(t.key).includes(n) || norm(t.uf) === n);
    hits.sort((a, b) => (norm(a.name).startsWith(n) ? 0 : 1) - (norm(b.name).startsWith(n) ? 0 : 1) || a.best - b.best);
    hits = hits.slice(0, 40); active = 0;
    list.innerHTML = hits.length ? hits.map((t, i) => `<li role="option" id="opt-${i}" data-k="${esc(t.key)}" aria-selected="${i === 0}">
      <b>${esc(t.name)}</b><span>${esc(t.school)} · ${esc(t.uf || "—")} · ${t.years.map((y) => `${y}: ${eng.row(y, t.key).pos}º`).join(" · ")}</span></li>`).join("")
      : `<li aria-disabled="true"><span>Nenhuma equipe encontrada. Tente parte do nome ou a sigla da universidade.</span></li>`;
    list.hidden = false; input.setAttribute("aria-expanded", "true");
  }
  function choose(k, y) {
    if (!k) return;
    S.team = k; S.year = y || store.get("year:" + k, yearsOf(k).slice(-1)[0]);
    if (!yearsOf(k).includes(S.year)) S.year = yearsOf(k).slice(-1)[0];
    S.compare = null; store.set("team", k); store.set("compare", null);
    input.value = ""; list.hidden = true; input.setAttribute("aria-expanded", "false"); input.blur();
    render();
  }
  input.addEventListener("input", () => search(input.value));
  input.addEventListener("focus", () => search(input.value));
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    const items = [...list.querySelectorAll("li[data-k]")];
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); active = (active + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items.forEach((li, i) => li.setAttribute("aria-selected", i === active)); items[active]?.scrollIntoView({ block: "nearest" });
      input.setAttribute("aria-activedescendant", "opt-" + active);
    } else if (e.key === "Enter") { e.preventDefault(); choose(items[active]?.dataset.k); }
    else if (e.key === "Escape") { list.hidden = true; input.setAttribute("aria-expanded", "false"); }
  });
  list.addEventListener("mousedown", (e) => { const li = e.target.closest("li[data-k]"); if (li) { e.preventDefault(); choose(li.dataset.k); } });
  document.addEventListener("click", (e) => { if (!e.target.closest(".picker")) { list.hidden = true; input.setAttribute("aria-expanded", "false"); } });

  // ------------------------------------------------------------ tooltip
  const tip = $("#tip");
  document.addEventListener("mouseover", (e) => { const t = e.target.closest("[data-tip]"); if (!t) { tip.hidden = true; return; } tip.textContent = t.dataset.tip; tip.hidden = false; });
  document.addEventListener("mousemove", (e) => { if (tip.hidden) return; const w = tip.offsetWidth; tip.style.left = Math.min(e.clientX + 14, innerWidth - w - 8) + "px"; tip.style.top = e.clientY + 16 + "px"; });
  document.addEventListener("focusin", (e) => { const t = e.target.closest("[data-tip]"); if (t) { const r = t.getBoundingClientRect(); tip.textContent = t.dataset.tip; tip.hidden = false; tip.style.left = r.left + "px"; tip.style.top = r.bottom + 6 + "px"; } });
  document.addEventListener("focusout", () => (tip.hidden = true));

  // ------------------------------------------------------------ componentes
  const pill = (s) => `<span class="pill ${s}">${STATUS[s]}</span>`;
  const kpi = (l, v, s) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s || ""}</div></div>`;
  const signCls = (v) => (v > 0.005 ? "pos" : v < -0.005 ? "neg" : "");
  const LEGEND = `<div class="legend"><span><i class="dot" style="background:var(--c-team)"></i>Equipe</span><span><i style="background:var(--c-top5)"></i>Mediana top-5</span><span><i style="background:var(--c-champ)"></i>Campeão</span><span><i style="background:var(--c-field)"></i>Mediana das equipes com voo</span></div>`;

  function bullet(y, b) {
    const vals = eng.edition(y).map((r) => r[b.field]).filter(isNum);
    let lo = Math.min(...vals, b.team), hi = Math.max(...vals, b.team);
    if (hi - lo < 1e-9) hi = lo + 1;
    const p = (v) => (100 * (v - lo)) / (hi - lo);
    const mk = [[b.flyers, "var(--c-field)", "Mediana das equipes com voo"], [b.top5, "var(--c-top5)", "Mediana top-5"], [b.champion, "var(--c-champ)", "Campeão: " + b.championName]];
    return `<div class="bullet" role="img" aria-label="${esc(`Equipe ${fmt(b.team)}; mediana top-5 ${fmt(b.top5)}; campeão ${fmt(b.champion)}`)}"><div class="track"></div>
      ${mk.map(([v, c, t]) => `<div class="mk" style="left:${p(v)}%;background:${c}"></div><div class="hit" style="left:${p(v)}%" data-tip="${esc(t)}: ${fmt(v)}"></div>`).join("")}
      <div class="me" style="left:${p(b.team)}%"></div><div class="hit" style="left:${p(b.team)}%" data-tip="Equipe: ${fmt(b.team)} (${b.rank}º de ${b.n})"></div></div>
      <div class="scale"><span>${fmt(lo)}</span><span>${fmt(hi)}</span></div>`;
  }

  function card(d) {
    const b = d.bench;
    return `<article class="card ${d.status}">
      <div class="hd"><h3>${esc(d.label)}</h3>${pill(d.status)}</div>
      <div class="val">${fmt(b.team)}</div>
      <div class="sub">${b.rank}º de ${b.n} no critério · top-5 ${fmt(b.top5)} · campeão ${fmt(b.champion)}</div>
      ${bullet(d.year, b)}
      ${d.gain > 0.01 ? `<div class="gain">Atingindo a meta: <b>+${fmt(d.gain)} pts</b> · ${d.gained > 0 ? `<b>+${d.gained}</b> posições (→ ${d.newPos}º)` : "mesma posição"}</div>` : ""}
      <div class="tipbox"><b>Como melhorar:</b> ${esc(d.tip)}</div>
      <details><summary>Evidências, interpretação e fontes</summary><dl>
        <dt>Problema</dt><dd>${esc(d.problem)}</dd>
        <dt>Evidência</dt><dd>${esc(d.evidence)}</dd>
        <dt>Comparação competitiva</dt><dd>${esc(d.competitive)}</dd>
        ${d.interpretation ? `<dt>Interpretação técnica</dt><dd>${esc(d.interpretation)}</dd>` : ""}
        <dt>Recomendação</dt><dd>${esc(d.recommendation)}</dd>
        ${d.hyps.length ? `<dt>Hipóteses a confirmar</dt><dd>${esc(d.hyps.join(" · "))}</dd>` : ""}
        <dt>Confiança: ${d.conf}</dt><dd>${esc(d.confWhy)}.</dd>
        <dd class="refs">Fontes: ${esc(d.refs.join(" · "))}</dd></dl></details>
    </article>`;
  }

  function table(head, rows, opts = {}) {
    return `<div class="tablewrap"${opts.maxh ? ` style="max-height:${opts.maxh}px"` : ""}><table><thead><tr>${head.map((h) => `<th class="${h.n ? "n " : ""}${h.sort ? "sortable" : ""}" ${h.sort ? `data-sort="${h.sort}" tabindex="0" aria-sort="${S.sort.col === h.sort ? (S.sort.dir > 0 ? "ascending" : "descending") : "none"}"` : ""}>${h.t}${S.sort.col === h.sort ? (S.sort.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  }

  // gráfico de linhas (SVG)
  function lineChart({ series, xs, height = 260, reverse = false, yfmt = (v) => fmt(v, 0), title }) {
    const W = 640, H = height, L = 46, R = 16, T = 16, B = 30;
    const all = series.flatMap((s) => s.pts.map((p) => p.y)).filter(isNum);
    let lo = Math.min(...all), hi = Math.max(...all);
    if (!reverse) lo = Math.min(0, lo);
    const pad = (hi - lo) * 0.08 || 1; hi += pad; if (reverse) lo = Math.max(1, lo - pad);
    const X = (x) => L + ((W - L - R) * xs.indexOf(x)) / Math.max(xs.length - 1, 1);
    const Y = (y) => (reverse ? T + ((H - T - B) * (y - lo)) / (hi - lo) : H - B - ((H - T - B) * (y - lo)) / (hi - lo));
    const ticks = 4, tv = [...Array(ticks + 1)].map((_, i) => lo + ((hi - lo) * i) / ticks);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title || "")}">`;
    tv.forEach((v) => (s += `<line class="gridl" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${yfmt(v)}</text>`));
    xs.forEach((x) => (s += `<text x="${X(x)}" y="${H - 8}" text-anchor="middle">${x}</text>`));
    for (const se of series) {
      const pts = se.pts.filter((p) => isNum(p.y) && xs.includes(p.x));
      if (!pts.length) continue;
      s += `<path d="${pts.map((p, i) => `${i ? "L" : "M"}${X(p.x)},${Y(p.y)}`).join("")}" fill="none" stroke="${se.color}" stroke-width="2" ${se.dash ? 'stroke-dasharray="4 4"' : ""}/>`;
      pts.forEach((p, i) => {
        s += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="${se.main ? 5 : 4}" fill="${se.color}" stroke="var(--surface)" stroke-width="2"/>`;
        s += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="12" fill="transparent" data-tip="${esc(`${se.name} · ${p.x}: ${p.label || yfmt(p.y)}`)}"/>`;
        if (se.main && (i === pts.length - 1 || se.labelAll)) s += `<text class="lab" x="${X(p.x)}" y="${Y(p.y) - 10}" text-anchor="middle">${p.label || yfmt(p.y)}</text>`;
      });
    }
    s += `</svg>`;
    const leg = series.length > 1 ? `<div class="legend">${series.map((se) => `<span><i ${se.main ? 'class="dot"' : ""} style="background:${se.color}"></i>${esc(se.name)}</span>`).join("")}</div>` : "";
    return leg + s;
  }

  // ------------------------------------------------------------ identidade
  function renderIdent() {
    const t = teamByKey[S.team], me = eng.row(S.year, S.team);
    $("#ident").innerHTML = `<div><h1>${esc(me.team_name)}</h1><div class="school">${esc(me.school)} · ${esc(me.uf || "—")}</div></div>
      <div class="yearchips" role="group" aria-label="Edição">${t.years.map((y) => { const r = eng.row(y, S.team);
        return `<button class="yearchip" data-year="${y}" aria-pressed="${y === S.year}"><small>${y}</small><b>${r.pos}º<small> /${r.n_equipes}</small></b><small>${fmt(r.total_geral)} pts</small></button>`; }).join("")}</div>`;
    $("#ident").querySelectorAll("[data-year]").forEach((b) => b.addEventListener("click", () => { S.year = +b.dataset.year; store.set("year:" + S.team, S.year); render(); }));
  }

  // ------------------------------------------------------------ visões
  function vEquipe() {
    const me = eng.row(S.year, S.team), pod = eng.podium(S.year, S.team), diags = eng.diagnose(S.year, S.team);
    const lim = eng.limiting(diags), order = { "crítico": 0, "atenção": 1, forte: 2 };
    const sorted = diags.slice().sort((a, b) => order[a.status] - order[b.status] || b.gain - a.gain);
    const reg = eng.reg(S.year);
    return `<section class="kpis">
        ${kpi("Posição", `${me.pos}º`, `de ${me.n_equipes} equipes em ${S.year}`)}
        ${kpi("Pontuação total", fmt(me.total_geral), `${pct(me.pct_campeao, 0)} do campeão`)}
        ${kpi("Faltam para o pódio", me.pos <= 3 ? "no pódio" : "+" + fmt(pod.toPodium), me.pos <= 3 ? "" : `3º: ${esc(pod.third)} (${fmt(pod.thirdTotal)})`)}
        ${kpi("Faltam para o título", me.pos === 1 ? "campeã" : "+" + fmt(pod.toTitle), me.pos === 1 ? "" : esc(pod.champ))}
      </section>
      ${lim.length ? `<section class="section"><h2>Onde a equipe mais perde posições</h2>
        <p class="lead">Simulação: a equipe atinge a meta do critério, as demais ficam como estão.</p>
        <div class="limits">${lim.map((d) => `<div class="limit ${d.status}"><b>${esc(d.label)}</b><span class="g">+${fmt(d.gain)} pts</span><div class="note">${d.gained > 0 ? `+${d.gained} posições (→ ${d.newPos}º)` : "mesma posição"} · confiança ${d.conf}</div></div>`).join("")}</div></section>` : ""}
      <section class="section"><h2>Blocos por categoria · ${S.year}</h2>
        <p class="lead">Cada bloco compara a equipe só com outras equipes da mesma edição. A meta é a mediana do top-5, ou o melhor valor observado quando a equipe já está acima dela.${reg ? "" : " Regulamento desta edição não está no projeto: as interpretações ficam restritas aos dados observados."}</p>
        ${LEGEND}<div class="grid">${sorted.map(card).join("")}</div></section>
      <section class="section"><h2>De onde vem a distância para o 3º colocado</h2>
        ${table([{ t: "Bloco do total" }, { t: "Equipe", n: 1 }, { t: "3º colocado", n: 1 }, { t: "Diferença", n: 1 }, { t: "Mediana top-5", n: 1 }, { t: "Campeão", n: 1 }],
          pod.blocks.map((b) => `<tr><td>${esc(b.label)}</td><td class="n">${fmt(b.team)}</td><td class="n">${fmt(b.third)}</td><td class="n ${signCls(-b.dThird)}">${fmt(b.dThird, 2, true)}</td><td class="n">${fmt(b.top5)}</td><td class="n">${fmt(b.champ)}</td></tr>`)
          .concat([`<tr><td><b>Total</b></td><td class="n"><b>${fmt(pod.total)}</b></td><td class="n"><b>${fmt(pod.thirdTotal)}</b></td><td class="n"><b>${fmt(pod.thirdTotal - pod.total, 2, true)}</b></td><td></td><td class="n"><b>${fmt(pod.champTotal)}</b></td></tr>`]))}
        <p class="note">Total = melhor bateria + confiabilidade + notas + vídeo + penalidades (identidade conferida em todos os PDFs). Diferença positiva = pontos que faltam.</p></section>`;
  }

  function vComparar() {
    const y = S.year, groups = eng.referenceGroups(y, S.team);
    if (!S.compare) S.compare = groups["Top-5"].filter((k) => k !== S.team).slice(0, 4);
    S.compare = S.compare.filter((k) => eng.row(y, k));
    const fields = eng.fieldsInYear(y).filter((f) => f !== "total_melhor_bateria");
    const crit = fields.concat(["total_geral", "carga_paga", "peso_vazio", "ee_calc", "fpv"]).includes(S.crit) ? S.crit : "notas_rel_apres";
    const teamsC = [S.team, ...S.compare];
    const e = eng.edition(y), hib = eng.hib(crit);
    const sortedE = e.filter((r) => isNum(r[crit])).sort((a, b) => (hib ? b[crit] - a[crit] : a[crit] - b[crit]));
    const vals = sortedE.map((r) => r[crit]), lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), span = hi - lo || 1;
    const colorOf = (k) => (k === S.team ? SERIES[0] : S.compare.includes(k) ? SERIES[1 + (S.compare.indexOf(k) % 7)] : "var(--c-field)");
    const bars = sortedE.map((r, i) => {
      const v = r[crit], x0 = (100 * (Math.min(0, v) - lo)) / span, w = (100 * Math.abs(v)) / span, hl = teamsC.includes(r.team_key);
      return `<tr class="click ${r.team_key === S.team ? "me" : ""}" data-k="${esc(r.team_key)}" data-y="${y}"><td class="n">${i + 1}</td><td>${esc(r.team_name)}<div class="note">${esc(r.school).slice(0, 60)}</div></td>
        <td style="width:45%"><div style="position:relative;height:14px"><div data-tip="${esc(r.team_name)}: ${fmt(v)}" style="position:absolute;left:${x0}%;width:${Math.max(w, 0.4)}%;height:14px;border-radius:3px;background:${colorOf(r.team_key)};opacity:${hl ? 1 : 0.45}"></div></div></td>
        <td class="n">${fmt(v)}</td><td class="n">${r.pos}º</td></tr>`;
    });
    const cols = ["total_geral", ...fields];
    const head = [{ t: "Critério" }, ...teamsC.map((k) => ({ t: esc(eng.row(y, k).team_name), n: 1 }))];
    const rows = cols.map((f) => {
      const mv = eng.row(y, S.team)[f];
      return `<tr><td>${esc(eng.label(f))}</td>${teamsC.map((k, i) => { const v = eng.row(y, k)[f], d = (eng.hib(f) ? 1 : -1) * (v - mv);
        return `<td class="n">${fmt(v)}${i ? `<div class="note ${signCls(d)}">${fmt(d, 2, true)}</div>` : ""}</td>`; }).join("")}</tr>`;
    });
    rows.unshift(`<tr><td>Posição geral</td>${teamsC.map((k) => `<td class="n">${eng.row(y, k).pos}º</td>`).join("")}</tr>`);
    const allKeys = e.map((r) => r.team_key).filter((k) => k !== S.team && !S.compare.includes(k));
    return `<section class="section"><h2>Comparar com todas as equipes · ${y}</h2>
        <p class="lead">Escolha um critério para ver a edição inteira ordenada. Clique em qualquer equipe para abrir a análise dela.</p>
        <div class="controls"><label class="ctl" for="crit">Critério<select id="crit">${fields.concat(["total_geral", "carga_paga", "peso_vazio", "ee_calc", "fpv"]).map((f) => `<option value="${f}" ${f === crit ? "selected" : ""}>${esc(eng.label(f))}</option>`).join("")}</select></label></div>
        ${table([{ t: "#", n: 1 }, { t: "Equipe" }, { t: esc(eng.label(crit)) }, { t: "Valor", n: 1 }, { t: "Geral", n: 1 }], bars, { maxh: 520 })}
        ${eng.F[crit] && eng.F[crit].note ? `<p class="note">${esc(eng.F[crit].note)}</p>` : ""}</section>
      <section class="section"><h2>Frente a frente</h2>
        <p class="lead">Sua equipe contra as escolhidas, em todos os critérios. Abaixo de cada valor, a vantagem dessa equipe sobre a sua (verde = ela está à frente).</p>
        <div class="controls">${Object.keys(groups).map((g) => `<button class="btn" data-group="${esc(g)}">${esc(g)}</button>`).join("")}
          <label class="ctl" for="addteam">Adicionar equipe<select id="addteam"><option value="">Escolher…</option>${allKeys.map((k) => `<option value="${esc(k)}">${esc(eng.row(y, k).team_name)}</option>`).join("")}</select></label></div>
        <div class="chips">${S.compare.map((k, i) => `<span class="chip"><i style="background:${SERIES[1 + (i % 7)]}"></i>${esc(eng.row(y, k).team_name)}<button data-rm="${esc(k)}" aria-label="Remover ${esc(eng.row(y, k).team_name)}">×</button></span>`).join("")}</div>
        ${table(head, rows)}</section>`;
  }

  function vRanking() {
    const y = S.rankYear, e = eng.edition(y).slice();
    const cols = [["pos", "Pos", 1], ["team_name", "Equipe", 0], ["school", "Universidade", 0], ["uf", "UF", 0], ["total_geral", "Total", 1], ["total_melhor_bateria", "Melhor bateria", 1],
      ["notas_rel_apres", "Notas", 1], ["pontos_voo", "Voo", 1], ["pontos_acurac", "Acurácia", 1], ["pontos_confiab", "Confiab.", 1], ["total_video", "Vídeo", 1],
      ["carga_paga", "CP (kg)", 1], ["peso_vazio", "PV (kg)", 1], ["ee_calc", "EE*", 1]];
    const { col, dir } = S.sort;
    e.sort((a, b) => { const va = a[col], vb = b[col]; if (typeof va === "string") return dir * va.localeCompare(vb, "pt-BR"); return dir * ((isNum(va) ? va : -1e9) - (isNum(vb) ? vb : -1e9)); });
    return `<section class="section"><h2>Ranking completo</h2>
      <div class="controls"><div class="chips" role="group" aria-label="Edição">${eng.years.map((yy) => `<button class="btn" data-ry="${yy}" aria-pressed="${yy === y}">${yy}</button>`).join("")}</div></div>
      <p class="lead">Clique no cabeçalho para ordenar e numa linha para abrir a equipe. ${eng.edition(y).length} equipes; ${eng.edition(y).filter((r) => r.voou).length} com voo registrado.</p>
      ${table(cols.map(([k, t, n]) => ({ t, n, sort: k })), e.map((r) => `<tr class="click ${r.team_key === S.team ? "me" : ""}" data-k="${esc(r.team_key)}" data-y="${y}">${cols.map(([k, , n]) =>
        `<td class="${n ? "n" : ""}">${k === "pos" ? r.pos + "º" : n ? fmt(r[k], k === "ee_calc" ? 2 : k.includes("carga") || k.includes("peso") ? 3 : 2) : esc(k === "school" ? String(r[k]).slice(0, 48) : r[k])}</td>`).join("")}</tr>`), { maxh: 640 })}
      <p class="note">*EE = CP/PV, calculada aqui a partir das colunas oficiais. Fonte: ${esc(eng.edition(y)[0].source_file)}.</p></section>`;
  }

  function vHistorico() {
    const h = eng.history(S.team), xs = eng.years, sm = eng.editionSummary();
    const total = lineChart({ xs, title: "Pontuação total por edição", series: [
      { name: h[0].team_name, color: "var(--c-team)", main: true, pts: h.map((r) => ({ x: r.year, y: r.total_geral, label: fmt(r.total_geral) })) },
      { name: "Campeão", color: "var(--c-champ)", pts: sm.map((s) => ({ x: s.year, y: s.champTotal })) },
      { name: "Mediana top-5", color: "var(--c-top5)", pts: sm.map((s) => ({ x: s.year, y: s.top5 })) },
      { name: "Média geral", color: "var(--c-field)", dash: true, pts: sm.map((s) => ({ x: s.year, y: s.mean })) }] });
    const posC = lineChart({ xs, reverse: true, title: "Posição por edição", yfmt: (v) => fmt(v, 0) + "º", series: [
      { name: "Posição", color: "var(--c-team)", main: true, labelAll: true, pts: h.map((r) => ({ x: r.year, y: r.pos, label: `${r.pos}º/${r.n_equipes}` })) }] });
    const crits = eng.meta.dashboard.filter((c) => !eng.meta.penalties.includes(c));
    const heat = crits.map((c) => {
      const rs = eng.relativeSeries(S.team, c);
      if (!rs.length) return "";
      return `<tr><td>${esc(eng.label(c))}</td>${xs.map((y) => { const r = rs.find((q) => q.year === y);
        if (!r || !isNum(r.rel)) return `<td class="c" style="color:var(--muted)">—</td>`;
        const v = Math.max(0, Math.min(1.5, r.rel)), bg = v < 1 ? `color-mix(in srgb, var(--crit) ${Math.round((1 - v) * 85)}%, var(--surface))` : `color-mix(in srgb, var(--c-team) ${Math.round((v - 1) * 2 * 70)}%, var(--surface))`;
        return `<td class="c" style="background:${bg}" data-tip="${esc(`${y}: equipe ${fmt(r.team)} · mediana top-5 ${fmt(r.top5)} · ${r.rank}º de ${r.n}`)}">${pct(r.rel, 0)}</td>`; }).join("")}</tr>`;
    }).join("");
    const opts = eng.meta.dashboard.concat(["carga_paga", "peso_vazio", "ee_calc", "fpv"]);
    const hc = opts.includes(S.histCrit) ? S.histCrit : "notas_rel_apres";
    const series = [["Equipe", "var(--c-team)", (y) => eng.row(y, S.team)?.[hc], true], ["Mediana top-5", "var(--c-top5)", (y) => median(eng.top(y, 5).map((r) => r[hc]))],
      ["Campeão", "var(--c-champ)", (y) => eng.edition(y)[0][hc]], ["Mediana com voo", "var(--c-field)", (y) => median(eng.edition(y).filter((r) => r.voou).map((r) => r[hc])), false, true]]
      .map(([name, color, fn, main, dash]) => ({ name, color, main, dash, pts: xs.map((y) => ({ x: y, y: fn(y) })).filter((p) => (main ? h.some((r) => r.year === p.x) : true)) }));
    return `<section class="two"><div class="panel"><h3>Pontuação total</h3>${total}</div><div class="panel"><h3>Classificação</h3>${posC}</div></section>
      <p class="note">Pontos totais não são estritamente comparáveis entre anos porque fórmulas e pesos mudam; compare a distância para as referências de cada edição.</p>
      <section class="section"><h2>Desempenho relativo por critério</h2>
        <p class="lead">Valor da equipe dividido pela mediana do top-5 da mesma edição. 100% = igual à referência. É a forma justa de comparar anos diferentes.</p>
        <div class="tablewrap heat"><table><thead><tr><th>Critério</th>${xs.map((y) => `<th class="n">${y}</th>`).join("")}</tr></thead><tbody>${heat}</tbody></table></div>
        <p class="note">Vermelho = abaixo da referência, azul = acima. “—” = equipe ausente ou mediana do top-5 igual a zero.</p></section>
      <section class="section"><h2>Um critério ao longo das edições</h2>
        <div class="controls"><label class="ctl" for="hcrit">Critério<select id="hcrit">${opts.map((f) => `<option value="${f}" ${f === hc ? "selected" : ""}>${esc(eng.label(f))}</option>`).join("")}</select></label></div>
        <div class="panel">${lineChart({ xs, series, yfmt: (v) => fmt(v, hc === "fpv" ? 3 : hc === "ee_calc" || hc.includes("peso") || hc.includes("carga") ? 2 : 0), title: eng.label(hc) })}</div>
        ${hc === "pontos_voo" || hc === "total_melhor_bateria" ? `<div class="warnbox">A fórmula de pontos de voo mudou (carga em 2022–2024, eficiência estrutural em 2026). Compare a distância para as referências, não o valor absoluto.</div>` : ""}</section>`;
  }

  function vPrioridades() {
    const me = eng.row(S.year, S.team), prio = eng.priorities(S.year, S.team, S.effort);
    if (!prio.length) return `<section class="section"><h2>Prioridades</h2><p class="lead">Nenhum critério abaixo da referência nesta edição.</p></section>`;
    const all = eng.simulate(S.year, S.team, Object.fromEntries(prio.map((p) => [p.field, p.meta])));
    const W = 1000, H = 380, L = 50, R = 30, T = 26, B = 44, gmax = Math.max(...prio.map((p) => p.gain)) * 1.15;
    const X = (v) => L + (W - L - R) * v, Y = (v) => H - B - ((H - T - B) * v) / gmax;
    let sc = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Ganho potencial versus facilidade">`;
    for (let i = 0; i <= 4; i++) { const v = (gmax * i) / 4; sc += `<line class="gridl" x1="${L}" x2="${W - R}" y1="${Y(v)}" y2="${Y(v)}"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fmt(v, 0)}</text>`; }
    [0, 0.25, 0.5, 0.75, 1].forEach((v) => (sc += `<text x="${X(v)}" y="${H - 22}" text-anchor="middle">${fmt(v, 2)}</text>`));
    sc += `<text x="${(W + L) / 2}" y="${H - 4}" text-anchor="middle">facilidade estimada (0 = difícil, 1 = fácil)</text>`;
    prio.forEach((p, i) => { const r = Math.min(22, 7 + 2 * Math.max(0, p.gained));
      sc += `<circle cx="${X(p.ease)}" cy="${Y(p.gain)}" r="${r}" fill="var(--c-team)" fill-opacity=".85" stroke="var(--surface)" stroke-width="2" data-tip="${esc(`${p.label}: +${fmt(p.gain)} pts, +${p.gained} posições · esforço ${p.esforco}, custo ${p.custo}, risco ${p.risco}`)}"/>
        <text class="lab" x="${X(p.ease)}" y="${Y(p.gain) + (i % 2 ? r + 13 : -r - 5)}" text-anchor="${p.ease > 0.85 ? "end" : p.ease < 0.15 ? "start" : "middle"}">${esc(p.label)}</text>`; });
    sc += `</svg>`;
    const md = reportMd(me, prio, all);
    return `<section class="section"><h2>Matriz de priorização · ${S.year}</h2>
        <p class="lead">Ganho, posições e recorrência vêm dos resultados. Esforço, custo e risco (1 = baixo, 5 = alto) são estimativas: ajuste aos números da sua equipe e a ordem é recalculada.</p>
        ${table([{ t: "#", n: 1 }, { t: "Critério" }, { t: "Atual", n: 1 }, { t: "Meta", n: 1 }, { t: "Ganho (pts)", n: 1 }, { t: "Posições", n: 1 }, { t: "Recorrência", n: 1 }, { t: "Esforço", n: 1 }, { t: "Custo", n: 1 }, { t: "Risco", n: 1 }, { t: "Prazo" }, { t: "Disciplinas" }, { t: "Confiança" }],
          prio.map((p) => `<tr><td class="n">${p.priority}</td><td>${esc(p.label)} ${pill(p.status)}</td><td class="n">${fmt(p.current)}</td><td class="n" data-tip="${esc(p.metaSrc)}">${fmt(p.meta)}</td><td class="n"><b>+${fmt(p.gain)}</b></td><td class="n">${p.gained > 0 ? "+" + p.gained : "0"}</td><td class="n">${pct(p.rec, 0)}</td>
            ${["esforco", "custo", "risco"].map((k) => `<td class="n"><input type="number" min="1" max="5" step="1" value="${p[k]}" data-eff="${p.field}" data-k="${k}" id="eff-${p.field}-${k}" aria-label="${k} de ${esc(p.label)}" style="width:56px"></td>`).join("")}
            <td>${esc(p.prazo)}</td><td class="wrap">${esc(p.disciplinas)}</td><td><span class="conf">${p.conf}</span></td></tr>`))}
        <div class="panel"><h3>Retorno × facilidade</h3><p class="note">Tamanho do círculo = posições ganhas.</p>${sc}</div>
        <div class="warnbox">Se todas as metas fossem atingidas, com as demais equipes iguais: <b>${fmt(all.total)} pts → ${all.newPos}º lugar</b>. É um teto de cenário, não uma previsão.</div></section>
      <section class="section"><h2>Relatório para a equipe</h2>
        <p class="lead">Texto em Markdown com metas, evidências e fontes. Copie e cole no Notion, Drive ou no repositório da equipe.</p>
        <div class="controls"><button class="btn primary" id="copy-md">Copiar relatório</button><span class="note" id="copy-ok" aria-live="polite"></span></div>
        <textarea id="md" readonly>${esc(md)}</textarea></section>`;
  }

  function reportMd(me, prio, all) {
    const diags = eng.diagnose(S.year, S.team), pod = eng.podium(S.year, S.team), L = [];
    L.push(`# ${me.team_name} — diagnóstico ${S.year}`, "", `${me.school} (${me.uf}) · ${me.pos}º de ${me.n_equipes} · ${fmt(me.total_geral)} pts · fonte: ${me.source_file}`, "");
    if (me.pos > 3) L.push(`Faltam ${fmt(pod.toPodium)} pts para o pódio (3º: ${pod.third}, ${fmt(pod.thirdTotal)}).`, "");
    L.push("## Prioridades", "", "| # | Critério | Atual | Meta | Ganho | Posições |", "|---|---|---|---|---|---|");
    prio.forEach((p) => L.push(`| ${p.priority} | ${p.label} | ${fmt(p.current)} | ${fmt(p.meta)} (${p.metaSrc}) | +${fmt(p.gain)} | ${p.gained > 0 ? "+" + p.gained : 0} |`));
    L.push("", `Cenário com todas as metas: ${fmt(all.total)} pts → ${all.newPos}º (demais equipes fixas).`, "", "## Diagnóstico por critério", "");
    diags.sort((a, b) => b.gain - a.gain).forEach((d) => {
      L.push(`### ${d.label} — ${d.status}`, "", `- ${d.problem}`, `- ${d.evidence}`, `- ${d.competitive}`);
      if (d.interpretation) L.push(`- Interpretação: ${d.interpretation}`);
      L.push(`- Recomendação: ${d.recommendation}`, `- Confiança: ${d.conf} (${d.confWhy})`, `- Fontes: ${d.refs.join(" | ")}`, "");
    });
    L.push("Esforço, custo e risco são estimativas; ganhos simulados supõem as demais equipes constantes.");
    return L.join("\n");
  }

  function vMetodo() {
    const ed = eng.meta.editions, regs = Object.entries(eng.meta.regulations);
    return `<section class="section"><h2>Como os números são calculados</h2>
      <div class="panel"><p><b>Fonte única:</b> os PDFs oficiais de pontuação final da Classe Regular. Nenhuma nota é estimada ou preenchida. As outras classes (Advanced, Micro) são recusadas na importação.</p>
      <p><b>Metas:</b> sempre tiradas de outras equipes da mesma edição: mediana das 5 primeiras colocadas ou o melhor valor observado. Os ganhos de posição vêm de recalcular o total da equipe e reordenar a edição com as demais equipes fixas.</p>
      <p><b>Entre anos:</b> as fórmulas mudam (a coluna de pontos de carga vale 12,5 × CP em 2022–2024 e 50 × EE em 2026), por isso as comparações entre edições usam posição relativa, nunca pontos brutos.</p>
      <p><b>Interpretações técnicas</b> (erro de previsão de peso vazio, erro de carga, efeito do relatório no voo, configuração provável) só usam as fórmulas do regulamento da própria edição e aparecem com grau de confiança: Alta (dado oficial), Média (derivado por fórmula), Baixa (hipótese).</p></div>
      <h3>Edições na base</h3>
      ${table([{ t: "Ano" }, { t: "Competição" }, { t: "Arquivo" }, { t: "Equipes", n: 1 }, { t: "Coluna de carga" }], ed.map((e) => `<tr><td>${e.year}</td><td>${e.edition_no}ª</td><td>${esc(e.file)}</td><td class="n">${eng.edition(e.year).length}</td><td>${e.regime === "50xEE" ? "50 × EE" : "12,5 × CP"}</td></tr>`))}
      <h3>Regulamentos usados</h3>
      ${regs.map(([y, r]) => `<p><b>${y}</b>: ${esc(r.file)} (${esc(r.revision)})</p>${table([{ t: "Item" }, { t: "Referência" }], Object.entries(r.refs).map(([k, v]) => `<tr><td>${esc(eng.label(k))}</td><td class="wrap">${esc(v)}</td></tr>`))}`).join("")}
      <div class="warnbox">Limitações: faltam os resultados de 2025 e os regulamentos de 2022–2025; relatório e apresentação aparecem somados no PDF; simulações supõem as demais equipes constantes.</div>
      <p class="note">Código aberto: o pacote Python (extração, validação, análise) gera este site estático com <code>python scripts/build_site.py</code>. Os cálculos do navegador são verificados contra o Python em todas as ${eng.rows.length} linhas da base.</p></section>`;
  }

  // ------------------------------------------------------------ render e eventos
  const VIEWFN = { equipe: vEquipe, comparar: vComparar, ranking: vRanking, historico: vHistorico, prioridades: vPrioridades, metodo: vMetodo };
  function currentView() { const h = location.hash.slice(1); return VIEWS.includes(h) ? h : "equipe"; }
  function render() {
    const v = currentView();
    document.querySelectorAll("#tabs a").forEach((a) => a.toggleAttribute("aria-current", a.dataset.view === v) || a.setAttribute("aria-current", a.dataset.view === v ? "page" : "false"));
    document.querySelectorAll("#tabs a").forEach((a) => a.setAttribute("aria-current", a.dataset.view === v ? "page" : "false"));
    renderIdent();
    $("#view").innerHTML = VIEWFN[v]();
    bind();
  }
  function openTeam(k, y) { if (k) { location.hash = "equipe"; choose(k, y ? +y : null); window.scrollTo(0, 0); } }
  function bind() {
    const V = $("#view");
    V.querySelectorAll("tr.click[data-k]").forEach((tr) => tr.addEventListener("click", () => openTeam(tr.dataset.k, tr.dataset.y)));
    $("#crit")?.addEventListener("change", (e) => { S.crit = e.target.value; render(); });
    $("#hcrit")?.addEventListener("change", (e) => { S.histCrit = e.target.value; render(); });
    $("#addteam")?.addEventListener("change", (e) => { if (e.target.value) { S.compare.push(e.target.value); store.set("compare", S.compare); render(); } });
    V.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { S.compare = S.compare.filter((k) => k !== b.dataset.rm); store.set("compare", S.compare); render(); }));
    V.querySelectorAll("[data-group]").forEach((b) => b.addEventListener("click", () => { S.compare = eng.referenceGroups(S.year, S.team)[b.dataset.group].filter((k) => k !== S.team).slice(0, 7); store.set("compare", S.compare); render(); }));
    V.querySelectorAll("[data-ry]").forEach((b) => b.addEventListener("click", () => { S.rankYear = +b.dataset.ry; render(); }));
    V.querySelectorAll("th[data-sort]").forEach((th) => { const go = () => { const c = th.dataset.sort; S.sort = { col: c, dir: S.sort.col === c ? -S.sort.dir : (["pos", "team_name", "school", "uf", "peso_vazio"].includes(c) ? 1 : -1) }; render(); };
      th.addEventListener("click", go); th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }); });
    V.querySelectorAll("input[data-eff]").forEach((inp) => inp.addEventListener("change", () => {
      const f = inp.dataset.eff, base = Object.assign({}, eng.meta.effort[f] || {}, S.effort[f] || {});
      base[inp.dataset.k] = Math.max(1, Math.min(5, Math.round(+inp.value || 3))); S.effort[f] = base; render();
      $(`#eff-${f}-${inp.dataset.k}`)?.focus();
    }));
    $("#copy-md")?.addEventListener("click", async () => {
      const ok = $("#copy-ok");
      try { await navigator.clipboard.writeText($("#md").value); ok.textContent = "Copiado."; }
      catch (e) { $("#md").select(); ok.textContent = "Texto selecionado: use Ctrl+C / Cmd+C."; }
    });
  }
  window.addEventListener("hashchange", render);
  render();
})();
