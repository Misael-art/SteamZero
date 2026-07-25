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

### ⚠️ Esta recomendação foi reaberta em 2026-07-25

A coleta do Bloco E trouxe três fatos que enfraquecem o MesenCE como primário —
ver [`retroarch.md`](retroarch.md) para o dossiê completo:

1. **O RetroArch é imune ao FM-27.** Ele desenha o próprio menu dentro da janela
   (RGUI/XMB/Ozone), sem popups de toolkit — a limitação do Gamescope que quebra
   a UI do MesenCE em Game Mode **não o afeta**. Não é sorte, é arquitetura.
2. **O netplay do RetroArch é rollback documentado**, contra o lockstep inferido
   do MesenCE (§6).
3. **Pistola de luz como eixo absoluto é primeira classe** no RetroArch, com
   multi-mouse via `udev` — e `udev` funciona sem X11.

E o pinning, que eu havia tratado como ponto fraco do RetroArch, **não é**: o
nosso `retroarch.adapter.json` já pina o *commit* Flatpak, que é imutável.

**O que segura a decisão:** o pilar deste dossiê é a auto-configuração de
periférico pela base de dados interna do Mesen (§4). **Não se sabe se ela
sobrevive no core libretro.** Essa pergunta decide o primário — e decide também
os outros cinco sistemas cobertos pelo MesenCE. É o **WI-R0** proposto em
`retroarch.md` §14: barato, e bloqueante para seis dossiês.

Até o WI-R0 responder, este dossiê mantém o MesenCE como primário **por causa da
§4**, e registra que a decisão está sub judice.

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
### ⚠️ Bloqueio de supply chain: não há artefato pinável no padrão do projeto

Corrigido em 2026-07-25 pela coleta externa. A versão anterior deste dossiê
afirmava "AppImage das releases, pinado por SHA-256". **Estava errado nos dois
pontos** — e o erro veio de assumir que o padrão dos manifestos de Switch valia
aqui.

| Fato | Fonte | Consultado |
|---|---|---|
| A estável 2.2.1 (2026-06-05) **não tem AppImage**. O único artefato Linux x86-64 é `Mesen_2.2.1_Linux_x64.zip`, build nativa AoT | https://github.com/nesdev-org/MesenCE/releases/tag/2.2.1 | 2026-07-25 |
| AppImage existe **só como nightly** de CI, sem hash em lugar nenhum | `SteamOS.md` + `.github/workflows/build.yml` | 2026-07-25 |
| O projeto **não publica SHA-256** nas notas. O Mesen 0.9.9 publicava — é **regressão de prática de supply chain** | notas da release 2.2.1 | 2026-07-25 |
| Há digest `sha256` por asset na **API do GitHub** — metadado da plataforma, não do projeto. Linux x64 2.2.1 = `c88ff4d251b407515c43d3332d641927655cd69fb538996b6a21da4509dbb58f` | https://api.github.com/repos/nesdev-org/MesenCE/releases/334857600 | 2026-07-25 |

**Consequência.** A regra 2 do `ADAPTER-MODEL.md` exige `sha256` na fonte. Aqui o
hash existe, mas quem o afirma é o GitHub — é integridade de transporte, não
proveniência assinada pelo autor. Vira questão de política (§12).

- **Fonte proposta:** `Mesen_<versão>_Linux_x64.zip` da release **estável**, hash
  fixado manualmente no primeiro download. **Nightly não entra** — sem hash.
- **Dependência de runtime:** **SDL2** nas builds nativas ("SDL2 must be manually
  installed first", notas 2.2.1); o AppImage nightly exigiria também FUSE.
  **.NET não é exigido em runtime** nas builds AoT — só para compilar. É
  `status`/`verify` do adapter, nunca `install`. Lista granular além de
  SDL2/FUSE: `NÃO ENCONTRADO` em documentação.
- **`configFormat`: `json`** — resolvido. `~/.config/MesenCE/settings.json`, com
  modo portable opcional e migração automática de `~/.config/Mesen2` legado.
  Subpastas: `GameConfig/`, `Saves/`, `SaveStates/`, `Screenshots/`, `Movies/`.
  Fonte: `UI/Config/ConfigManager.cs`, master, 2026-07-25.
  ⚠️ **Fato de código, não de documentação** — não existe site oficial da linha
  2.x. O caminho efetivo sob SteamOS não foi confirmado por execução real
  `[validar no spike]`.
- **Parser estrutural obrigatório:** JSON facilita, a regra não muda. Diff antes
  de aplicar, marcador de ownership, FM-22 se o emulador reescrever por fora.

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

**Confirmado na linha 2.x** (a versão anterior deste dossiê marcava como dúvida):

| Fato | Fonte | Consultado |
|---|---|---|
| `AutoConfigureInput` existe na `NesConfig`, **padrão `true`**, com checkbox `chkAutoConfigureInput` na tela de input do NES | `UI/Config/NesConfig.cs`, `UI/Views/NesInputConfigView.axaml`, master | 2026-07-25 |
| O núcleo consulta a base de dados interna ao carregar a ROM: `if(GetNesConfig().AutoConfigureInput && romData.Info.InputType != GameInputType::Unspecified)` | `Core/NES/NesConsole.cpp`, master | 2026-07-25 |
| O rótulo de UI é literalmente o mesmo do manual antigo — a funcionalidade sobreviveu com o texto intacto | Sinden Lightgun Wiki, "Mesen", 2024-03-24 | 2026-07-25 |

**Como o SteamZero remove a fricção:** a base já existe e já vem ligada — mas o
usuário só descobre isso abrindo um menu que, em Game Mode, **não renderiza**
(§10). O SteamZero garante o estado por arquivo e o usuário nunca encontra o
problema.

### ⚠️ Conflito com o WI-5 (rename No-Intro) — descoberto por cruzamento

Este é o achado que só aparece cruzando duas fontes, e ele **quebra
silenciosamente** se não for tratado.

| Fato | Fonte | Consultado |
|---|---|---|
| A config por jogo do MesenCE é gravada em `GameConfig/<nome-do-arquivo-da-ROM>.json`, endereçada pelo **nome do arquivo** (`Path.GetFileNameWithoutExtension`) — **não** por hash nem serial | `UI/Config/GameConfig.cs`, `UI/Interop/EmuApi.cs`, master | 2026-07-25 |

O **WI-5 da porting-directive renomeia ROMs para o nome canônico No-Intro.**
Logo: aplicar o WI-5 numa biblioteca que já tem config por jogo do MesenCE
**órfã todas elas de uma vez**. Os arquivos continuam lá, apontando para o nome
antigo; o emulador carrega os padrões. **Sem erro, sem aviso, sem falha visível**
— exatamente o tipo de degradação silenciosa que a invariante §2.6 proíbe.

**Requisito de projeto que isto impõe ao WI-5:** para emuladores cuja config por
jogo é endereçada por nome de arquivo, o rename precisa mover o *sidecar* junto,
**dentro da mesma transação e do mesmo rollback**. Isso não está nos entregáveis
do WI-5 hoje. Proposto como **FM-29** (§10).

**Contraste que vale registrar:** DuckStation, PCSX2 e Dolphin endereçam config
por jogo pelo **serial** do título (`SLUS-00594`, `RMGE01`) — imune a rename.
Ver `RESEARCH-INPUT-LEGACY-SCRIPTS.md` C1. O MesenCE é o caso frágil, não a
regra; o WI-5 precisa tratar a classe, não o caso.

**Limitação honesta do escopo:** a config por jogo do MesenCE cobre só *overscan*
e *dip switches*. Filtro de vídeo e aspect ratio são override **por console**,
não por jogo (`UI/Config/ConsoleOverrideConfig.cs`). Não prometer "qualquer
ajuste por jogo" neste sistema.

## 5. Inputs exóticos (P2) — **aplica; o item estrela está em risco**

**Todos os sete periféricos de interesse estão confirmados no enum
`ControllerType` e no núcleo** (fonte: `Core/Shared/SettingTypes.h` e
`Core/NES/Input/`, master, 2026-07-25):

| Original | Confirmado | Hardware do Deck proposto |
|---|---|---|
| Zapper (NES/Famicom/VS) | `NesZapper`, `FamicomZapper`, `VsZapper` | **giroscópio** — ver risco abaixo |
| Four Score | `FourScore` | — (P3) |
| Four Player Adapter (Famicom) | `FourPlayerAdapter`, `TwoPlayerAdapter` | — (P3) |
| Power Pad / Family Trainer | `PowerPadSideA/B`, `FamilyTrainerMatSideA/B` | botões + trackpad |
| Arkanoid / paddle | `NesArkanoidController`, `FamicomArkanoidController` | **trackpad** como paddle absoluto |
| Microfone do Famicom | botão `Microphone` no controle P2; `BandaiMicrophone` | microfone do Deck |
| Family BASIC keyboard | `FamilyBasicKeyboard` | teclado virtual do produto |

Extras presentes que ninguém espera: Oeka Kids Tablet, Konami Hyper Shot, Party
Tap, Pachinko, Exciting Boxing, Jissen Mahjong, Subor keyboard/mouse, Barcode
Battler, Hori Track, Datach barcode reader, NTT Data Keypad.

### ⚠️ O mapa gyro → Zapper não tem caminho comprovado

A coleta de 2026-07-25 mudou o quadro. Registro honesto:

| Fato | Fonte | Consultado |
|---|---|---|
| **Nenhum precedente documentado** de giroscópio do Deck mapeado para pistola de luz em emulador, após múltiplas buscas | `NÃO ENCONTRADO` | 2026-07-25 |
| O gyro-como-mouse do Steam Input emite **movimento relativo (deltas)**, não coordenada absoluta de tela | https://partner.steamgames.com/doc/features/steam_controller | 2026-07-25 |
| Pistola de luz precisa de **posição absoluta**. O cursor deriva em relação à mira real | análise da coleta | 2026-07-25 |
| Uma issue do RetroArch (2021) cita giroscópio como fonte teórica de coordenadas de lightgun — **ideia registrada, sem implementação** | https://github.com/libretro/RetroArch/issues/12736 | 2026-07-25 |
| O caminho que existe: a API libretro expõe `RETRO_DEVICE_LIGHTGUN` e um `Pointer` com **coordenadas absolutas** (−0x7fff…0x7fff) | https://forums.libretro.com/t/how-to-configure-mouse-as-light-gun-and-light-gun-as-mouse/8970 | 2026-07-25 |

**Leitura sóbria.** O gap é relativo-versus-absoluto, e não é detalhe de
afinação: é a diferença entre funcionar e não funcionar. Fazer gyro virar mira
absoluta exige uma camada de recentralização/fusão que **ninguém publicou**.

Isso corta nos dois sentidos, e o dossiê registra os dois: é a maior
oportunidade de diferenciação do produto **e** o item de maior risco de execução
de toda a Onda 1. O spike deixa de ser "medir latência" e passa a ser
**"provar que é possível"** — com resultado negativo aceitável.

**Plano B, se o spike falhar:** trackpad como apontador absoluto. Menos
espetacular que levantar o console e atirar, mas é posição absoluta de verdade e
mantém o Zapper jogável. O momento mágico da §11 muda de veículo, não de destino.

## 6. Multiplayer (P3) — **aplica**

| Modo | Fato | Fonte |
|---|---|---|
| 4 jogadores locais | NES via acessório **Four Score**; Famicom via **Four Player Adapter** na porta de expansão — o Mesen expõe os dois separadamente | manual de input, consultado 2026-07-24 |
| Netplay | **Existe na 2.x**: `Core/Netplay/` com `GameServer`/`GameClient`, janela `NetplayConnectWindow`, config persistida em `settings.json` (`NetplayConfig`: host, porta **8888**, senhas) | código master, 2026-07-25 |

Transporte: **TCP direto** — o host precisa de porta acessível, exigindo
port-forward ou VPN.

**Limitações honestas, todas confirmadas:**

- **Lockstep, provavelmente.** Há `InputDataMessage` de sincronização e
  **nenhum** código de rollback/GGPO. `[hipótese baseada no código]` — não há
  documentação de netplay da linha 2.x.
- **O UPnP regrediu.** O manual 0.9.9 prometia adicionar regras de
  port-forwarding automaticamente via UPnP; `grep -i upnp` em `Core/Netplay` da
  master **não retorna nada**. Tratar como regressão não documentada: o usuário
  terá de configurar rede à mão.
- Nenhuma limitação declarada oficialmente para 2.x: `NÃO ENCONTRADO`.

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

- **HD Packs — confirmados na 2.x, e só para NES.** `Core/NES/HdPacks/`
  (`HdPackLoader`, `HdNesPpu`, `HdAudioDevice`), opção `EnableHdPacks` **padrão
  `true`** na `NesConfig`. Formato HDNes (`hires.txt`, versão 106) com PNGs e
  substituição de áudio em estilo MSU-1; instalação em `HdPacks/<nome-da-ROM>`
  ou `.zip` solto na pasta. Fonte: código master, 2026-07-25.
  - ⚠️ **A pasta é endereçada pelo nome da ROM** — mesmo problema do FM-29 (§4).
  - ⚠️ **Limitação de primeira classe:** há relatos de que HD Packs do Mesen 2.x
    são problemáticos em Linux e que packs que funcionam no 0.9.9 não funcionam
    no 2.x (fórum libretro, 2024-01-30). **Não verificado no MesenCE 2.2.x.**
    Não prometer HD Packs antes de testar em hardware.
  - A documentação de formato disponível é a do 0.9.9; não há doc de formato 2.x.
- **Cheats** e **Movies**: ferramentas de primeira classe.
- **Patches BPS**: suporte presente ("BPS: Fixed potential crashes when applying
  BPS patches").

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
| FM-29 | Rename de ROM órfã config por jogo endereçada por nome de arquivo | adapter declara como a config por jogo é endereçada (`filename` × `serial` × `hash`) | o rename move o sidecar na **mesma transação**; falha parcial restaura os dois. Nunca renomear ROM deixando config para trás |

**FM-27 confirmado e ainda vigente em 2026-07-25.** A correção upstream do
Avalonia (PR #14366) foi **revertida** (PR #14573, 2024-02-10). Os fixes de
Gamescope de junho/2026 (issues #2176/#2211) tratam dropdowns de processos
filhos no `steamcompmgr`, **não** o caso genérico de toolkit — a issue #327
("Dropdowns out of screen", 2022) segue aberta. Risco de leitura apressada:
alguém ver "dropdown fixed" e concluir que o problema acabou. Não acabou.

*Caminho não explorado pelo upstream, registrado como pista:* o Avalonia suporta
`X11PlatformOptions { OverlayPopups = true }`, que renderiza popups dentro da
janela principal. `grep` no MesenCE não encontra uso — `[hipótese, não
implementada]`. Não é ação nossa (é upstream), mas informa a conversa.

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

> **O usuário abre Duck Hunt em Game Mode, levanta o Deck e atira na tela.
> Sem configurar nada.**

O destino é esse. O **veículo** depende do spike da §5, e o dossiê não finge que
já sabe qual será:

- **Veículo A (giroscópio):** espetacular, sem precedente publicado, risco alto.
- **Veículo B (trackpad como apontador absoluto):** menos memorável, tecnicamente
  sólido, é posição absoluta de verdade.

Critério de aceite mensurável — **independente do veículo**:

1. Instalar NES pelo SteamZero, colocar `Duck Hunt` na biblioteca, lançar pelo
   Game Mode: o Zapper está ligado na porta 2 **sem intervenção**, porque
   `AutoConfigureInput` foi garantido por arquivo (§4).
2. A mira acompanha o apontamento com precisão suficiente para acertar um pato
   em movimento — critério de jogabilidade, não de latência bruta.
3. Em nenhum momento o usuário precisa abrir um menu do emulador — que, sob
   Gamescope, não renderizaria (§10).
4. Desinstalar reverte a configuração ao estado anterior, provado por teste de
   rollback com injeção de falha.
5. **Renomear a ROM pelo WI-5 não perde a configuração do jogo** (§4).

O item 5 não estava na versão anterior deste dossiê. Ele existe porque o
cruzamento de duas fontes revelou que o rename órfã a config — e um critério de
aceite que não cobre isso deixaria passar uma regressão silenciosa.

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
| F7 | `UI/Config/ConfigManager.cs` (master) | 2026-07-25 | formato JSON, caminho `~/.config/MesenCE/`, subpastas |
| F8 | `UI/Config/GameConfig.cs`, `UI/Interop/EmuApi.cs` (master) | 2026-07-25 | **config por jogo endereçada por nome de arquivo** — base do FM-29 |
| F9 | `UI/Config/NesConfig.cs`, `Core/NES/NesConsole.cpp` (master) | 2026-07-25 | `AutoConfigureInput` padrão `true`, confirmado na 2.x |
| F10 | `Core/Shared/SettingTypes.h`, `Core/NES/Input/` (master) | 2026-07-25 | enum completo de periféricos |
| F11 | `Core/Netplay/`, `UI/Config/NetplayConfig.cs` (master) | 2026-07-25 | netplay TCP porta 8888; ausência de UPnP e de rollback |
| F12 | https://api.github.com/repos/nesdev-org/MesenCE/releases/334857600 | 2026-07-25 | digest sha256 do asset — metadado de plataforma |
| F13 | https://github.com/AvaloniaUI/Avalonia/pull/14573 | 2026-07-25 | reversão da correção de popups |
| F14 | https://github.com/ValveSoftware/gamescope/issues/327 | 2026-07-25 | issue de dropdowns aberta desde 2022 |
| F15 | https://github.com/libretro/RetroArch/issues/12736 | 2026-07-25 | gyro como fonte teórica de lightgun, sem implementação |
| F16 | https://partner.steamgames.com/doc/features/steam_controller | 2026-07-25 | gyro-como-mouse é **relativo**; sem data de revisão declarada |

**Fatos das linhas F7–F11 vêm de leitura de código-fonte, não de documentação.**
Não existe site oficial da linha 2.x — `mesen.ca/docs` descreve o 0.9.9 de 2020.
Essa era exatamente a armadilha antecipada no briefing de pesquisa, e ela se
confirmou.

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
