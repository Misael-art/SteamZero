# Centralização dos worktrees — 2026-09-26

## Direção

O único checkout SteamZero ativo está em `Canonical/2026-09-21`, na branch
`codex/main-worktree-reconciliation-2026-09-26`. A base medida é `origin/main`
(`ed097a1323d5b48c4d1334adffa00b86383303fd`); o código reconciliado partiu de
`eef9337b4497e073233c27050ae732b71a7a27fb`. A árvore `.git` principal foi
relocalizada com esse checkout; `Project Backup/` não faz mais parte da árvore
do projeto.

## Decisão sobre as sete frentes

- **063 — AURA completion:** preflight de BIOS e projeção multidisco foram
  reconciliados nesta branch. A alteração candidata ao runner de testes segue
  fora até reprodução específica.
- **045/050/054 — planos de conteúdo:** requisitos foram consolidados em um
  único plano de cobertura de conteúdo real; não foram duplicados manifestos
  nem promessas de suporte.
- **006 — gates em lote:** a cadência focada e o checkpoint integral ficaram
  alinhados em `AGENTS.md` e `CI-AND-GATE-EFFICIENCY.md`.
- **029/038 — evidência visual:** as capturas não foram promovidas. A de 029
  tem a área de detalhes coberta; a de 038 é anterior à captura já presente na
  main. Os arquivos locais foram preservados nos snapshots de recuperação.

Os testes específicos de BIOS e projeção multidisco passaram (6/6), assim como
`tools/project_status.py check`. A execução integral registrada em
`INTEGRAL-TESTS.log` passou com 6.294 testes aprovados e 47 ignorados.

## Recuperação antes da remoção das árvores

Antes da remoção, cada ponta de worktree foi fixada em
`refs/archive/worktrees/2026-09-26/<nome>/tip`. As 11 árvores com alterações
locais também receberam snapshots Git em `.../<nome>/working-tree`. Assim, os
commits não integrados continuam recuperáveis e os arquivos versionáveis
locais não dependem mais dos diretórios removidos.

O bundle completo está na área local de recuperação:

`centralization-2026-09-26/steamzero-centralization-2026-09-26.bundle`

Ele contém 708 refs e passou por `git bundle verify`. Foi restaurado em um
repositório bare temporário: 707 refs foram importadas, os 11 snapshots locais
foram encontrados e `git fsck --full --no-dangling` terminou limpo.

Alterações locais geradas sob `.tmp/aura-session-osd-gate` (563 arquivos,
aproximadamente 31 MiB) foram excluídas dos snapshots de código; são homes
isolados de testes, não arquivos-fonte. A configuração local foi transferida
para o checkout canônico com permissão privada. Dados de VM, sessão e artefatos
locais foram mantidos fora de Git no diretório de arquivo da centralização.
Material de usuário privado também foi preservado fora do repositório, com
permissões restritas.

O clone de referência EmuDeck estava limpo em
`71d4cdc7c4dc121b99b9b1f8684cbda0f56b7fca` e aponta para
`https://github.com/dragoonDorise/EmuDeck.git`; ele é reproduzível por clone do
repositório e checkout do SHA registrado.

## Estado terminal do disco

- `git worktree list --porcelain` contém apenas `Canonical/2026-09-21`. Foram removidos 48
  worktrees secundários após a verificação de suas refs/snapshots.
- `Project Backup/` e os clones de referência saíram da árvore do projeto. O
  projeto tem um único checkout; a área de recuperação externa está descrita em
  `centralization-2026-09-26/UNREGISTERED-MATERIAL.md`.
- Os materiais fora do worktree list não foram apagados por engano: 17 entradas
  Codex, 2 bundles SD e 3 referências foram movidos intactos para essa área.
  O clone EmuDeck, público, limpo e reproduzível por SHA, foi removido.
- O `status-check` e os seis testes específicos passaram novamente no checkout
  único. A branch foi publicada no PR #237 contra `main`; o CI remoto está
  validando o head publicado. Nenhum merge foi executado.

## Limite desta etapa

Remover worktrees não integra automaticamente todos os seus branches à main.
As decisões das sete frentes acima foram reconciliadas; as demais pontas não
integradas permanecem preservadas nos refs locais e no bundle para revisão a
partir do único checkout. Nenhum branch remoto foi apagado, nenhum push ou merge
foi executado nesta limpeza.
