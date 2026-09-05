# Evidência física — Launcher P0 — 2026-09-05

Release ativa comprovada antes da captura: `2.0.0rc1-bf23fd7dd62f`, commit
`bf23fd7dd62f3c161e9375b7ccf253b933834605`. A ativação veio do bundle CI/run
`33964880293`; o plano registrou rollback para `2.0.0rc1-cf9c47e7b55b` e
preservação do estado do usuário.

## Evidências ordenadas

- `01-baseline.png`: estado degradado controlado, com Steam indisponível e ação
  de diagnóstico visível.
- `02-entrega-funcional.png`: biblioteca editorial com acervo publicado e
  navegação Steam/emulação renderizada pela release ativa.
- `03-recuperacao.png`: retorno à biblioteca em grade após a navegação, sem
  travamento ou janela preta.

As três imagens são recortes nomeados de capturas live do mesmo ciclo; o
manifesto `MANIFEST.json` contém o contexto QML, hashes, commit, origem live e
snapshot do host para as 55 capturas geradas.

## Provas complementares

- `MANIFEST.json`: 55/55 capturas com conteúdo e contexto, QML próprio sem
  warnings, processo concluído sem crash.
- Journal governado:
  `/home/misael/.local/state/steamzero/release-automation/transactions/` —
  transação `bf23fd7dd62f-1788610658586285208.json`, fases
  `preflight-passed → approved → activated → convergence-passed → smokes-passed`.
- Versão CLI: `steamzero --version` retornou `2.0.0rc1`.
- Units read-only: `steamzero-core.socket` e `steamzero-core.service` ficaram
  `active`; daemon confirmou a release e o commit novos.
- Doctor read-only: `pendingOperations=0`, `staleJobs=0`, `deckInputKeys=true`;
  os avisos já existentes são `orphanStaging=1` e `bootDirect=unknown` por
  permissão de inspeção.

## Erro controlado e recuperação

Uma tentativa de atualização com o checkout sujo pela própria pasta de
evidências foi recusada de forma controlada (`update recusa worktree suja`), sem
chamada privilegiada. Depois, o fluxo válido concluiu a ativação, convergência
idempotente, smoke offscreen e preservação de estado. Não foi feito reboot:
essa ação continua exclusiva do operador.
