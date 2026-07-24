# WI-G2 — Compositor puro de ambiente de lançamento

## Entrega

- `compose_launch_environment` recebe uma cópia do ambiente herdado e camadas
  declarativas, sem mutar as entradas;
- o launcher compõe uma única vez as camadas `steamzero`, `mangohud` e
  `frame-generation` antes de criar o processo;
- ownership de variáveis gerenciadas é fechado e colisões com o ambiente
  herdado ou entre camadas falham antes do lançamento;
- o resumo público `gtool-launch-environment-v1` informa somente camadas,
  nomes das chaves, política de colisão e ausência de shell;
- valores de ambiente e segredos herdados não são publicados no contrato.

## Segurança

- apenas chaves allowlisted podem ser produzidas por uma camada;
- IDs, chaves e valores têm formato e tamanho limitados, e NUL é recusado;
- `PATH`, `LD_PRELOAD` e qualquer variável arbitrária não podem ser injetados
  pelo compositor;
- nenhuma camada executa shell ou expande texto;
- uma variável gerenciada já presente no ambiente pai é tratada como conflito
  de ownership, sem sobrescrita silenciosa.

## Evidência

- suíte integral: 1.444 testes aprovados;
- cobertura total: 85,32%;
- cobertura do novo domínio de composição: 100%;
- Ruff, mypy em 152 módulos, independência e fronteiras: aprovados;
- contratos golden incluem `gtool-launch-environment-v1`;
- testes cobrem pureza, redação pública, colisões, IDs inválidos, NUL,
  `LD_PRELOAD` e ownership herdado.

Estado final: `verified-dev`.
