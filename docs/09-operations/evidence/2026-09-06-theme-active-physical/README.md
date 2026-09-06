# Evidência física — semântica de tema ativo

Data: 2026-09-06 (America/Sao_Paulo)

Release observada: `2.0.0rc1-ca9ab317fc3c` (`2.0.0rc1`, commit de origem
`ca9ab317fc3cefdd4088add8cb58a55dc67f7cd2`). A Central foi aberta em processo
QML da release instalada e a sessão KDE permaneceu aberta; não houve reboot,
logout, encerramento do KDE ou encerramento do launcher existente.

## Provas

- `01-central-theme-catalog.png`: catálogo de temas publicado na Central, com
  5 temas e `567.3 MB em 4125 arquivos`.
- `02-theme-editor-active.png`: aba **Editar aparência** da Central. O tema
  ativo `Theme Engine — asset único` aparece destacado com `Já está em uso`;
  os temas alternativos exibem `Aplicar`.

## Jornada de ativação

1. `steamzero theme status --json` confirmou
   `org.steamzero.asset-recipes-demo` v`1.0.0` como ativo.
2. `steamzero theme plan --theme-id org.steamzero.asset-recipes-demo` retornou
   `theme plan: already-active`, `alreadyActive: true`, mensagem `Já está em
   uso`, sem plano nem confirmação pendente.
3. Para provar o caminho alternativo, foi criado um plano para
   `org.steamzero.default` v`1.1.0`; o plano foi aplicado com confirmação e
   imediatamente revertido pelo rollback da própria operação.
4. O status final voltou a `org.steamzero.asset-recipes-demo` v`1.0.0`.

O fluxo prova que “já ativo” é um no-op informativo na UI e na bridge, enquanto
um tema diferente segue plan→confirm→rollback. O token de confirmação não foi
persistido nesta evidência.

## Saúde e rastreabilidade

`steamzero doctor --json` após a jornada: versão `2.0.0rc1`,
`pendingOperations=0`, `orphanStaging=1` (aviso preexistente e não relacionado
à jornada). Os PIDs das janelas QML usadas nas capturas foram registrados em
`HOST-OBSERVATIONS.json`; o launcher pré-existente não foi tocado.
