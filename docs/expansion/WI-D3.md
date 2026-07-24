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
- candidatos de mod com artefato HTTPS suportado (`zip`, `ips`, `bps`,
  `pchtxt`, `txt` ou `bin`) podem ser baixados em job, inspecionados e
  materializados em cache gerenciado endereçado pelo SHA-256 do conteúdo;
- ZIPs usam `safezip` com limites de contagem, tamanho, profundidade e razão de
  expansão; traversal, caminhos absolutos e symlinks são recusados sem publicar
  manifesto parcial;
- instalação de mod remoto somente é habilitada depois do preparo; o plano
  revalida manifesto, confinamento, tamanho e SHA-256 de cada arquivo antes da
  cópia transacional;
- resultados cuja fonte publica somente uma página/diretório continuam
  visíveis, porém desabilitados com motivo explícito em vez de simular suporte;
- a jornada NSZ já existente foi verificada de ponta a ponta na composição:
  card pronto → seletor local → `nsz.convert` → serviço transacional.

## Limites honestos

D3 está `verified-dev`: lifecycle local, busca/cache remoto, preparo seguro de
artefatos, instalação transacional e estados honestos de fonte não suportada
foram verificados em desenvolvimento. A marca não afirma validação física de
rede, emulador ou hardware.

D8 permanece `in-progress` porque conversão está conectada, enquanto artwork
canônico pertence a A7.

## Evidência

- testes focados cobrem busca, cache offline, read model, preparo/instalação de
  mod, adulteração do cache, rejeição de ZIP com traversal, instalação de cheat
  e publicação NSZ;
- jornada QML offscreen cobre cards de busca/candidatos e estados das ações;
- suíte integral: `1282 passed`;
- cobertura limpa: `85.05%` (mínimo exigido: 85%);
- Ruff, mypy strict, independência, fronteiras e `git diff --check`: aprovados.

Nenhuma validação física é alegada.
