# Status verificavel do projeto

`docs/status/items/*.json` e a unica fonte de verdade para o estagio atual de cada capacidade. Os arquivos em `docs/STATUS.md` e `docs/ACTIVE-WORK.md` sao gerados; nao os edite manualmente.

Documentos de visao, ADRs e catalogos definem intencao. `WORKLOG.md`, diagnosticos e relatorios preservam fatos e decisoes. Nenhum deles deve ser usado sozinho para afirmar que uma capacidade esta pronta.

## Modelo

Cada item usa cinco eixos independentes:

| Campo | Pergunta respondida |
|---|---|
| `implementation` | O codigo existe? |
| `integration` | Em qual linha ele esta integrado? |
| `verification` | Qual evidencia realmente o exercitou? |
| `operation` | Qual e a verdade operacional observada? |
| `distribution` | Foi empacotado, instalado ou certificado? |

O campo derivado exibido em `STATUS.md` nunca substitui os cinco eixos. Por exemplo, `verified-dev` nao autoriza alegar VM, hardware ou release.

## Fluxo obrigatorio de trabalho paralelo

1. Antes de iniciar, o coordenador cria ou atualiza um registro em `workstreams/`, com branch, base, dono e caminhos exclusivos.
2. O agente confere `docs/ACTIVE-WORK.md`, cria sua branch da base declarada e trabalha somente no escopo registrado.
3. Cada mudanca em `src/`, `tools/`, `tests/` ou documentacao normativa precisa pertencer a algum `scopePaths`. O `status-check` reprova arquivo alterado sem dono.
4. Ao fechar, o agente atualiza o item com evidencia, `scopeDigest`, gaps, proxima acao e workstream. A entrada no WORKLOG continua append-only e historica.
5. Somente o integrador altera arquivos compartilhados no ultimo commit de integracao. A visao gerada e atualizada no mesmo commit.

`docs/WORKLOG.md` nao recebe blocos de inicio. O inicio e o claim do workstream; o fechamento e registrado no worklog do item ou na sessao append-only final, em conformidade com `AGENTS.md`.

## Comandos

```bash
rtk .venv/bin/python tools/project_status.py digest --item SZ-M10
rtk .venv/bin/python tools/project_status.py render --write
rtk .venv/bin/python tools/project_status.py check
make status-check
```

O digest sela exatamente os arquivos em `scopePaths`. Quando um deles muda, a evidencia fica obsoleta ate que o responsavel atualize o item apos reexecutar os testes aplicaveis.

## Regras de nomenclatura

- capacidades: `SZ-<DOMINIO>-<NOME>`;
- workstreams: `WS-<ANO>-<MES>-<NOME>`;
- gaps legados mantem os prefixos `GAP-`, `LEDGER-` ou `DEBT-`;
- `M10`, `A7` ou `G5` sem namespace nao sao identificadores validos de status.
