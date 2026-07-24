# WI-D3 — Catálogos de mods/cheats e jornada NSZ

## Entrega

- `EmulationController` compõe, por portas injetáveis, GitHub mods, SEMD,
  `ns-emu-mod-downloader` e NSECM; nenhum adapter existente foi reescrito;
- busca por Title ID executa em job cancelável, publica progresso e persiste
  candidatos nas tabelas de catálogo já migradas;
- falha/offline preserva o último cache válido em vez de apagar resultados;
- snapshot por jogo publica busca, candidatos, origem, Build ID, confiança e
  ações com motivo explícito;
- cheat remoto somente é instalável quando possui Build ID e códigos Atmosphere
  válidos; a escrita usa plano, confirmação, backup e rollback do núcleo;
- candidatos de mod são visíveis, mas instalação fica bloqueada até que URLs
  heterogêneas sejam materializadas e inspecionadas como árvore segura;
- a jornada NSZ já existente foi verificada de ponta a ponta na composição:
  card pronto → seletor local → `nsz.convert` → serviço transacional.

## Limites honestos

D3 permanece `in-progress`: lifecycle local de mods está operacional, mas
download/preparo transacional de pacotes remotos de mod ainda é um WI separado.
D8 permanece `in-progress` porque conversão está conectada, enquanto artwork
canônico pertence a A7.

## Evidência

- testes focados cobrem busca, cache offline, read model, bloqueio honesto de
  mod, instalação de cheat e publicação NSZ;
- jornada QML offscreen cobre cards de busca/candidatos e estados das ações;
- suíte integral: `1281 passed`;
- cobertura limpa: `85.13%` (mínimo exigido: 85%);
- Ruff, mypy strict, independência, fronteiras e `git diff --check`: aprovados.

Nenhuma validação física é alegada.
