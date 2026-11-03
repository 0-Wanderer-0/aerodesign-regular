# SAE AeroDesign Intelligence — V0 (Classe Regular)

Inteligência competitiva a partir dos PDFs oficiais de pontuação final da SAE BRASIL AeroDesign.
Digite o nome de qualquer equipe → o sistema vincula **universidade, ranking e ano** de cada edição,
monta **blocos por categoria** e diz **como melhorar usando apenas dados de outras equipes**.

## Rodar

```bash
pip install -r requirements.txt
streamlit run app.py          # na 1ª execução importa os PDFs de data/raw
python -m pytest -q           # 26 testes
python scripts/ingest.py      # reimporta a pasta data/raw (opcional)
```

Novos PDFs: página **06 — Documentos e dados → Importar resultados**, ou copie para `data/raw/` e rode `scripts/ingest.py`.
Se já existir resultado da mesma edição, o novo documento o substitui (ex.: rev01 sobre rev00) e isso fica no log.

## Site público (estático, open source)

O mesmo conteúdo do painel, para qualquer pessoa com o link, sem servidor:

```bash
python scripts/build_site.py      # gera site/dist/index.html (arquivo único, ~160 KiB, dados embutidos)
```

- Abra `site/dist/index.html` no navegador, ou publique a pasta `site/dist/` em qualquer hospedagem estática.
- **GitHub Pages:** suba o repositório, vá em *Settings → Pages → Source: GitHub Actions*. O workflow
  `.github/workflows/pages.yml` reimporta os PDFs, roda os testes e publica a cada push na `main`.
- Abas do site: Blocos por categoria · Comparar equipes (edição inteira por critério + frente a frente) ·
  Ranking completo (ordenável, clique abre a equipe) · Histórico · Prioridades (esforço/custo/risco editáveis,
  relatório em Markdown para copiar) · Método e fontes.
- Os cálculos rodam no navegador em `site/src/engine.js`, um porte de `analysis.py` + `diagnosis.py`.
  `tests/test_site_parity.py` compara os dois motores em **todas** as linhas da base (leva ~6 min; precisa de Node).

**Nova edição:** coloque o PDF em `data/raw/`, rode `python scripts/ingest.py`, `python -m pytest -q` e
`python scripts/build_site.py` (ou só faça push: o workflow faz tudo).

## Páginas do painel Streamlit

| Página | Conteúdo |
|---|---|
| 01 Visão geral | KPIs, **blocos por categoria** (valor, rank, régua vs. top-5/campeão, ganho simulado, “como melhorar”), evolução |
| 02 Análise histórica | Heatmap equipe ÷ mediana top-5 por ano, séries por critério, variabilidade |
| 03 Benchmarking | Campeão / top-3 / top-5 / concorrentes diretas / maior evolução; radar de percentis; ranking completo |
| 04 Diagnóstico | O que limita a classificação, cascata até o 3º lugar, simulador, diagnóstico completo com evidência e confiança |
| 05 Relatório | Matriz de priorização (esforço/custo/risco editáveis), metas por disciplina, síntese por IA (opcional), exportação MD/HTML |
| 06 Documentos e dados | Upload com validação antes de incorporar, correções auditáveis, apelidos de equipes, log, regulamentos, CSV |

## Arquitetura

```
aerointel/
  schema.py      campos canônicos, blocos e ordem das colunas por edição
  extraction.py  PDF → linhas (lê o fluxo de caracteres: células transbordam e se sobrepõem)
  validation.py  identidade do total, soma da bateria, ordenação, regime da coluna de carga
  db.py          SQLite: documents, results_raw, results, corrections, aliases, processing_log
  teams.py       chave de equipe entre edições + busca aproximada
  rules.py       fórmulas/tetos/referências por regulamento (só 2026 disponível)
  analysis.py    benchmarking, lacuna p/ pódio, simulação, recorrência, séries relativas
  diagnosis.py   diagnóstico crítico, dicas, matriz de priorização
  report.py      relatório Markdown/HTML com referências
  llm.py         síntese opcional via API (ANTHROPIC_API_KEY)
ui/              páginas Streamlit — sem lógica de cálculo
tests/           pytest
```

## O que foi verificado nos PDFs (não presumido)

- 2022: 56 equipes, vírgula decimal, 22 colunas numéricas. 2023: 56, + *Bônus motor elétrico* e *Desempate*.
  2024: 57, ponto decimal, *Desempate*. 2026: 61, página girada 90°, + *Maior EE* e *Voos válidos*.
- `Total = max(0, Melhor bateria + Confiabilidade + Notas + Vídeo + Penalidades)` confere em todas as edições.
- A coluna “Pontos” após o FPV é **12,5 × CP** em 2022–2024 e **50 × EE** em 2026 (detectado aritmeticamente) — não comparar entre regimes.
- Em alguns casos a *Penalidade de validação* (−20) não está descontada da melhor bateria; o valor oficial é mantido e a diferença fica registrada.

## Regras de confiabilidade implementadas

- Metas = mediana do top-5 ou melhor valor observado **da mesma edição** — nunca valores inventados.
- Interpretação causal só com o regulamento da própria edição (hoje, 2026). Para 2022–2024 o sistema declara que a causa não pode ser determinada.
- Cada diagnóstico traz arquivo, página, linha e coluna de origem, referência do regulamento, e confiança (Alta/Média/Baixa).
- Esforço, custo e risco são estimativas editáveis, separadas dos dados observados.
- Correções manuais não sobrescrevem o original (tabela `corrections`).

## Limitações conhecidas

- Faltam os resultados de 2025 e os regulamentos de 2022–2025.
- Relatório e apresentação vêm somados no PDF de resultados.
- Simulações mantêm as demais equipes fixas (cenário, não previsão).
- A unificação de grafias de equipes cobre os casos conhecidos; revise na página 06 ao importar novas edições.
