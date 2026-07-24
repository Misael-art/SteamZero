# WI-F3 — Paginação e follow de jobs/operações

## Entrega

- jobs e operações possuem paginação keyset decrescente, com limite obrigatório
  entre 1 e 256 e cursor determinístico;
- o log append-only possui leitura crescente paginada por `seq`, filtros exatos
  de kind/entity e cursor próprio para reconexão sem duplicação;
- `steamzero jobs list --follow --json` e
  `steamzero operations list --follow --json` emitem NDJSON `event-v1` e podem
  acompanhar um alvo até seu estado terminal;
- o follow consome uma página por vez, libera cada evento imediatamente e não
  acumula o histórico em memória;
- transações do núcleo espelham estados de operação no State Store sem substituir
  o journal de recovery; atualização de operação e `operation.state` são atômicos;
- progresso mais recente continua persistido no job, enquanto a emissão pública
  é limitada a 4 eventos/s por job;
- a projeção pública recupera correlação do job, usa correlação sistêmica
  reservada quando não existe requisição e não expõe parâmetros, ambiente ou paths
  internos de journal/backup.

## Limite de escopo

F3 entrega o contrato, persistência, paginação e transporte local da CLI.
Subscriptions duráveis no socket JSON-RPC e a reconexão do cliente do daemon
pertencem a F4; a CLI com flags ainda faz fallback seguro para o núcleo local.

## Evidência

- testes de State Store cobrem keyset, limite, filtros, cursor e atomicidade;
- testes `event-v1` cobrem reconexão, páginas múltiplas, payloads degradados,
  unidades reais, eventos sistêmicos e parada terminal;
- testes CLI cobrem NDJSON de jobs/operações, modo humano, validação de entradas
  e ausência de paths internos;
- testes transacionais provam `applying → committed` no espelho persistido;
- suíte integral: `1313 passed`;
- cobertura limpa: `85.24%` (mínimo exigido: 85%);
- Ruff, mypy strict, independência, fronteiras e `git diff --check`: aprovados.

Nenhuma validação física é alegada.
