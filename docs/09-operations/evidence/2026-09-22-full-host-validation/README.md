# Auditoria física completa do host — 2026-09-22

> Complemento orientado à jornada UX, first-run, fade, interface live e
> tratamento real de nomes/ROMs: [adendo de diagnóstico de 2026-09-22](../2026-09-22-ux-deep-dive/README.md).

## Escopo e identidade

- Release instalada: `2.0.0rc1-504d10b14485`
- Commit de código executado: `504d10b144851b70eab99d1fad7110ae34e88f84`
- Wheel: `d55ea7a2ae97accc2aaf8a98abbbcf67468f648ae486dd9712054489d3fe2476`
- Host: Steam Deck LCD, Wayland, `800×1280`, 60 Hz, escala 1.35
- Doctor final: `degraded`, sem blockers, pending, stale ou órfãos
- State audit final: limpo; sessões físicas finais: `closed=69`, `failed=22`, nenhuma sessão ativa

O teste usou a rota instalada `steamzero emulation launch`, os executores
instalados e o State Store real. ROMs não foram movidas, extraídas, convertidas
ou sobrescritas. Cada processo criado para a matriz foi identificado pelo PID e
PGID observado e encerrado pelo PGID exato ao terminar a observação.

## Scan real da biblioteca

Job `01M34E00S3ESQBVMV32YZAQ4K3`, concluído com sucesso:

| Métrica | Resultado |
|---|---:|
| arquivos encontrados | 16.513 |
| jogos catalogados pelo scan | 1.843 |
| jogos expostos no workspace | 1.825 |
| updates | 102 |
| DLCs | 144 |
| não identificados | 0 |
| erros | 0 |
| incompatíveis | 1.342 (`archive-platform-unknown`) |
| ignorados | 13.082 (`unsupported-format`) |
| roots | 2 |

A diferença entre `games=1843` do scan e `1825` no workspace é a projeção que
recusa conteúdo não jogável/sem readiness. Isso não é promoção de arquivo
incompatível a jogo executável.

Plataformas com conteúdo observado no workspace: Switch, Game Boy/Color/Advance,
NES/Famicom, SNES, Mega Drive, PlayStation, GameCube/Wii, Master System, Game
Gear, ZX Spectrum, Amiga, 3DO, PlayStation 2, Dreamcast, Nintendo DS, Nintendo
3DS, Wii U, PlayStation 3, Xbox, Xbox 360, Saturn, Neo Geo CD, PlayStation Vita,
Sharp X68000 e PlayStation 4.

## Componentes e executores

Foram verificados todos os 33 componentes instalados individualmente com
`component verify`: todos retornaram `ok=true`, `state=installed` e
`verified=true`.

| Situação | Componentes |
|---|---|
| instalados e verificados | 16 emuladores/engines + 17 cores libretro |
| ausentes | `vita3k`, `sunshine` |
| degradado | `xenia-canary`: manifesto do deployment divergiu sem mudança na fonte fixada |
| fallback testado | `citron`, `ryubing` e `sharpemu` iniciaram pelo `component launch`; o wrapper publicou PID, mas o app não permaneceu observável após 2 s |

O `component stop` declarou corretamente que parada de Flatpak não é gerenciada
por essa ação; os processos de teste foram encerrados pelo PGID conhecido e não
ficaram resíduos.

## Matriz de launch físico

`spawn` significa que o preflight foi aceito, o executor criou um processo real
e o processo foi observado por pelo menos dois segundos. Não significa que um
jogo chegou a uma partida interativa; BIOS, firmware e controles continuam
classificados separadamente.

| Plataforma | Executor | Resultado físico | Diagnóstico |
|---|---|---|---|
| switch | Eden | spawn, encerramento limpo | título executável; processo saiu com código 0 |
| nintendo-handheld | RetroArch/mGBA | spawn, encerramento limpo | runtime e core presentes |
| nes-famicom | RetroArch/Mesen | spawn, encerramento limpo | runtime e core presentes |
| snes | RetroArch/Snes9x | spawn, encerramento limpo | runtime e core presentes |
| mega-drive | RetroArch/Genesis Plus GX | spawn, encerramento limpo | runtime e core presentes |
| playstation | DuckStation | spawn, encerramento limpo | processo terminou com código 1; requer observação visual/interativa adicional |
| nintendo-console | Dolphin | spawn, encerramento limpo | rota GameCube/Wii criada |
| master-system | RetroArch/Genesis Plus GX | spawn, encerramento limpo | runtime e core presentes |
| game-gear | RetroArch/Genesis Plus GX | spawn, encerramento limpo | runtime e core presentes |
| zx-spectrum | RetroArch/Fuse | spawn, encerramento limpo | runtime e core presentes |
| amiga | RetroArch/PUAE | bloqueado antes do spawn | archive não materializado |
| three-do | RetroArch/Opera | spawn, encerramento limpo | BIOS `panafz1.bin` ainda é pré-condição para gameplay |
| playstation-2 | PCSX2 | spawn, encerramento limpo | processo criado; gameplay depende do conteúdo/controle |
| dreamcast | Flycast | spawn, encerramento limpo | processo criado |
| nintendo-ds | melonDS | spawn, encerramento limpo | processo criado |
| nintendo-3ds | Azahar | spawn, encerramento limpo | processo criado |
| wii-u | Cemu | spawn, encerramento limpo | processo criado |
| playstation-3 | RPCS3 | bloqueado antes do spawn | firmware oficial `PS3UPDAT.PUP` ausente |
| xbox | xemu | bloqueado antes do spawn | arquivos `flash`, `mcpx` e `hdd` ausentes |
| xbox-360 | nenhum | bloqueado antes do spawn | plataforma planejada, sem perfil de launch/emulador instalado |
| sega-saturn | RetroArch | bloqueado antes do spawn | core `mednafen_saturn` ausente |
| neo-geo-cd | RetroArch | bloqueado antes do spawn | core `neocd` ausente |
| playstation-vita | nenhum | bloqueado antes do spawn | plataforma planejada, `vita3k` ausente |
| x68000 | RetroArch | bloqueado antes do spawn | archive não materializado |
| playstation-4 | shadPS4 | spawn, encerramento limpo | processo publicou PID, mas encerrou antes de permanecer observável |

As outras 39 plataformas declaradas não tinham um jogo projetado para launch
físico nesta sessão, ou são cloud/cores sem executor. A matriz canônica continua
sendo a fonte da lista completa de 64 plataformas; `geforce-now`,
`xbox-cloud-gaming` e `amazon-luna` ficaram em `attention` porque conta,
assinatura, região, catálogo e rede não são verificáveis localmente.

## Sessão, pausa, save-state, bezel e multi-disk

Foi executado um teste dentro do mesmo processo controlador para SNES:

- `listPeripherals`: aceito; bezel `aura-default` selecionado, compatível e
  disponível como `asset://bezels/aura-bezel.svg`.
- `pause`: aceito, estado `suspended`.
- `resume`: aceito, estado `running`.
- `listSaveStates`: inicialmente vazio com motivo explícito.
- `saveState(slot=31)`: aceito; arquivo `.state31` e thumbnail foram publicados.
- `listSaveStates` após salvar: slot 31 disponível.
- `loadState(slot=31)`: aceito.
- `listDiscs`: respondeu `unavailable` com motivo “jogo não declara um conjunto
  multi-disc”.
- Configuração RetroArch real confirmou `network_cmd_enable`, porta `55355`,
  `savestate_directory` gerenciado e `input_overlay_enable=true` apontando para
  o bezel AURA.

Não existe `.m3u` nem linha em `multi_disc_set`/`multi_disc_disc` no host; uma
troca de disco real não pôde ser executada sem inventar conteúdo do usuário.
Os contratos e a materialização multi-disc passaram nos testes automatizados,
mas o critério físico `swapDisc` permanece não certificado.

### Lacuna crítica descoberta no lifecycle

Quando o launch é executado diretamente pela CLI, o processo do emulador sobe,
mas o processo controlador termina cedo demais: o socket de controle pode ficar
como arquivo de 0 bytes e a linha de sessão permanecer `running` até o próximo
launch chamar o reaper. Isso foi reproduzido no primeiro NES (`PID 218632`),
quando `listPeripherals` expirou e os pedidos seguintes receberam
`Connection refused`. A matriz posterior limpou as sessões pelo reaper e terminou
sem sessão ativa, mas a rota CLI não é prova de controle interativo persistente.

## Temas e editor

Estado físico atual:

- Tema ativo restaurado: `AURA ES-DE Physical`, versão `1.0.0`.
- O resolvedor publicou 60 tokens, 3 media recipes e 3 effects; o tema ativo não
  publica scene layouts/containers/motion completos.
- Quatro temas de usuário ES-DE aparecem inválidos:
  `org.esde.iconic`, `org.esde.nso-menu`, `org.esde.playstation-x` e
  `org.esde.xmb-menu`.
- Os temas builtin AURA, SteamZero, Steam Deck e asset-recipes produziram planos
  transacionais válidos.
- AURA foi aplicada no host e depois revertida pelo rollback da operação; o
  status final voltou ao tema anterior e `pendingOperations=0`.
- Harnesses QML do editor AURA, import, Studio Canvas e asset recipes carregaram
  com `qml6` em offscreen e retornaram código 0.
- `check_scene_esde_view.qml` e `check_theme_scene_preview.qml` não são executáveis
  como smoke simples com `qml6` porque permanecem em event loop; o
  `qmltestrunner` disponível no host retornou código 1 sem relatório. A cena
  ES-DE e a prévia, portanto, não foram promovidas a prova física nesta sessão.
- Testes de editor/importação/cenas/sessão/ROM: **291 passed**.
- Matriz adicional de emuladores, plataformas, launch, importadores e catálogo:
  **654 passed, 44 skipped**. Skips são declarados para Flatpak fixo, cores que
  não lançam sozinhos e capacidades `configure` não declaradas.

## RetroFE, ES-DE e tema nativo

`frontends status` no host real retornou:

- SRM: `missing`, diretório de manifests ausente.
- ES-DE: `missing`, `es_systems.xml` ausente.
- RetroFE: nenhum diretório/configuração local encontrado na busca read-only.

Logo, os temas RetroFE e ES-DE não foram “lançados” como frontend real nesta
release: faltam as próprias instâncias dos frontends. O tema nativo SteamZero/AURA
foi resolvido, aplicado e revertido pelo fluxo governado, mas a cena ES-DE não
foi renderizada fisicamente.

## ROMs, nomes, identidade e controles

- O scan terminou com `unidentified=0` e 1.843 itens catalogados.
- Nomes de jogos com regiões, traduções, pontuação e formatos foram normalizados
  em amostras reais; a projeção expõe nomes legíveis e IDs estáveis.
- PS5 teve um arquivo no scan, mas o workspace não expôs jogo lançável; Vita e
  Xbox 360 ficaram `planned`/`no-reader` ou sem emulador.
- Perfis de controle foram consultados. SNES e Switch possuem
  `standard-gamepad` selecionado; NES, PlayStation e GameCube/Wii permanecem
  `unverified` sem perfil selecionado.
- Doctor físico confirma `deckInputKeys=false`: chegada de botões do Deck como
  teclas não foi comprovada. Isso impede afirmar execução harmônica por controle
  físico, mesmo nos launches que criaram processo.
- Health está `unchecked` para 1.145 itens; apenas um jogo possui hash verificado
  no último health run. Isto não é falha do scan, mas é uma lacuna de integridade
  de conteúdo.

## Lacunas abertas e prioridade

1. Corrigir o ownership do watcher/socket na rota CLI para que pausa, resume,
   save-state, bezel e recovery permaneçam acessíveis após o retorno do comando.
2. Fazer uma prova visual/interativa por plataforma, não apenas spawn, começando
   por DuckStation, Dolphin, PCSX2, Switch, 3DS, DS, Cemu e shadPS4.
3. Obter do operador firmware/BIOS legítimos para 3DO, PS3 e Xbox; nenhum foi
   baixado ou criado automaticamente.
4. Materializar um conjunto multi-disc legítimo com `.m3u` gerenciado e repetir
   `listDiscs`/`swapDisc`/fade.
5. Instalar/configurar as instâncias reais de ES-DE e RetroFE antes de declarar
   seus temas lançáveis.
6. Selecionar/provar perfis de controle NES, PlayStation e GameCube/Wii e resolver
   o provider de entrada do Deck (`deckInputKeys=false`).
7. Corrigir ou substituir o smoke QML das cenas ES-DE/preview, que não encerra
   corretamente com `qml6` e falha silenciosamente no `qmltestrunner` do host.
8. Revalidar conteúdo Vita/PS5/Xbox 360 e os 1.342 archives sem classificação;
   não extrair nem alterar esses arquivos fora de plano governado.

Esta evidência não declara que todas as plataformas “funcionam”: ela registra
cada plataforma com conteúdo observável, cada bloqueio de preflight e os limites
exatos do que foi fisicamente provado.
