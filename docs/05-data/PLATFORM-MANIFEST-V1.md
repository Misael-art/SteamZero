# PLATFORM-MANIFEST-V1 — registry declarativo de plataformas

## Objetivo

`platform-manifest-v1` é a fonte de apresentação e capacidade da central de
emulação. QML recebe plataformas, áreas, ações, emuladores candidatos, formatos
de mídia, controles, timing e presets pelo snapshot; nomes de plataforma não
escolhem funções Python nem comandos.

O registry embutido cobre:

- Nintendo Switch;
- GB/GBC/GBA;
- NES/Famicom;
- SNES;
- Mega Drive/Genesis;
- Arcade/CPS/Neo Geo/MAME;
- PlayStation;
- GeForce NOW, Xbox Cloud Gaming e Amazon Luna.

## Honestidade de capacidade

Estados declarativos são `ready`, `planned` e `unavailable`. `ready` significa
que existe composição local capaz de verificar o estado, não que ela foi
confirmada neste host. A projeção inicial converte esse caso em `unverified`.
`planned` nunca habilita ação e sempre carrega a dependência no `detail`.

Timing usa `unknownFallback: unknown-explicit`: região, padrão ou refresh ausente
não pode ser convertido silenciosamente em NTSC, PAL ou percentual sintético.
Presets ainda pertencentes ao track R permanecem `planned`.

## Integridade semântica

Além do JSON Schema draft 2020-12, o loader rejeita:

- IDs, actions ou precedências duplicadas;
- área que referencia capability ausente;
- payload cloud em plataforma emulada ou emulador em plataforma cloud;
- URL sem HTTPS, com credencial embutida, porta diferente de 443 ou hostname
  fora da allowlist exata.

Os manifestos são dados empacotados no wheel. Não há descoberta de código,
hooks, shell ou diretório de plugins.

Desde F6, cada ID em `controls.profiles` precisa existir no registry
`retro-input-profile-v1`, declarar a plataforma correspondente e respeitar seu
`maxPlayers`. O manifesto descreve aplicabilidade; seleção, rotação e rollback
ficam no contrato de input.

## Cloud

F5 registra somente identidade e allowlist; lançamento e atalhos reversíveis
pertencem ao A5 e permanecem desabilitados. As origens oficiais verificadas em
2026-07-23 são:

- `https://play.geforcenow.com/`;
- `https://www.xbox.com/play`;
- `https://luna.amazon.com/`.

Assinatura, disponibilidade regional, catálogo e compatibilidade variam fora do
controle do SteamZero e nunca são alegados pelo manifesto.

## Assets

Cada plataforma possui um fallback SVG diferente, original do SteamZero e
licenciado sob GPL-3.0-or-later. O registry referencia apenas caminhos relativos
fechados em `../assets/<slug>.svg`; os testes confirmam unicidade e presença.
