# CLAUDE.md — SAE AeroDesign Intelligence

Contexto para continuar o desenvolvimento no Claude Code.

## Comandos
- `streamlit run app.py` — app (importa `data/raw/*.pdf` se a base estiver vazia)
- `python -m pytest -q` — testes (rodar após qualquer mudança em `aerointel/`)
- `python scripts/ingest.py` — reimporta PDFs

## Regras do domínio (não violar)
- Só Classe Regular. `extraction.py` lê a classe do título e `validation`/`ingest` recusam outras.
- Nunca inventar pontuação. Metas vêm de outras equipes da mesma edição.
- Não aplicar fórmula de um regulamento a outra edição. Para adicionar um regulamento:
  registre-o em `rules.REGULATIONS[ano]` com tetos e referências (§, equação, página) e
  só então habilite interpretações em `diagnosis.py`.
- Comparação entre anos = posição relativa (`analysis.relative_series`), não pontos brutos.
- Interface (`ui/`) não calcula nada; toda lógica fica em `aerointel/`.

## Extração
- Os PDFs não têm grade; células longas transbordam e se sobrepõem. A extração usa a ORDEM
  do fluxo de caracteres (`_runs_from_chars`): novo run quando o x volta ou salta > 0,6 pt.
- Colunas numéricas por edição: `schema.TAIL_BASE` + opcionais detectadas por palavra do
  cabeçalho (`schema.OPTIONAL_TAIL`). Se um novo PDF falhar, ajuste ali e adicione teste.

## Ideias para a V1
- Regulamentos 2022–2025 e resultados de 2025.
- Importar planilhas internas da equipe (PV previsto, N, b, notas por disciplina) para trocar hipóteses por dados.
- Notas por disciplina quando a organização publicar o detalhamento.
