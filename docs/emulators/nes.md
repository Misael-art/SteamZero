# EMULATOR-DOSSIER — NES / Famicom

**Slug:** `nes` · **Onda:** 1 · **Status:** revisão · **Estudo:** 2026-07-24

> Regra deste documento: fato carrega fonte e data; hipótese carrega
> `[validar no spike]`. Limitações têm a mesma tipografia dos recursos.

---

## 1. Recomendação: emulador primário / alternativa

**Primário: MesenCE (Mesen Community Edition), 2.2.1, GPL-3.0.**

| Fato | Fonte | Consultado |
|---|---|---|
| `SourMesen/Mesen2` foi arquivado pelo dono em 2026-06-04 e está read-only; o README aponta o sucessor | https://github.com/SourMesen/Mesen2 | 2026-07-24 |
| `nesdev-org/MesenCE` é fork comunitário, 255 commits à frente do arquivo, 3.765 commits no total | https://github.com/nesdev-org/MesenCE | 2026-07-24 |
| Release estável corrente **2.2.1**; a nota de release declara "Mesen is becoming MesenCE... All development will occur in this new fork going forward" — a transição é reconhecida pelo autor original | https://github.com/nesdev-org/MesenCE/releases | 2026-07-24 |
| Licença GPL-3.0, herdada do upstream ("Mesen is available under the GPL V3 license", copyright 2014-2025 Sour) | https://github.com/SourMesen/Mesen2 (LICENSE/README) | 2026-07-24 |
| Manutenção ativa: commits recentes tocam Avalonia 12/.NET 10, precisão de CPU/APU/PPU do NES ("passes 11 more AccuracyCoin tests"), PAL e Famicom Disk System | https://github.com/nesdev-org/MesenCE/releases | 2026-07-24 |

**Este é o achado que muda a decisão óbvia.** Escolher "Mesen" por reputação
levaria a um repositório arquivado. O adapter deve apontar para MesenCE.

**Alternativa: RetroArch + core Mesen/Nestopia UE.** O SteamZero já tem manifesto
`retroarch.adapter.json` commitado, o que reduz custo de adapter a zero para um
caminho de fallback. `[validar no spike]` qual core RetroArch de NES está em
melhor estado de manutenção em 2026 e se ele expõe as mesmas superfícies de
periférico da §5 — o núcleo do argumento do MesenCE é a base de dados interna de
jogos, que um core libretro pode não carregar.

**Critério de desempate aplicado:** experiência no Deck. O MesenCE traz a base de
dados de jogos que configura periférico sozinho (§4) — é a diferença entre "Duck
Hunt abre e não funciona" e "Duck Hunt abre com a pistola já ligada".

## 2. Adapter: manifesto, canal, modelo de config + parser

Formato conforme `ADAPTER-MODEL.md` e os seis manifestos já commitados em
`src/steamzero/adapters/manifests/`.

- **`id`:** `mesence` · **`platforms`:** `["nes"]` — e, num WI posterior, também
  `snes`, `gb`, `gbc`, `gba`, `pce`, `sms`, `gg`, `ws`. O manifesto é
  multi-plataforma por natureza; o registry de plataformas associa por
  `adapterId` (`PLATFORM-MANIFEST-V1.md`).
- **`sources`:** AppImage Linux x64 das releases do GitHub, `versionPolicy:
  pinned` com `sha256` obrigatório — regra 2 do `ADAPTER-MODEL.md` e regra 2 das
  invioláveis da porting-directive. Segue o padrão de `eden`/`ryubing`/`citron`,
  que já pinam AppImage por URL + SHA-256.
- **Canal:** estável (2.2.1). Nightly **não** entra: o upstream distribui
  nightlies sem checksum publicado, e `versionPolicy: latest` só é admissível em
  canal dev com checksum no lockfile.
- **Dependência de runtime:** as releases declaram que **SDL2 precisa estar
  instalado manualmente** no Linux (fonte: notas de release 2.2.1, consultado
  2026-07-24). Isso é um `status`/`verify` do adapter, não um `install` — o
  SteamZero não instala pacote de distro. Ausência ⇒ ação some com causa
  (invariante §2.6).
- **`configFormat`:** `[validar no spike]` — a linha 2.x armazena configuração em
  JSON no perfil do usuário, mas o layout exato e a estabilidade entre 2.2.x
  precisam de inspeção antes de escrever parser. Enquanto não confirmado, o
  dossiê **não** afirma o formato.
- **Parser estrutural obrigatório:** nunca reserialização cega (invariante §2.2).
  Diff antes de aplicar, marcador de ownership, e o comportamento de FM-22 se o
  emulador reescrever o arquivo por fora.

## 3. BIOS / firmware / keys

**Não aplica como bloqueio.** O NES não exige BIOS. Duas exceções que o dossiê
registra:

- **Famicom Disk System** exige a BIOS do drive. `[validar no spike]` nome/hash
  canônico e se o MesenCE aceita o formato usual.
- Alguns mapeadores com áudio de expansão não precisam de BIOS.

Onde houver BIOS, vale `local-owned-dump-only` (invariante §2.5) e o store do
`domain/bios.py`, já existente. O produto valida o que o usuário tem; nunca
obtém, sugere ou baixa.

## 4. Config-per-game (P1) — **aplica, e é o pilar deste sistema**

| Fato | Fonte | Consultado |
|---|---|---|
| O Mesen tem opção "Automatically configure controllers when loading a game": ao carregar um jogo reconhecido pela **base de dados interna**, os controles apropriados são conectados sozinhos. O exemplo do próprio manual é Duck Hunt conectando um Zapper na porta 2 | https://www.mesen.ca/docs/configuration/input.html | 2026-07-24 |

⚠️ Essa documentação é da versão **0.9.9, "Last Updated: 2020-02-01"** — é a
linha Mesen 1, NES-only. `[validar no spike]` que a base de dados e a
auto-configuração sobreviveram na linha 2.x/MesenCE e como são expostas em
arquivo.

**Como o SteamZero remove a fricção:** a base já existe dentro do emulador, mas
está atrás de um checkbox que o usuário precisa achar — e, em Game Mode, atrás
de um menu que **não renderiza** (§10). O SteamZero liga a opção por arquivo no
momento da instalação e o usuário nunca vê o problema.

## 5. Inputs exóticos (P2) — **aplica**

Mapa proposto. Cada linha é hipótese de design até o spike de input medir
latência e precisão no hardware.

| Original | Hardware do Deck | Nota |
|---|---|---|
| Zapper (pistola de luz) | **giroscópio** para mira + gatilho no R2 | O manual do Mesen tem seção dedicada "Zapper / Light Gun" (fonte §4). É o caso de uso que justifica o giroscópio sozinho |
| Power Pad (tapete) | mapeamento para botões/trackpad | `[validar no spike]` se o MesenCE expõe o Power Pad |
| Arkanoid Vaus (paddle) | **trackpad** como paddle absoluto | Casa com P2 "trackpads = paddle/spinner" |
| Microfone do 2º controle do Famicom | microfone do Deck | Mesen expõe `Console Type: NES × Famicom` porque os acessórios diferem (fonte §4). É P4 tanto quanto P2 |
| Family BASIC keyboard | teclado virtual do SteamZero | Já existe superfície de teclado no produto |
| Datach / barcode | — | `[validar no spike]` |

## 6. Multiplayer (P3) — **aplica**

| Modo | Fato | Fonte |
|---|---|---|
| 4 jogadores locais | NES via acessório **Four Score**; Famicom via **Four Player Adapter** na porta de expansão — o Mesen expõe os dois separadamente | manual de input, consultado 2026-07-24 |
| Netplay | O manual 0.9.9 lista **Netplay** entre as ferramentas | https://www.mesen.ca/docs/ (índice), 2026-07-24 |

`[validar no spike]` se o netplay do Mesen 1 sobreviveu ao MesenCE 2.2.1, qual o
transporte e se tem rollback. **Limitação honesta:** netplay de emulador clássico
costuma ser lockstep sensível a latência; não prometer paridade com rollback
moderno antes de medir.

Transporte da Fase 7: depende da diretiva `COOP-ONLINE`, que **não existe no
repositório** (D3 do ledger). O WI proposto na §14 declara essa dependência em
vez de inventá-la.

## 7. Periféricos / expansões (P4/P5) — **aplica**

- **P4:** Zapper, Power Pad, Arkanoid, microfone do Famicom, Family BASIC
  keyboard — todos acima. A UI os expõe como *escolha de periférico por jogo*,
  não como configuração global.
- **P5 — áudio de expansão:** o NES tem chips de som em cartucho (VRC6, VRC7,
  N163, FME-7, MMC5, Sunsoft) que a maioria dos usuários nunca ouve porque o
  hardware americano não os reproduzia. As notas de 2.2.0 mencionam trabalho em
  **EPSM** e no mapper **Rainbow** (fonte: releases, 2026-07-24), o que indica
  cobertura viva de mapeadores exóticos. `[validar no spike]` a lista completa.
- **P5 — modelo de máquina:** `Console Type: NES × Famicom` é seleção por jogo
  (fonte §4), e as notas 2.2.0 citam melhoria de precisão **PAL**. Região e
  modelo entram no manifesto de plataforma com `unknownFallback:
  unknown-explicit` — nunca converter ausência em NTSC silenciosamente
  (`PLATFORM-MANIFEST-V1.md`).

## 8. Mods / patches (P6) — **aplica**

- **HD Packs**: o Mesen tem seção inteira de documentação dedicada
  (https://www.mesen.ca/docs/, consultado 2026-07-24). Substituição de texturas
  em NES é o tipo de recurso que "quase ninguém usa porque dá trabalho".
- **Cheats** e **Movies** também são ferramentas de primeira classe no índice.
- **Patches BPS**: o changelog do repositório arquivado cita "BPS: Fixed
  potential crashes when applying BPS patches" — há suporte a patch soft.

Supply chain: HD Packs são conteúdo de terceiro. Entram pelo caminho de
componente transacional com sha256 e rollback (invariantes §2.1 e §2.3); nunca
por download livre do adapter.

## 9. "Como era" selecionável (P7) — **aplica**

- **Precisão como recurso:** 2.2.0 declara "Improved CPU/APU/PPU accuracy (passes
  11 more AccuracyCoin tests)" e "Improved PAL emulation accuracy" (fonte:
  releases, 2026-07-24). O SteamZero pode oferecer "como era" com lastro.
- **Ganchos WI-R:** integer scale em 1280×800 — o NES a 256×240 cabe em **3×**
  (768×720) com barras, e 240×3 = 720 ≤ 800. A tabela normativa de escala
  inteira já existe no repositório (commit `2965e6f`), então este dossiê
  **consome** o contrato em vez de propor outro.
- Shader CRT, timing autêntico (60.0988 Hz NTSC) e overscan por região: candidatos
  a preset declarativo, `planned` até existir composição que verifique.

## 10. Robustez

**A falha mais importante deste sistema não é de emulação, é de compositor.**

| Fato | Fonte | Consultado |
|---|---|---|
| "Due to Gamescope (SteamOS' compositor) not handling Avalonia UI's popups very well... Mesen's menus for settings are not working through Gamescope unless running Mesen through running KDE Plasma's Desktop through a script" | https://github.com/nesdev-org/MesenCE/blob/master/SteamOS.md | 2026-07-24 |

O upstream recomenda contornar ligando atalhos de teclado aos botões traseiros
L4/R4/L5/R5 (mesma fonte). Isso é exatamente o que o contrato
`retro-input-profile-v1` já modela.

**FM propostos (aditivos, a partir de FM-27 — ver D1 do ledger):**

| FM | Condição | Detecção | Resposta exigida |
|---|---|---|---|
| FM-27 | UI do emulador não renderiza sob o compositor de Game Mode | capability de sessão + emulador com toolkit conhecido | SteamZero configura por arquivo e **não** oferece "abrir configurações" em Game Mode; a ação some com causa, nunca abre uma janela invisível |
| FM-28 | Dependência de runtime da distro ausente (SDL2) | `verify` do adapter | ação de launch some com causa e instrução; nunca falha silenciosa no meio do boot do jogo |

- **Saves/estados:** `[validar no spike]` onde a linha 2.x grava saves e
  savestates. Entram no domínio Saves central — o adapter **não** faz backup de
  saves (`ADAPTER-MODEL.md`: "backup/restore: dados do próprio componente; nunca
  saves").
- **Recovery em SIGKILL:** `[validar no spike]`. O produto já tem injeção de
  falha por SIGKILL nos testes (`tests/failure_injection/`), então há bancada.
- **Performance no Deck:** NES é barato; **não** medido nesta sessão. Sem
  promessa numérica até o spike. O custo real a vigiar não é a emulação e sim os
  HD Packs e shaders.
- **Sandbox/Flatpak:** o caminho recomendado pelo upstream é AppImage, não
  Flatpak — coerente com os manifestos de Switch já commitados.

## 11. Momento mágico + critério de aceite

> **O usuário abre Duck Hunt em Game Mode, levanta o Deck e atira na tela com o
> giroscópio. Sem configurar nada.**

Critério de aceite mensurável:

1. Instalar NES pelo SteamZero, colocar `Duck Hunt` na biblioteca, lançar pelo
   Game Mode: o Zapper está ligado na porta 2 **sem intervenção** — a base de
   dados do emulador foi habilitada por arquivo pelo SteamZero.
2. O giroscópio move a mira; R2 dispara.
3. Em nenhum momento o usuário precisa abrir um menu do emulador — que, sob
   Gamescope, não renderizaria (§10).
4. Desinstalar reverte a configuração ao estado anterior, provado por teste de
   rollback com injeção de falha.

## 12. Riscos / licenças / supply chain

| Risco | Severidade | Mitigação |
|---|---|---|
| Adapter apontar para o repositório arquivado | **alta** — é o erro natural | O manifesto aponta `nesdev-org/MesenCE`; o dossiê registra o motivo |
| Fork comunitário jovem perder tração | média | Alternativa RetroArch mantida viva na §1; `versionPolicy: pinned` isola o produto de regressões upstream |
| Documentação oficial defasada (0.9.9, 2020) contra binário 2.2.1 | **alta para o planejamento** | Todo fato tirado dela está marcado `[validar no spike]` |
| HD Packs / cheats de terceiro | média | Componente transacional com sha256 e rollback; nunca download livre |
| GPL-3.0 | baixa | Compatível com o produto (GPL-3.0-or-later); redistribuição de binário não ocorre — o núcleo baixa da origem oficial |

**Questões para o operador:**

1. O `configFormat` do MesenCE precisa de inspeção de binário. Autoriza um spike
   que baixe o AppImage numa bancada isolada? O §9.2 do diretivo de estudo proíbe
   baixar/compilar emuladores neste ciclo — então isso é um WI, não estudo.
2. Um adapter multi-plataforma (MesenCE cobre 6 sistemas da Onda 1) muda a
   ordem das ondas? Estudar SNES/GB/GBA/PCE/SMS pode reaproveitar quase toda a
   §2 deste dossiê.
3. `COOP-ONLINE` não existe. O netplay do NES fica `planned` até ela existir?

## 13. Fontes

| # | URL | Consultado | Uso |
|---|---|---|---|
| F1 | https://github.com/SourMesen/Mesen2 | 2026-07-24 | arquivamento, licença, ponteiro para sucessor |
| F2 | https://github.com/nesdev-org/MesenCE | 2026-07-24 | estado de manutenção, contagem de commits |
| F3 | https://github.com/nesdev-org/MesenCE/releases | 2026-07-24 | versão 2.2.1, changelog, SDL2 |
| F4 | https://github.com/nesdev-org/MesenCE/blob/master/SteamOS.md | 2026-07-24 | limitação Gamescope, contorno com botões traseiros |
| F5 | https://www.mesen.ca/docs/configuration/input.html | 2026-07-24 | auto-config por base de dados, Four Score, Zapper, NES×Famicom. **Versão 0.9.9, atualizada 2020-02-01** |
| F6 | https://www.mesen.ca/docs/ | 2026-07-24 | índice: Netplay, HD Packs, Cheats, Movies, Lua. **Mesma ressalva de versão** |

Fontes internas: `docs/03-architecture/ADAPTER-MODEL.md`,
`docs/03-architecture/PLUGIN-MODEL.md`, `docs/05-data/PLATFORM-MANIFEST-V1.md`,
`docs/12-roadmap/EMULATOR-PORTING-DIRECTIVE.md`,
`src/steamzero/adapters/manifests/*.adapter.json`.

## 14. WI proposto para a PORTING-DIRECTIVE

**WI-N1 — Adapter MesenCE e plataforma NES**

- **Objetivo:** NES jogável a partir da central, com periférico correto por jogo
  e sem nenhuma dependência da GUI do emulador.
- **Base existente:** engine `component` + manifestos; `retro-input-profile-v1`;
  tabela de escala inteira (`2965e6f`); `domain/library.py`; `domain/bios.py`.
- **Entregáveis:**
  1. `mesence.adapter.json` pinado por versão + SHA-256, canal estável, com
     `verify` que detecta ausência de SDL2;
  2. spike de `configFormat` com parser estrutural + diff + marcador de
     ownership (resolve a questão 1 da §12);
  3. entrada de `platform-manifest-v1` para NES com timing
     `unknownFallback: unknown-explicit`;
  4. perfil `retro-input-profile-v1` para NES incluindo o mapa Zapper→giroscópio;
  5. FM-27 e FM-28 em `FAILURE-MODES.md`.
- **Gates:** os quatro de sempre, cobertura não regride, mais o critério de
  aceite de experiência da §11 verificado em Game Mode real.
- **Dependências:** nenhuma bloqueante para 1–3. O item 4 depende do spike de
  giroscópio. Netplay **fora deste WI** — depende de `COOP-ONLINE`, inexistente.
