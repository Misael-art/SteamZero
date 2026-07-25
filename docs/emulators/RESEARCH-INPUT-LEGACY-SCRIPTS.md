# Entrada de pesquisa — capacidades observadas em scripts legados

Proveniência de pesquisa para o ciclo de estudo, na forma que o §1 da
`EMULATOR-PORTING-DIRECTIVE` já autoriza para documento de planejamento: aqui se
registra **a capacidade e o padrão**, nunca o nome, o código ou a estrutura de
diretórios de origem no artefato entregue. O gate `make independence` varre
`src/steamzero/**/*.py` e `pyproject.toml`; `docs/` está fora do escopo do gate,
mas o artefato de produto continua proibido de referenciar a origem (ADR-0019).

Levantado em 2026-07-24 a partir de uma árvore de scripts de referência local.
Cada item abaixo é **capacidade observada funcionando**, não hipótese — mas a
portabilidade para a arquitetura do SteamZero é que precisa de spike.

---

## C1 — Config por jogo endereçada por serial (P1)

**O padrão observado.** Três emuladores de disco expõem override de configuração
por jogo em arquivo, endereçado pelo **serial do título**, não pelo nome nem pelo
hash do arquivo:

| Emulador | Caminho de override | Chave |
|---|---|---|
| DuckStation | `GameSettings/<serial>.ini` | `SLUS-00594` |
| PCSX2 | `inis/GameSettings/<serial>.ini` | `SLUS-20946` |
| Dolphin | `GameSettings/<serial>.ini` | `RMGE01` |

A escrita é INI idempotente que **preserva as demais seções** e cria diretórios
ausentes — exatamente a invariante "parser estrutural com diff, nunca
reserialização cega" já exigida pelo SteamZero.

**Por que importa para o estudo.** O SteamZero já tem adapters commitados de
`duckstation` e `dolphin`. A superfície de config-per-game desses dois sistemas
**não precisa ser inventada** — ela existe no emulador e é endereçável por
arquivo. Isso muda a §4 dos dossiês de `ps1` e `gamecube-wii` de "pesquisar" para
"consumir contrato conhecido".

**O que o SteamZero acrescenta.** A árvore de referência carrega 14 perfis
curados à mão. Curadoria manual não escala e envelhece. A oportunidade é a mesma
do `nes.md` §4: consumir uma base de compatibilidade como **dado** com licença
compatível, em vez de manter lista própria.

**Ganchos de detecção de root** (ordem observada): `$XDG_CONFIG_HOME/<emulador>`
e depois o caminho Flatpak. Vale para o `detect`/`status` dos adapters.

## C2 — Dois ecrãs físicos para emuladores de dois ecrãs (P4) — **o achado mais forte**

**A restrição arquitetural, verificada — e confirmada upstream em 2026-07-25:**
o compositor do Game Mode é single-output e single-focus, e **continua sendo**.
As issues canônicas do Gamescope seguem abertas: #645 "Select monitor for
gamescope to appear on" (2022, última atividade 2026-06-28) e #737 "unable to
span or stretch across multiple monitors" (2023). Não há flag de seleção de
monitor nem spanning na série 3.16.x.

O compositor do Desktop Mode (KWin/Wayland) é multi-output de verdade e tem
regra de janela por "Screen". **Portanto este recurso é Desktop Mode apenas** —
e isso não é limitação temporária a contornar, é propriedade do compositor.
Índices de tela resolvidos dinamicamente via `kscreen-doctor`, para sobreviver a
reordenação de saída.

Capacidades observadas por sistema:

| Sistema | Emulador | Modo |
|---|---|---|
| Wii U | Cemu | GamePad abre como **2ª janela** ("Separate GamePad View", `PadViewFrame`). Chaves em `~/.config/Cemu/settings.xml`: `open_pad`, `pad_position`, `pad_size`, `pad_maximized` |
| 3DS | Azahar | layout "Separate Windows" em `qt-config.ini`, seção `[Layout]`, chave `layout_option`. ⚠️ **O valor correto é `4`, não `5`** — o enum é `Default=0, SingleScreen=1, LargeScreen=2, SideScreen=3, SeparateWindows=4, HybridScreen=5, CustomLayout=6`. O `5` do script legado é HybridScreen |
| PSP | PPSSPP | duas instâncias posicionadas em duas telas |
| GBA | mGBA | duas instâncias posicionadas — **base para link cable** (P3) |
| NDS | melonDS | **TEM, sim.** Desde a linha 1.0: "View → Open New Window" abre outra janela da mesma instância, cada uma com *Screen Sizing* independente (Top/Bottom Only), layout salvo entre sessões |

> **Correção de 2026-07-25.** A versão anterior desta tabela afirmava que o
> melonDS "não tem" modo de duas janelas, e citava `layout_option=5` para o
> Azahar. Ambos vinham dos comentários do script legado e **ambos estavam
> errados**: o melonDS ganhou multi-janela na 1.0, e o `5` é HybridScreen.
> Lição de método: comentário de script de referência é *hipótese datada*, não
> fato — o script foi escrito antes da 1.0 do melonDS e envelheceu em silêncio.
>
> Limitações reais do Azahar (fonte: `azahar-emu/azahar#1485`, aberta desde
> 2025-11-28): não lembra posição/maximização entre sessões e não tem fullscreen
> dedicado por monitor. Separate Windows não combina com Custom Layout (#251).
> Chave exata do `melonDS.ini`: `NÃO ENCONTRADO`.

**Por que ninguém usa.** Exige regra de janela do compositor, resolução de
índice de conector e conhecimento de qual emulador aceita segunda janela. É
precisamente o tipo de fricção que o SteamZero existe para remover.

**Impacto na fila:** informa diretamente `3ds`, `nds`, `psp` (Onda 2) e `wiiu`
(Onda 3). O dossiê de `wiiu` tem aqui o seu momento mágico praticamente pronto:
o GamePad de verdade, na tela do Deck, com o jogo na TV.

**Casa com FM-27.** O `nes.md` §10 já registrou que a UI Avalonia do Mesen não
renderiza sob o compositor de Game Mode. Somando os dois: **o compositor do Game
Mode é uma restrição transversal de primeira classe**, não um detalhe por
emulador. Vale um FM próprio e uma capability declarada no manifesto de
plataforma, em vez de ser redescoberto sistema a sistema.

## C3 — O giroscópio está sendo jogado fora (P2) — **oportunidade, não portação**

A árvore de referência **filtra explicitamente** dispositivos de
`motion sensor|imu|accelerometer|gyroscope` para fora da enumeração de joysticks.
Ou seja: o IMU do Deck é tratado como ruído a descartar.

**Consequência para o estudo:** o mapa gyro→pistola de luz proposto em
`nes.md` §5 não tem precedente para portar — é território inexplorado. Isso
eleva o risco (não há prova de que funciona) e o valor (ninguém fez). Continua
`[validar no spike]`, agora com a nota de que o spike é de fato exploratório.

## C4 — Capacidades já cobertas pelo SteamZero (registrar e não duplicar)

Observadas na árvore de referência e **já resolvidas** no produto — nenhum WI
novo: store de BIOS/keys, conversão NSZ, índice e rename de mídia, atalhos Steam,
biblioteca/scan, conteúdo compartilhado, integração de frontends.

## Ações propostas para o ciclo de estudo

1. Reescrever a §4 dos dossiês `ps1` e `gamecube-wii` para consumir o contrato
   C1 em vez de pesquisar do zero.
2. Promover a restrição de compositor (C2 + FM-27) a **item transversal**: uma
   capability de plataforma, não um achado por sistema.
3. Marcar `wiiu` e `3ds` como candidatos a momento mágico de alto impacto (C2).
4. Manter o spike de giroscópio como exploratório, com risco declarado (C3).
