# RETRO-INPUT-PROFILE-V1 — perfis de entrada retro

## Objetivo

`retro-input-profile-v1` descreve um layout sem conhecer arquivos de configuração
de emuladores. O contrato publica ID estável, revisão monotônica, plataformas
compatíveis, proveniência/licença, família do layout, limite de jogadores,
bindings semânticos e política de rotação.

O perfil não contém comandos, paths, nomes de módulo nem hotkeys específicas de
um emulador. A tradução `ação semântica → configuração concreta` pertence a um
adapter allowlisted e será composta incrementalmente no R6.

## Resolução e TATE

Orientações válidas são `landscape`, `portrait-left` e `portrait-right`. Perfis
que declaram `rotate-with-display` precisam publicar o hat direcional completo.
O resolver faz a transformação geométrica dos quatro direcionais e preserva os
demais bindings. Isso entrega a base determinística para o TATE do R4 sem
afirmar que display físico, gabinete ou controle especializado foram validados.

## Seleção e reversão

A seleção é materializada em
`$XDG_CONFIG_HOME/steamzero/input-profiles/active/<platform>/<scope>-<id>.json`.
Escopos aceitos: `global`, `platform`, `game`, `device` e `mode`.

O fluxo é:

1. validar plataforma, perfil, escopo e orientação;
2. resolver bindings e produzir preview G-FULL;
3. congelar fingerprint e emitir `planId` + `confirmToken`;
4. aplicar por staging/backup/rename atômico;
5. reabrir, revalidar o contrato e comparar os bindings resolvidos;
6. permitir rollback byte-idêntico, local e idempotente.

Arquivo ausente é `unverified`; arquivo inválido, grande demais ou inseguro é
`degraded` com causa. A seleção não afirma que o adapter já materializou o
perfil no emulador.

## Perfis empacotados no F6

- controle padrão e par de Joy-Con;
- Mega Drive de três e seis botões;
- arcade padrão;
- PlayStation digital e DualShock;
- gamepad cloud padrão.

Trackball, spinner, light gun, twin-stick, volante, paddle, luta, N64, DS/3DS,
Wii e sensores específicos permanecem no R6. Nenhum template externo foi
copiado; os perfis são originais do SteamZero sob GPL-3.0-or-later.
