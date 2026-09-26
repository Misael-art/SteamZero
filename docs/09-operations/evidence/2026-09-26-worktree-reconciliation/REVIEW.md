# Revisão e decisões de reconciliação — 2026-09-26

Base verificada: `origin/main` em `ed097a1323d5b48c4d1334adffa00b86383303fd`.
Na revisão inicial, as árvores fonte continuavam preservadas e nenhum worktree
havia sido removido. A passagem posterior de centralização está registrada em
`CENTRALIZATION.md`.

## Checkpoint local

A primeira sessão integral perdeu a sessão do terminal em 27%, sem emitir
resultado e deixando seu diretório temporário; ela foi classificada como
interrompida, não como falha de testes. Uma execução durável subsequente terminou
com exit 0: 6.294 passed, 47 skipped em 2.202,78s. O log completo está em
`INTEGRAL-TESTS.log`. A guarda real-state foi idêntica antes/depois: 12.588
arquivos, 2.061 diretórios, 1.327.036.375 bytes e mesmo `max_mtime_ns`.

Independência, boundaries, component lock, capability matrix, status-check,
ruff check, ruff format e `python -m mypy src` passaram. O alvo Makefile
`typecheck` não pôde iniciar porque este worktree não tinha `.venv/bin/mypy`;
usei o módulo mypy do ambiente compartilhado (297 arquivos, sem erros). Nenhum
CI, push ou merge foi executado.

## Conteúdo integrado nesta branch

- **063 — AURA completion:** portado o preflight das BIOS declaradas no perfil
  de lançamento. Falta BIOS ou projeção `bios.link`? readiness/launch falham
  com `E-CONTENT-BIOS-MISSING` antes de tentar iniciar o emulador.
- **063 — catálogo multidisco:** portado com o modelo atual. Um M3U só é
  publicado no catálogo se o scan atual reconhecer o mesmo conjunto, a
  propriedade SteamZero e IDs/ordem/caminhos exatos, e se o hash dos arquivos
  derivados bater com os membros dos archives. A origem permanece; quando a
  projeção válida entra, os archives desse conjunto não são publicados em
  duplicidade. A alteração candidata a `/tmp` em `run_tests_isolated.py` não foi
  portada: é independente, afeta infraestrutura compartilhada e precisa de
  reprodução específica antes de alterar o runner.
- **045/050/054 — planos de conteúdo:** requisitos foram consolidados em
  `docs/12-roadmap/REAL-CONTENT-COVERAGE-PLAN.md`. Os três ramos compartilhavam
  o mesmo ponto de inserção do roadmap e apontavam para seis planos/prompts que
  não existem na main. As capacidades e formatos atuais foram conferidos nos
  manifestos; nenhum manifesto, snapshot de status ou promessa de launch foi
  duplicado.
- **006 — gates em lote:** aceita-se a cadência de testes focados durante o
  lote, checkpoint integral uma vez no corte estável e CI remoto consultado no
  estado terminal. `AGENTS.md` e `CI-AND-GATE-EFFICIENCY.md` agora expressam a
  mesma regra, incluindo `make status-check`.

## Evidência visual revisada

- **029 — `06-details-installed-baseline.png`: não promover.** A captura foi
  inspecionada e contém uma janela externa preta cobrindo a área de detalhes;
  texto “Screenshots não publicados” permanece visível. Comparei os oito PNGs
  sujos com `origin/main`: sete são idênticos; o README já marca esta captura
  única como não promovida. Arquivo fica no worktree de origem até limpeza
  explícita.
- **038 — `07-release-post-install.png`: não substituir.** A captura fonte tem
  hash Git `2bd9b6df377e0d4c59e3974b4963bf992c9b1e88` e relógio 20:08. A main já
  contém a captura posterior das 20:13, hash
  `85715577be46bb54b4d91f0d209cf83f0a2544e2`; a versão fonte é redundante e
  anterior.

## Limpeza posterior

Inventário read-only após as sete frentes selecionadas: 11 worktrees antigos
continuam sujos; esta branch de reconciliação é o 12º. Os quatro fora do escopo
selecionado ficam marcados como candidatos à limpeza final, com estas barreiras:

| Worktree | Evidência atual | Condição antes de remover |
|---|---|---|
| `root-Port_Steam` | 23 entradas sujas; mudanças de registry/title variants revisadas como já presentes na main; há relatórios e artefatos temporários locais | Inventariar e guardar qualquer arquivo não rastreado que ainda contenha evidência única; não apagar temporários pelo nome apenas |
| `001-steamzero-gap-g16` | 4 entradas sujas; correção de symlink em código/testes já existe na main; `WORKLOG.md` local tem 9 linhas próprias | Preservar a sessão do WORKLOG em cópia antes de descartar a árvore |
| `060-steamzero-cohesive-roadmap` | 10 entradas, várias staged; inclui guideline, roadmap, evidência e `WORKLOG.md` próprios | Revisar/archive do patch staged e do WORKLOG; não é seguro apagar a árvore ainda |
| `104-Port_Steam-theme-default-pr2` | 2 comentários `pragma: no cover`, sem mudança de comportamento | Guardar diff curto e confirmar árvore/refs antes da remoção final |

Os sete worktrees fonte 006/029/038/045/050/054/063 foram preservados durante a
reconciliação. As alterações locais, pontas dos worktrees e critérios de
centralização estão registrados em `CENTRALIZATION.md`; nenhum conteúdo local
foi usado como motivo para descartar commits sem cópia recuperável.
