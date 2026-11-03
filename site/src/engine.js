/* SAE AeroDesign Intelligence — motor de análise no navegador.
 * Porte de aerointel/analysis.py + aerointel/diagnosis.py (Python é a referência;
 * tests/test_site_parity.py compara os números dos dois).
 * Regras: metas vêm só de outras equipes da mesma edição; fórmulas do regulamento só
 * são usadas na edição a que pertencem.
 */
(function (root) {
  "use strict";

  const EPS = 1e-9;

  // ------------------------------------------------------------ utilidades
  const isNum = (v) => typeof v === "number" && isFinite(v);
  function median(arr) {
    const a = arr.filter(isNum).sort((x, y) => x - y);
    if (!a.length) return NaN;
    const m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }
  const mean = (arr) => { const a = arr.filter(isNum); return a.length ? a.reduce((s, v) => s + v, 0) / a.length : NaN; };
  function std(arr) {
    const a = arr.filter(isNum); if (a.length < 2) return NaN;
    const m = mean(a); return Math.sqrt(a.reduce((s, v) => s + (v - m) ** 2, 0) / (a.length - 1));
  }
  function fmt(x, nd = 2, signed = false) {
    if (!isNum(x)) return "—";
    const s = Math.abs(x).toLocaleString("pt-BR", { minimumFractionDigits: nd, maximumFractionDigits: nd });
    const sign = x < 0 ? "−" : signed ? "+" : "";
    return sign + s;
  }
  const pct = (x, nd = 1, signed = false) => (isNum(x) ? fmt(100 * x, nd, signed) + "%" : "—");
  const v0 = (v) => (isNum(v) ? v : 0);

  // ------------------------------------------------------------ regulamento 2026
  const R26 = {
    fpv: (e) => Math.max(0.8, 1.1 - 15 * e * e),
    pvErrFromFpv: (f) => (!isNum(f) || f <= 0.8001 ? null : Math.sqrt(Math.max(0, (1.1 - f) / 15))),
    pac: (e) => Math.max(0, 30 - 830 * Math.abs(e) ** 1.75),
    cpErrFromPac: (p) => (!isNum(p) || p <= 0 ? null : ((30 - p) / 830) ** (1 / 1.75)),
    fpr: (nr) => Math.min(1, 0.5 + (0.75 * nr) / 185),
    fN: (n) => { n = Math.min(n, 3); return 0.185 * n * n - 0.775 * n + 1.81; },
    penHyp(pen) {
      const p = Math.abs(pen || 0); if (p < 0.01) return [];
      const out = [`Potência: excesso de ≈${fmt(p / 0.5, 0)} W acima de 600 W (PP = 0,5·ΔSp)`];
      if (p <= 5) out.push(`Envergadura: excesso de ≈${fmt(p, 1)} cm acima de 4,0 m (PD = 100·ΔSd)`);
      else if (p >= 25) out.push(`Envergadura: excesso de ≈${fmt(p - 20, 1)} cm (>5 cm, inclui adicional de 20 pts)`);
      return out;
    },
  };

  // ------------------------------------------------------------ dados
  function Engine(data) {
    this.meta = data;
    const cols = data.columns;
    this.rows = data.rows.map((r) => { const o = {}; cols.forEach((c, i) => (o[c] = r[i])); return o; });
    this.rows.sort((a, b) => a.year - b.year || a.pos - b.pos || a.row_index - b.row_index);
    this.years = [...new Set(this.rows.map((r) => r.year))].sort();
    this.byYear = {};
    for (const y of this.years) this.byYear[y] = this.rows.filter((r) => r.year === y);
    this.F = data.fields;
  }
  const E = Engine.prototype;

  E.label = function (k) { return (this.F[k] && this.F[k].label) || this.meta.derived[k] || k; };
  E.hib = function (k) { return this.F[k] ? this.F[k].hib : true; };
  E.reg = function (y) { return this.meta.regulations[String(y)] || null; };
  E.edition = function (y) { return this.byYear[y] || []; };
  E.row = function (y, key) { return this.edition(y).find((r) => r.team_key === key) || null; };
  E.top = function (y, n) { return this.edition(y).slice(0, n); };
  E.fieldsInYear = function (y, cands) {
    const e = this.edition(y);
    return (cands || this.meta.dashboard).filter((f) => e.some((r) => isNum(r[f])));
  };

  E.teams = function () {
    const m = new Map();
    for (const r of this.rows) {
      const t = m.get(r.team_key) || { key: r.team_key, years: [], best: Infinity };
      t.name = r.team_name; t.school = r.school; t.uf = r.uf; t.years.push(r.year); t.best = Math.min(t.best, r.pos);
      t.last = r; m.set(r.team_key, t);
    }
    return [...m.values()].sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
  };
  E.history = function (key) { return this.rows.filter((r) => r.team_key === key); };

  E.rankIn = function (y, f, value) {
    const hib = this.hib(f);
    return 1 + this.edition(y).filter((r) => isNum(r[f]) && (hib ? r[f] > value : r[f] < value)).length;
  };

  // ------------------------------------------------------------ benchmark
  E.bench = function (y, key, f) {
    const e = this.edition(y);
    const me = e.find((r) => r.team_key === key);
    if (!me || !e.some((r) => isNum(r[f]))) return null;
    const others = e.filter((r) => r.team_key !== key);
    const hib = this.hib(f);
    let best = null;
    for (const r of others) if (isNum(r[f]) && (best === null || (hib ? r[f] > best[f] : r[f] < best[f]))) best = r;
    const above = e.filter((r) => r.pos < me.pos);
    const neighbor = above.length ? above[above.length - 1] : null;
    const top5 = e.slice(0, 5), top3 = e.slice(0, 3), champ = e[0];
    const reg = this.reg(y);
    const b = {
      field: f, label: this.label(f), year: y, team: v0(me[f]), rank: this.rankIn(y, f, v0(me[f])), n: e.length,
      champion: v0(champ[f]), championName: champ.team_name,
      top3: median(top3.map((r) => r[f])), top5: median(top5.map((r) => r[f])),
      top5min: Math.min(...top5.map((r) => v0(r[f]))), top5max: Math.max(...top5.map((r) => v0(r[f]))),
      fieldMedian: median(e.map((r) => r[f])), flyers: median(e.filter((r) => r.voou).map((r) => r[f])),
      best: best ? best[f] : NaN, bestTeam: best ? best.team_name : "—",
      neighbor: neighbor ? neighbor[f] : null, neighborName: neighbor ? neighbor.team_name : null,
      regMax: reg && reg.max[f] ? reg.max[f][0] : null,
      regRef: reg ? (reg.max[f] ? reg.max[f][1] : reg.refs[f] || null) : null,
    };
    b.gapTop5 = b.top5 - b.team; b.gapBest = b.best - b.team; b.gapChamp = b.champion - b.team;
    const nearBest = b.gapBest <= Math.max(0.1 * Math.abs(b.best), 0.5);
    b.status = b.team >= b.top5 - EPS && (nearBest || b.top5 > 0) ? "forte" : b.team >= b.flyers - EPS ? "atenção" : "crítico";
    return b;
  };

  E.target = function (b) {
    if (b.team < b.top5 - EPS) return [b.top5, "mediana do top-5 da edição"];
    if (b.team < b.best - EPS) return [b.best, `melhor valor observado (${b.bestTeam})`];
    return [b.team, "já no melhor nível observado"];
  };

  // ------------------------------------------------------------ simulação
  E.recomputeTotal = function (r) {
    return Math.max(0, this.meta.total_components.reduce((s, c) => s + v0(r[c]), 0));
  };
  E.simulate = function (y, key, changes) {
    const e = this.edition(y);
    const me = e.find((r) => r.team_key === key);
    if (!me) return null;
    const row = Object.assign({}, me);
    const bc = this.meta.battery_components;
    const compSum = bc.reduce((s, c) => s + v0(row[c]), 0);
    let base = v0(row.total_melhor_bateria);
    if (base <= 0 && compSum < 0) base = compSum;
    for (const [f, v] of Object.entries(changes || {})) {
      if (bc.includes(f)) { base += v - v0(row[f]); row.total_melhor_bateria = Math.max(0, base); }
      row[f] = v;
    }
    const total = this.recomputeTotal(row);
    const newPos = e.filter((r) => r.team_key !== key && r.total_geral > total + EPS).length + 1;
    return { original: me.total_geral, total, gain: total - me.total_geral, pos: me.pos, newPos, gained: me.pos - newPos };
  };

  E.podium = function (y, key) {
    const e = this.edition(y), me = this.row(y, key);
    if (!me) return null;
    const third = e.slice(0, 3)[Math.min(2, e.length - 1)], champ = e[0], top5 = e.slice(0, 5);
    const blocks = this.meta.total_components.map((c) => ({
      field: c, label: this.label(c), team: v0(me[c]), third: v0(third[c]), dThird: v0(third[c]) - v0(me[c]),
      top5: median(top5.map((r) => r[c])), dTop5: median(top5.map((r) => r[c])) - v0(me[c]),
      champ: v0(champ[c]), dChamp: v0(champ[c]) - v0(me[c]),
    }));
    return {
      total: me.total_geral, pos: me.pos, third: third.team_name, thirdTotal: third.total_geral,
      toPodium: Math.max(0, third.total_geral - me.total_geral + 0.01), champ: champ.team_name,
      champTotal: champ.total_geral, toTitle: Math.max(0, champ.total_geral - me.total_geral + 0.01), blocks,
    };
  };

  // ------------------------------------------------------------ séries e recorrência
  E.relativeSeries = function (key, f) {
    const out = [];
    for (const y of this.years) {
      const b = this.bench(y, key, f); if (!b) continue;
      out.push({ year: y, team: b.team, top5: b.top5, champion: b.champion, flyers: b.flyers,
                 rel: Math.abs(b.top5) > EPS ? b.team / b.top5 : NaN, rank: b.rank, n: b.n });
    }
    return out;
  };
  E.recurrence = function (key) {
    const res = {};
    for (const f of this.meta.dashboard) {
      let n = 0, below = 0, belowMed = 0; const years = [];
      for (const r of this.history(key)) {
        const b = this.bench(r.year, key, f); if (!b) continue;
        n++; if (b.team < b.flyers - EPS) belowMed++;
        if (b.team < b.top5 - EPS) { below++; years.push(r.year); }
      }
      if (n) res[f] = { n, below, belowMed, rate: below / n, years };
    }
    return res;
  };
  E.editionSummary = function () {
    return this.years.map((y) => {
      const e = this.edition(y), t = e.map((r) => r.total_geral);
      return { year: y, n: e.length, flyers: e.filter((r) => r.voou).length, champion: e[0].team_name,
               champTotal: e[0].total_geral, third: e[Math.min(2, e.length - 1)].total_geral,
               top5: median(e.slice(0, 5).map((r) => r.total_geral)), mean: mean(t), median: median(t), std: std(t) };
    });
  };

  // ------------------------------------------------------------ diagnóstico
  E._tip = function (f, y, me, b, meta, src) {
    const t5 = this.top(y, 5);
    if (meta === b.team) return `No nível de referência da edição (melhor observado ${fmt(b.best)}).`;
    const head = `Meta ${fmt(meta)} (${src}).`;
    switch (f) {
      case "pontos_voo":
        return `${head} Top-5: EE ${fmt(median(t5.map((r) => r.ee_calc)))} × sua ${fmt(me.ee_calc)}; PV ${fmt(median(t5.map((r) => r.peso_vazio)))} × ${fmt(me.peso_vazio)} kg; fator residual ${fmt(median(t5.map((r) => r.fator_residual)), 3)} × ${fmt(me.fator_residual, 3)}.`;
      case "notas_rel_apres":
        return `${head} Top-5 entre ${fmt(b.top5min)} e ${fmt(b.top5max)}; melhor nota: ${b.bestTeam} (${fmt(b.best)}).`;
      case "pontos_acurac":
        if (this.reg(y)) { const e = R26.cpErrFromPac(me.pontos_acurac); return `${head} Seu erro de previsão de carga ≈ ${e === null ? "≥15%" : pct(e)}; a meta equivale a ≈ ${pct(R26.cpErrFromPac(meta) || 0)}.`; }
        break;
      case "pontos_confiab":
        return `${head} Sua 2ª bateria caiu ${isNum(me.queda_2a_bateria) ? pct(me.queda_2a_bateria) : "100%"}; no top-5 a queda mediana foi ${pct(median(t5.map((r) => r.queda_2a_bateria)))}.`;
      case "bonus_pouso":
        return `${head} ${t5.filter((r) => r.pouso_100m === "Sim").length} de 5 do top-5 pararam em 100 m; o bônus escala com a carga/EE.`;
      case "bonus_tempo_carga":
        return `${head} Seu tempo: ${fmt(me.tempo_carga, 1)} s; top-5: ${fmt(median(t5.map((r) => (r.tempo_carga === 999 ? NaN : r.tempo_carga))), 1)} s.`;
    }
    if (this.meta.penalties.includes(f)) {
      const e = this.edition(y); return `${head} ${pct(e.filter((r) => r[f] === 0).length / e.length, 0)} das equipes da edição não sofreram essa penalidade.`;
    }
    return `${head} Melhor observado: ${b.bestTeam} (${fmt(b.best)}).`;
  };

  E._interp = function (f, y, me, b) {
    const reg = this.reg(y), t5 = this.top(y, 5), e = this.edition(y);
    const out = { text: "", hyps: [], conf: "Alta" };
    if (f === "notas_rel_apres") {
      out.text = "O resultado publicado soma relatório e apresentação; o PDF não separa as parcelas, então não é possível dizer qual disciplina perdeu pontos.";
      if (reg && me.notas_rel_apres < 123.3) {
        const fprMax = R26.fpr(me.notas_rel_apres), pv = v0(me.pontos_voo);
        out.text += ` Pelo regulamento ${y}, o FPR multiplica o voo e só satura com NR ≥ 123,3/185. Como a nota total (${fmt(me.notas_rel_apres)}) já é < 123,3, FPR ≤ ${fmt(fprMax, 3)}: o voo foi reduzido em pelo menos ${pct(1 - fprMax)}. Levar NR a ≥ 123,3 renderia ≥ ${fmt(pv > 0 ? pv / fprMax - pv : 0)} pts extras em P_voo além dos pontos diretos.`;
        out.hyps.push("FPR < 1 penalizou P_voo (derivado, Eq. 7.4)."); out.conf = "Média";
      }
    } else if (f === "pontos_voo") {
      out.text = `Perfil da equipe: CP ${fmt(me.carga_paga, 3)} kg, PV ${fmt(me.peso_vazio, 3)} kg, EE ${fmt(me.ee_calc)}, FPV ${fmt(me.fpv, 4)}. Top-5 (mediana): CP ${fmt(median(t5.map((r) => r.carga_paga)), 3)} kg, PV ${fmt(median(t5.map((r) => r.peso_vazio)), 3)} kg, EE ${fmt(median(t5.map((r) => r.ee_calc)))}, FPV ${fmt(median(t5.map((r) => r.fpv)), 4)}.`;
      const keys = ["pontos_carga_ee", "fpv", "fator_residual"];
      const ref = {}; keys.forEach((k) => (ref[k] = median(t5.map((r) => r[k]))));
      if (keys.every((k) => isNum(me[k]) && me[k] > 0) && v0(me.pontos_voo) > 0) {
        const logs = {}; keys.forEach((k) => (logs[k] = Math.log(me[k] / ref[k])));
        const tot = keys.reduce((s, k) => s + logs[k], 0);
        const nm = { pontos_carga_ee: "carga/EE", fpv: "FPV", fator_residual: "fator residual" };
        const shares = keys.slice().sort((a, c) => logs[a] - logs[c]).filter((k) => tot < 0 && logs[k] < 0)
          .map((k) => `${nm[k]} explica ${pct(logs[k] / tot, 0)} da diferença`);
        out.text += ` Decomposição observada (P_voo = pontos carga/EE × FPV × fator residual): fator residual ${fmt(me.fator_residual, 3)} vs ${fmt(ref.fator_residual, 3)} no top-5. ${shares.join("; ")}${shares.length ? "." : ""}`;
        if (reg) {
          const res = me.fator_residual, fprHi = R26.fpr(me.notas_rel_apres), cands = [];
          for (const n of [1, 2, 3]) for (const fpr of [...new Set([fprHi, 1])].sort()) {
            const x = res / (fpr * R26.fN(n));
            if (x > 0 && x <= 1) { const bs = -Math.log(x) / Math.log(1.15); if (bs >= 0.5 && bs <= 4) cands.push(`N=${n}, b≈${fmt(bs)} m (FPR=${fmt(fpr, 3)})`); }
          }
          if (cands.length) { out.text += ` Pelo regulamento ${y}, fator residual = FPR × f(N) × 1,15^(−b). Combinações coerentes com ${fmt(res, 3)}: ${cands.join("; ")}.`; out.hyps.push("Configuração (N) e envergadura (b) inferidas do fator residual; confirmar com o projeto real."); }
          const t5res = ref.fator_residual;
          out.text += ` No top-5 (${fmt(t5res, 3)}), exemplos com FPR = 1: N=3 com b≈${fmt(-Math.log(t5res / 1.15) / Math.log(1.15))} m ou N=1 com b≈${fmt(-Math.log(t5res / 1.22) / Math.log(1.15))} m.`;
          const err = R26.pvErrFromFpv(me.fpv);
          if (err !== null) { const errs = t5.map((r) => R26.pvErrFromFpv(r.fpv)).filter((x) => x !== null); out.text += ` FPV ${fmt(me.fpv, 4)} ⇒ erro de previsão do PV ≈ ${pct(err)} (Eq. 7.3); top-5: mediana ${pct(median(errs))}.`; }
          const needEE = b.top5 / (50 * me.fpv * res), maxEE = Math.max(...e.map((r) => v0(r.ee_calc)));
          out.text += ` Mantendo FPV e fator residual, chegar a P_voo ${fmt(b.top5)} exigiria EE ≈ ${fmt(needEE)} (maior EE da edição: ${fmt(maxEE)}).${needEE > maxEE ? " Só aumentar carga não basta: é preciso mexer no fator de configuração/relatório." : ""}`;
          out.conf = "Média";
        } else {
          out.text += ` Regulamento ${y} não disponível no projeto: a decomposição é uma identidade aritmética, mas o significado do fator residual nessa edição não pode ser determinado.`;
        }
      }
    } else if (f === "pontos_acurac") {
      if (!reg) out.text = "Sem o regulamento da edição não é possível converter pontos em erro de previsão.";
      else {
        const err = R26.cpErrFromPac(me.pontos_acurac); out.conf = "Média";
        const errs = t5.map((r) => R26.cpErrFromPac(r.pontos_acurac)).filter((x) => x !== null);
        out.text = err === null
          ? "Pontuação zero: erro de previsão ≥ ~15%, coeficientes não lançados no aeroct ou bateria sem acuracidade; o resultado não permite distinguir."
          : `P_AC ${fmt(me.pontos_acurac)} ⇒ erro de previsão de carga ≈ ${pct(err)} (Eq. 7.6 invertida). Top-5 que pontuaram: erro mediano ≈ ${pct(median(errs))}. Depende de previsão (reta a·Hρ + b), não de desempenho bruto.`;
      }
    } else if (f === "bonus_pouso") {
      const fl = e.filter((r) => r.voou);
      out.text = `Pouso < 100 m da equipe: ${me.pouso_100m}. ${pct(fl.filter((r) => r.pouso_100m === "Sim").length / fl.length, 0)} das equipes com voo pararam em 100 m.`;
      if (reg) { const bmax = 2 * v0(me.ee_calc); out.conf = "Média"; out.text += ` Em ${y}, B_PO = 2×EE: com a EE atual o máximo seria ${fmt(bmax)}.${bmax < b.top5 ? " A meta só é alcançável aumentando a EE; o pouso já não é o gargalo." : ""}`; }
    } else if (f === "bonus_tempo_carga") {
      out.text = `Tempo de retirada ${fmt(me.tempo_carga, 1)} s; mediana com registro ${fmt(median(e.filter((r) => r.tempo_carga < 999).map((r) => r.tempo_carga)), 1)} s.${reg ? " Em 2026 o bônus cai de 20 para 15,5 pts com 0,5 s acima de 20 s (Eq. 7.8)." : ""}`;
    } else if (f === "pontos_confiab") {
      out.text = `2ª melhor bateria ${fmt(me.total_2a_bateria)} vs melhor ${fmt(me.total_melhor_bateria)} (queda ${isNum(me.queda_2a_bateria) ? pct(me.queda_2a_bateria) : "—"}). Top-5: queda mediana ${pct(median(t5.map((r) => r.queda_2a_bateria)))}.`;
      if (isNum(me.voos_validos)) out.text += ` Voos válidos: ${me.voos_validos} (top-5 mediana ${fmt(median(t5.map((r) => r.voos_validos)), 0)}).`;
      if (reg) { out.text += " Pelo regulamento 2026 a bonificação zera com queda ≥ 44,7% e vale 16 pts com 20% (Eq. 7.9)."; out.conf = "Média"; }
    } else if (f === "pen_dim_pot") {
      const v = v0(me.pen_dim_pot);
      if (v >= 0) out.text = "Sem penalidade.";
      else {
        out.text = `Penalidade de ${fmt(v)} pts na melhor bateria.`;
        const cs = this.meta.battery_components.reduce((s, c) => s + v0(me[c]), 0);
        if (v0(me.total_melhor_bateria) === 0 && cs < 0) out.text += " Ela ZEROU a bateria (soma dos componentes negativa).";
        if (reg) { const h = R26.penHyp(v); out.hyps = h; out.conf = "Baixa";
          out.text += h.length === 1 ? ` Única hipótese compatível pelo regulamento: ${h[0]}.` : ` Hipóteses pelo regulamento: ${h.join("; ")}. O PDF não informa qual ocorreu.`; }
        else out.text += " Sem o regulamento da edição não é possível separar dimensão de potência.";
      }
    }
    return out;
  };

  const RECS = {
    notas_rel_apres: "Usar como benchmark os relatórios do top-5 (quando públicos) e revisar cada disciplina com banca interna antes da entrega.",
    pontos_voo: "Atacar o termo com maior participação na decomposição: fator residual → configuração/envergadura e FPR; carga/EE → reduzir PV e aumentar CP; FPV → melhorar a previsão de peso vazio.",
    pontos_acurac: "Refazer a curva de carga vs. altitude-densidade com ensaios em voo e margem estatística; comparar previsão e carga real em cada bateria.",
    bonus_pouso: "Treinar e projetar para parada dentro da zona de 100 m (freio, trem, rampa de aproximação).",
    bonus_tempo_carga: "Cronometrar a retirada de carga em treinos com 2 pessoas; manter margem abaixo do limite do bônus.",
    pontos_confiab: "Garantir duas baterias válidas e próximas: plano de manutenção entre baterias e inspeção pós-voo.",
    total_video: "Cumprir integralmente os requisitos do vídeo de voo no prazo.",
    pen_dim_pot: "Checagem dimensional e de potência (wattímetro de pico, hélice escolhida por ensaio) antes de cada bateria.",
    pen_validacao: "Reforçar componentes não primários e rodas; inspeção após cada pouso.",
    pen_competicao: "Checklist de prazos e requisitos documentais.",
  };
  const CONF = {
    Alta: "valor oficial e comparação direta com outras equipes da mesma edição",
    Média: "inclui grandezas derivadas das fórmulas do regulamento da edição",
    Baixa: "a causa é hipótese; o PDF de resultados não a registra",
  };

  E.diagnose = function (y, key) {
    const me = this.row(y, key); if (!me) return [];
    const reg = this.reg(y), out = [];
    for (const f of this.meta.score_criteria) {
      const b = this.bench(y, key, f); if (!b) continue;
      const [meta, src] = this.target(b);
      const sim = meta !== b.team ? this.simulate(y, key, { [f]: meta }) : { gain: 0, gained: 0, newPos: me.pos };
      const it = this._interp(f, y, me, b);
      const refs = [`${me.source_file}, p. ${me.page}, linha Pos ${me.pos} (${me.team_name}), coluna "${b.label}"`];
      if (reg && (reg.refs[f] || reg.max[f])) refs.push(reg.refs[f] || reg.max[f][1]);
      else if (!reg) refs.push(`Regulamento ${y}: não disponível no projeto; fórmula da edição não verificada.`);
      const t5 = this.top(y, 5);
      out.push({
        field: f, label: b.label, year: y, status: b.status, bench: b,
        problem: b.status === "forte" || meta === b.team ? `${b.label}: nível de referência (${b.rank}º de ${b.n}).`
          : `${b.label}: ${fmt(b.team)} pts, ${fmt(meta - b.team)} abaixo da meta (${src}; ${b.rank}º de ${b.n}).`,
        evidence: `Equipe ${fmt(b.team)} (${b.rank}º/${b.n}). Faltam ${fmt(b.gapTop5, 2, true)} pts para a mediana do top-5 e ${fmt(b.gapChamp, 2, true)} para o campeão (positivo = a ganhar).`,
        competitive: `Mediana top-5 ${fmt(b.top5)} (faixa ${fmt(b.top5min)}–${fmt(b.top5max)}); campeão (${b.championName}) ${fmt(b.champion)}; melhor observado ${fmt(b.best)} (${b.bestTeam}); mediana das equipes com voo ${fmt(b.flyers)}.${b.neighborName ? ` Equipe logo acima no geral (${b.neighborName}): ${fmt(b.neighbor)}.` : ""}`,
        interpretation: it.text, hyps: it.hyps, conf: it.conf, confWhy: CONF[it.conf],
        recommendation: `Meta: ${fmt(meta)} (${src}). Referências: ${t5.map((r) => `${r.team_name} (${fmt(r[f])})`).join(", ")}. ${RECS[f] || ""}`,
        tip: this._tip(f, y, me, b, meta, src), meta, metaSrc: src,
        gain: sim.gain, gained: sim.gained, newPos: sim.newPos, refs,
      });
    }
    return out;
  };

  E.priorities = function (y, key, effortOverride, weights) {
    const eff = Object.assign({}, this.meta.effort, effortOverride || {});
    const w = Object.assign({ potencial: 0.35, posicoes: 0.25, recorrencia: 0.15, facilidade: 0.25 }, weights || {});
    const latest = this.years[this.years.length - 1];
    const current = this.fieldsInYear(latest);
    const rec = this.recurrence(key);
    const rows = this.diagnose(y, key).filter((d) => d.gain > 0.01 && current.includes(d.field)).map((d) => {
      const e = eff[d.field] || { esforco: 3, custo: 3, risco: 3, prazo: "—", disciplinas: "—" };
      return { field: d.field, label: d.label, status: d.status, gain: d.gain, gained: d.gained, newPos: d.newPos,
               rec: rec[d.field] ? rec[d.field].rate : 0, esforco: e.esforco, custo: e.custo, risco: e.risco,
               prazo: e.prazo, disciplinas: e.disciplinas, conf: d.conf, meta: d.meta, metaSrc: d.metaSrc,
               current: me_(this, y, key)[d.field] };
    });
    if (!rows.length) return rows;
    const norm = (k) => { const a = rows.map((r) => r[k]), lo = Math.min(...a), hi = Math.max(...a); return (v) => (hi > lo ? (v - lo) / (hi - lo) : 1); };
    const nG = norm("gain"), nP = norm("gained");
    rows.forEach((r) => {
      r.ease = (15 - r.esforco - r.custo - r.risco) / 12;
      r.score = w.potencial * nG(r.gain) + w.posicoes * nP(r.gained) + w.recorrencia * r.rec + w.facilidade * r.ease;
    });
    rows.sort((a, b) => b.score - a.score);
    rows.forEach((r, i) => (r.priority = i + 1));
    return rows;
  };
  function me_(eng, y, key) { return eng.row(y, key) || {}; }

  E.limiting = function (diags, n = 3) {
    return diags.filter((d) => d.gain > 0).sort((a, b) => b.gained - a.gained || b.gain - a.gain).slice(0, n);
  };

  E.referenceGroups = function (y, key) {
    const e = this.edition(y), me = this.row(y, key);
    const g = { "Campeão": e.slice(0, 1), "Top-3": e.slice(0, 3), "Top-5": e.slice(0, 5) };
    if (me) g["Concorrentes diretas (±3)"] = e.filter((r) => Math.abs(r.pos - me.pos) <= 3 && r.team_key !== key);
    const i = this.years.indexOf(y);
    if (i > 0) {
      const prev = this.years[i - 1], pmap = {};
      this.edition(prev).forEach((r) => (pmap[r.team_key] = r.percentil_total));
      g[`Maior evolução (${prev}→${y})`] = e.filter((r) => r.team_key in pmap)
        .sort((a, b) => (b.percentil_total - pmap[b.team_key]) - (a.percentil_total - pmap[a.team_key])).slice(0, 5);
    }
    return Object.fromEntries(Object.entries(g).map(([k, v]) => [k, v.map((r) => r.team_key)]));
  };

  Engine.fmt = fmt; Engine.pct = pct; Engine.median = median; Engine.isNum = isNum; Engine.R26 = R26;
  if (typeof module !== "undefined" && module.exports) module.exports = Engine;
  else root.Engine = Engine;
})(typeof window !== "undefined" ? window : globalThis);
