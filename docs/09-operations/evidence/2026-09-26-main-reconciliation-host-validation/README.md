# Validação no host — reconciliação de 2026-09-26

## Artefato e proveniência

- Release instalada pelo fluxo governado: `2.0.0rc1-e2af2562ebba`.
- Código-fonte: `e2af2562ebba3acb6ebd7ed27806ca785816e20c`.
- Run `push` verde: [36233353596](https://github.com/Misael-art/SteamZero/actions/runs/36233353596), 8 jobs concluídos com sucesso.
- Wheel SHA-256: `de750abf8d6c0e8578142bbe09e762f962273137de18f74e65fb0d7bd82f8a00`.
- Rollback previamente verificado: `2.0.0rc1-621a3389db32`.

## Instalação e smoke

O preflight confirmou release anterior verificável, schema de dados 22
compatível, zero operações pendentes, daemon convergido e units ativas. A
instalação preservou os dados XDG e não alterou boot. A release ativa e o
`sourceCommit` foram conferidos no manifesto instalado.

A convergência confirmou a nova geração na primeira chamada e foi idempotente
na segunda (`attempts=0`, `restarted=false`). O smoke do instalador confirmou
`steamzero --version`, Doctor (`ok=true`, schema 22, zero operações pendentes),
socket, serviço, Game Mode e QML visível por cinco segundos.

## UI real

A UI foi iniciada pelo `/usr/local/bin/steamzero desktop ui` na sessão gráfica
do host. A captura [02-desktop-ui.png](./02-desktop-ui.png) registra a tela
real da release instalada. A janela abriu e renderizou a Central de jogos.
Ela mostra zero títulos publicados e alerta que nenhum perfil foi aplicado.

O perfil Amiga consultado permaneceu `unverified`, sem perfil ativo; o
componente `libretro-puae` está instalado. Como não há título publicado para
testar nessa sessão e o perfil está sem seleção, não tentei iniciar jogo nem
alterei biblioteca ou controles. Assim, a inicialização real da UI foi provada;
o preflight de BIOS e a projeção multidisco ainda não têm prova física neste
host. A auditoria de 22/09 também registra que nenhum conjunto Amiga M3U estava
materializado naquela medição.

Não houve mutação de conteúdo, perfil, estado XDG ou boot. Erro controlado,
recuperação de jogo e reboot físico não se aplicam a esta sessão. O relatório do
controlador manteve `physicalCertification=false`; a ativação da release não
equivale a certificação de boot ou de launch por hardware.

## Estado preservado

O Doctor permanece `degraded`, embora `ok=true`: seguem os avisos de nove
backups órfãos, nove journals órfãos, botões do Deck não reconhecidos como
teclas e permissão negada para inspecionar boot. Não foram apagados nem
corrigidos nesta tarefa. A release anterior segue instalada como rollback.
