# WI-F4 — Daemon persistente e compatibilidade CLI

## Entrega

- `jobs.list`, `operations.list` e `events.page` passaram a integrar a allowlist
  fechada do daemon, preservando paginação, envelopes e fallback local da CLI;
- `events.subscribe` mantém a conexão UNIX autenticada dedicada e entrega
  notificações JSON-RPC `events.event` seguidas de `events.complete`;
- o ack fixa `subscriptionId`, transporte e cursor inicial antes de qualquer
  evento, removendo a janela entre descoberta do maior `seq` e início do follow;
- filtros de kinds, jobs, operações e entidades são exatos e limitados; página,
  timeout, listas, texto e tamanho de mensagem possuem limites explícitos;
- jobs e operações informados são validados antes do ack, e kinds internos não
  entram na superfície pública;
- o cliente valida cada `event-v1`, ordem estritamente crescente, identidade da
  assinatura e cursores de ack/conclusão;
- queda de transporte depois do ack retoma pelo último cursor entregue, com no
  máximo três reconexões e sem fallback para outra fonte;
- fallback in-process continua permitido somente quando o daemon nunca chegou a
  ser conectado;
- assinatura ociosa percebe desconexão do peer e shutdown do servidor, evitando
  handlers presos; uma conexão em stream não volta ao dispatch de comandos.

## Segurança e limites

- somente AF_UNIX, socket `0600`, diretório `0700` e `SO_PEERCRED` do mesmo UID;
- nenhuma reflexão, TCP, comando de shell ou campo RPC desconhecido;
- mensagens limitadas a 1 MiB, filtros a 64 itens, página entre 1 e 256 e idle
  timeout entre 0 e 86400 segundos;
- consumo de memória limitado a uma página, independentemente do tamanho do
  histórico persistido;
- eventos não carregam paths de journal/backup, parâmetros ou ambiente interno.

## Evidência

- testes focados de eventos, CLI, cliente e serviço: 90 aprovados;
- teste de socket falso força queda depois do primeiro evento e prova que a
  segunda requisição envia o cursor confirmado, sem duplicação;
- testes de daemon real cobrem capabilities, queries paginadas, assinatura,
  conclusão terminal e preferência da CLI pelo IPC;
- parser defensivo cobre campos desconhecidos, listas/tamanhos, kinds privados,
  cursores, limites, timeout não finito e tipos booleanos indevidos;
- suíte integral: 1332 aprovados;
- cobertura limpa: 85,03% (mínimo exigido: 85%);
- Ruff, mypy strict em 140 módulos, independência, fronteiras e
  `git diff --check`: aprovados.

Estado final: `verified-dev`. Nenhuma validação física é alegada.
