# Evidência física — Launcher P0 — 2026-09-05

Release ativa comprovada antes da captura: `2.0.0rc1-bf23fd7dd62f`, commit
`bf23fd7dd62f3c161e9375b7ccf253b933834605`. A ativação veio do bundle CI/run
`33964880293`; o plano registrou rollback para `2.0.0rc1-cf9c47e7b55b` e
preservação do estado do usuário.

## Evidências ordenadas

- `01-baseline.png`: abertura física da home, com o foco no cartão real
  `3D Alien Maze (Homebrew) (SMS) 1.0`.
- `02-entrega-funcional.png`: página física do jogo real, aberta com Enter e
  com a ação `Jogar` focada.
- `03-recuperacao.png`: retorno físico à home após encerrar o emulador, com o
  mesmo cartão ainda focado.

As três imagens principais são capturas do compositor real, feitas sem clique
de mouse. O arquivo `PHYSICAL-VALIDATION.json` registra PID/janela, hashes e
as teclas enviadas. O manifesto `MANIFEST.json` também contém o contexto QML,
hashes, commit, origem live e snapshot do host para as 55 capturas offscreen
complementares. Nenhuma imagem persistida contém tokens ou dados pessoais.

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

- `PHYSICAL-VALIDATION.json`: Enter abriu a página do jogo, Enter iniciou o
  RetroArch real, Alt+F4 encerrou-o e o Launcher retornou ao mesmo cartão; não
  restaram processos do teste.

## Erro controlado e recuperação

Uma tentativa de atualização com o checkout sujo pela própria pasta de
evidências foi recusada de forma controlada (`update recusa worktree suja`), sem
chamada privilegiada. Depois, o fluxo válido concluiu a ativação, convergência
idempotente, smoke offscreen e preservação de estado. A validação física
confirmou sucesso e retorno; o aviso de Steam indisponível continua coberto por
`steam-area-library.png`. Não foi feito reboot: essa ação continua exclusiva
do operador.
