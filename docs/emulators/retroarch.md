# EMULATOR-DOSSIER — RetroArch (frontend multi-sistema)

**Slug:** `retroarch` · **Onda:** transversal · **Status:** revisão · **Estudo:** 2026-07-25

> **Não é um dossiê de sistema.** RetroArch é um frontend que atende dezenas de
> sistemas da fila. Este documento existe porque a alternativa citada em cada
> dossiê de sistema não pode ser reescrita 40 vezes. Dossiês de sistema
> **referenciam** este; não repetem as seções 2, 3 e 10.

---

## 1. Recomendação

**RetroArch 1.22.2, GPLv3.** Tag publicada em 2025-11-20; Flathub publicou em
2025-11-22. Cadência recente e ativa: 1.22.0 (2025-11-14), 1.22.1 (11-15),
1.22.2 (11-20). Fonte: `github.com/libretro/RetroArch/releases/tag/v1.22.2`,
consultado 2026-07-25.

**Papel proposto no SteamZero:** *alternativa de primeira classe*, não primário
universal. A escolha por sistema continua sendo do dossiê do sistema — mas com
dois argumentos novos e fortes a favor do RetroArch (§4 e §7).

## 2. Adapter

**Já existe manifesto commitado** (`src/steamzero/adapters/manifests/retroarch.adapter.json`):
Flatpak `org.libretro.RetroArch`, `configFormat: ini`, licença `GPL-3.0-only`,
`paths.config: {XDG_CONFIG_HOME}/retroarch/retroarch.cfg`.

### Correção a um alerta da coleta

A coleta (E2) afirma que "Flatpak e Steam auto-atualizam — incompatíveis com a
premissa de versões pinadas". **Isso é verdade para Steam e falso para Flatpak
como o usamos:** o nosso manifesto já pina o *commit* Flatpak
(`56fdd2ed2f5ae5d7bb887f38858c68757e27afcc8e86e830e338e14cd4988522`), e commit
Flatpak é um identificador imutável de conteúdo — é um pin legítimo, equivalente
funcional ao SHA-256 de um arquivo.

| Canal | Pinável? | Nota |
|---|---|---|
| **Flatpak (Flathub)** | **sim**, por commit | é o que já fazemos; atualização só acontece se mudarmos o commit |
| buildbot `.7z` | sim, com hash calculado por nós | `buildbot.libretro.com/stable/1.22.2/linux/x86_64/` — sem hash publicado |
| Steam (app 1118310) | **não** | auto-atualiza, fora do nosso controle |
| GitHub releases | n/a | **só código-fonte**; binários não são anexados |

**Conclusão:** o canal Flatpak que já usamos é o correto. Nenhuma mudança de
manifesto exigida por esta coleta — o que é um resultado, não uma omissão.

**Dependências de runtime** (canal buildbot): `libudev` e `libxkbcommon` para o
driver de input `udev` — que **funciona sem servidor X, em KMS**, propriedade
relevante para sessões tipo Game Mode. Flatpak e Steam embutem o runtime.
Lista completa via `ldd`: `NÃO ENCONTRADO` em documentação.

## 3. BIOS / firmware

Herda a política do projeto: `local-owned-dump-only`, store em `domain/bios.py`.
Cada core declara suas necessidades; o RetroArch não altera essa regra.

## 4. Config-per-game (P1) — **o sistema mais completo da coleta**

Tudo texto plano, tudo por arquivo, **sem necessidade de GUI** — a documentação
oficial diz literalmente que são "only plain text files and can be adjusted
manually with a text editor". Fonte: `docs.libretro.com/guides/overrides/`,
consultado 2026-07-25.

**Hierarquia de override, do mais específico ao mais geral:**

```
jogo  →  diretório de conteúdo  →  core  →  global (retroarch.cfg)
```

Cada nível é um arquivo que contém **só os diffs**:

| Camada | Caminho | Endereçado por |
|---|---|---|
| override por jogo | `config/<core>/<nome-do-jogo>.cfg` | **nome do arquivo** |
| override por pasta | `config/<core>/<nome-do-diretório>.cfg` | nome do diretório |
| override por core | `config/<core>/<nome-do-core>.cfg` | nome do core |
| remap de input | `config/remaps/<core>/<jogo>.rmp` | **nome do arquivo** |
| opções de core | `<jogo>.opt` (exige *Load Content Specific Core Options Automatically*) | **nome do arquivo** |
| preset de shader | por jogo/core | **nome do arquivo** |

Caminho típico: `~/.config/retroarch/`; Flatpak:
`~/.var/app/org.libretro.RetroArch/config/retroarch/`. Todos reconfiguráveis.

**Limitação declarada pela própria doc:** "Some settings cannot be saved in an
override file from the menu. You can manually add settings to the override file
to workaround most situations." Ou seja: escrever por arquivo é *mais* capaz que
a GUI — o que joga a favor do SteamZero.

### ⚠️ FM-29 se aplica aqui, e pior

O `nes.md` §4 descobriu que renomear a ROM órfã a config por jogo do MesenCE
(`GameConfig/<rom>.json`). **No RetroArch o problema é quatro vezes maior:**
override `.cfg`, remap `.rmp`, opções `.opt` e preset de shader — **todos
endereçados por nome de arquivo do conteúdo**.

Hash/CRC existe no RetroArch, mas só no handshake de netplay e no scan de
playlists — **não** na config.

Isso reforça que o requisito imposto ao WI-5 (mover o sidecar na mesma
transação) precisa tratar **conjunto de sidecars**, não arquivo único. Registrado
como ampliação de FM-29, não FM novo.

## 5. Inputs exóticos (P2)

### Pistola de luz: primeira classe ✅

Os drivers de input Linux expõem pointer absoluto e dispositivo lightgun
dedicado; cores consomem `RETRO_DEVICE_LIGHTGUN`.

| Driver | Multi-mouse | Nota |
|---|---|---|
| `udev` | sim | **sem X11**, funciona em KMS |
| `x` | sim, desde 1.20.0 | via `xinput create-master`/`reattach` |
| `wayland` | pointer sim | botões fixos |

Pistolas USB (Sinden, AimTrak, GUN4IR) aparecem como pointer absoluto. O core
`PCSX ReARMed` promoveu o GunCon de "Pointer" para "Lightgun" com botões
mapeáveis e *offscreen reload* (changelog 1.10.3, 2022).

### Giroscópio: a API existe, o driver Linux não entrega ❌

**Este é o fato mais decisivo do Bloco E para o nosso maior risco.**

A API libretro prevê 3 eixos de giroscópio + 3 de acelerômetro + sensor de
iluminação ("Auxiliary Sensor Input"). Mas **os únicos drivers que passam
giroscópio são `android`, `cocoa`, `vita` e `switch`**. Os drivers Linux x86
(`x`, `wayland`, `udev`, `sdl`, `linuxraw`) passam **somente iluminação**.

Fonte: `docs.libretro.com/guides/input-controller-drivers/`, consultado
2026-07-25.

**Consequência para o risco DESC-9/C4:** a hipótese anterior era "não há
precedente publicado". Agora é mais dura e mais precisa: **no Steam Deck o
RetroArch não lê o giroscópio nativamente**. A ponte gyro→absoluto teria de
nascer *fora* do RetroArch — como driver que apresente um pointer absoluto
sintético ao `udev`, alimentado por fusão de IMU.

Isso não mata a ideia; ela vira um componente próprio, não uma configuração. E
**eleva o valor do plano B** (trackpad como apontador absoluto), que funciona
hoje, sem componente novo.

## 6. Multiplayer (P3) — **rollback documentado, e isso decide**

| Fato | Fonte |
|---|---|
| O netplay é **baseado em replay**: "free of input latency in the default configuration"; o cliente rebobina e re-executa ao receber input atrasado (*rewind + replay*) | `docs.libretro.com/development/retroarch/netplay/` |
| Transporte TCP; até **16 jogadores** + espectadores; servidor canônico; senha com hash no handshake; latência de input opcional para reduzir custo de rewind | idem |
| A versão Steam tem netplay via **Steam Remote Play** — independe de serialização | anúncio libretro, 2021 |

**Contraste que importa:** o netplay do MesenCE é lockstep (inferido do código,
`nes.md` §6); o do RetroArch é rollback (documentado). Se multiplayer online
entrar na fila, **essa diferença é decisiva e não deve ser nivelada por baixo**.

**Limitações declaradas, com a mesma tipografia:** a garantia de sincronia é
condicional — a própria doc anota "¹ Guarantee not actually a guarantee";
depende de core determinístico com serialização; dispositivos de input limitados
a gamepad/analógico; core e ROM idênticos dos dois lados, conferidos por CRC.

Transporte da Fase 7 continua dependendo de `COOP-ONLINE`, que não existe.

## 7. Game Mode — **imune ao problema que quebra o MesenCE** ✅

RetroArch **renderiza menu e OSD dentro da própria janela**, pelo video driver
(menu drivers RGUI, XMB, Ozone, MaterialUI). **Não usa popups de toolkit.**
Portanto **não é afetado pela restrição do Gamescope** documentada em FM-27 e
detalhada no `nes.md` §10 e no adendo C1.

Isto é arquitetura, não sorte: um frontend que desenha a própria UI em GL/Vulkan
não tem janelas filhas para o compositor recusar.

`[validar no spike]` que nenhum fluxo comum usa popup — o *desktop menu*/Qt
companion é opcional e separado, mas existe.

Diferenças da versão **Steam** (app 1118310), fonte: anúncio de 2021-09-14 —
⚠️ *documento de 2021, pode estar desatualizado*: sem Core Downloader
(conformidade com ToS da Valve), cores como DLC gratuito (65 hoje), assets
pré-empacotados, sem Desktop Menu, com Remote Play e Steam Cloud de saves.

## 8. Mods/patches (P6) e 9. "Como era" (P7)

Shaders (incluindo presets CRT) são cidadãos de primeira classe e configuráveis
por jogo (§4). Isso alimenta diretamente os ganchos WI-R já existentes no
repositório (tabela de escala inteira, `2965e6f`). Detalhamento fica nos dossiês
de sistema — aqui só se registra que a superfície existe e é por arquivo.

## 10. Robustez

- **Config:** texto plano estilo INI (`chave = "valor"`). Parser estrutural com
  diff é viável e obrigatório. Ownership: FM-22 se o RetroArch reescrever.
- **Pinning:** resolvido pelo commit Flatpak (§2). **Não** usar canal Steam.
- **FM propostos:** nenhum novo. FM-27 **não se aplica** (§7) — e registrar
  ausência de modo de falha é resultado. FM-29 se aplica ampliado (§4).
- **Performance no Deck:** não medida. Sem promessa.
- **Sandbox:** Flatpak é o caminho já adotado; o driver `udev` precisa de acesso
  a dispositivos de input — `[validar no spike]` o que o sandbox nega, à luz do
  ADR-0003.

## 11. Momento mágico

Este dossiê **não define momento mágico próprio** — ele é infraestrutura. O
momento mágico pertence ao dossiê de cada sistema. Registrado explicitamente
para não deixar seção vazia sem justificativa (§7 do checklist).

## 12. Riscos e questões

| Risco | Severidade | Nota |
|---|---|---|
| `docs.libretro.com` **não versiona páginas** — conteúdo rolling, sem data | **alta para planejamento** | Tudo em §4–§7 pode mudar em silêncio. Rechecar antes de pinar decisão |
| Canal Steam não pinável | média | Não usar; documentado |
| Core Downloader no Flatpak | baixa | `NÃO ENCONTRADO` se funciona dentro do sandbox |
| Comportamento da versão Steam sob Gamescope em 2026 | média | Fonte é de 2021; só teste em hardware resolve |

**Questão para o operador:** RetroArch reabre a decisão primária do NES (§13 do
`nes.md`). Ver a comparação abaixo e decidir.

### A decisão que o Bloco E reabre

| Critério | MesenCE | RetroArch |
|---|---|---|
| UI em Game Mode | **quebrada** (FM-27) | **imune** (§7) |
| Config por jogo | JSON, escopo estreito (overscan + dip switches) | **4 camadas, escopo amplo** |
| Netplay | lockstep (inferido) | **rollback (documentado)** |
| Lightgun absoluta | via cursor da janela | **primeira classe**, multi-mouse |
| Auto-config de periférico por jogo | **base de dados interna** (o pilar do `nes.md`) | `[validar no spike]` se o core Mesen a carrega |
| Pinning | frágil (sem AppImage na estável, sem hash do projeto) | **resolvido** (commit Flatpak) |
| Precisão de NES | referência | core Mesen disponível |

**Recomendação:** o critério de desempate do direcionador é experiência no Deck,
e o RetroArch ganha em quatro dos sete critérios — incluindo o único que hoje é
uma *falha* (UI em Game Mode). Mas o pilar do `nes.md` é a auto-configuração de
periférico por base de dados interna, e **não sabemos se ela sobrevive no core
libretro**. Essa é a pergunta que decide, e ela é barata de responder.

## 13. Fontes

Coleta de 2026-07-25, Bloco E. Principais: `github.com/libretro/RetroArch/releases/tag/v1.22.2` ·
`buildbot.libretro.com/stable/1.22.2/linux/x86_64/` ·
`docs.libretro.com/guides/overrides/` ·
`docs.libretro.com/guides/input-controller-drivers/` ·
`docs.libretro.com/development/retroarch/netplay/` ·
`store.steampowered.com/dlc/1118310/RetroArch/` · issue `libretro/RetroArch#15196`.

⚠️ **`docs.libretro.com` não declara data nem versão em nenhuma página.** Todos
os fatos de §4 a §9 herdam essa fragilidade — é o mesmo tipo de armadilha do
`mesen.ca/docs`, com sintoma diferente: lá a doc era velha e datada; aqui é
rolling e sem data.

**Derivados** (proveniência de pesquisa; nomes não vão para artefato de produto,
ADR-0019): a coleta levantou seis integradores. O mais relevante é uma
plataforma all-in-one em Flatpak único, 0.10.9b de 2026-05-30, GPL-3.0, feita
para Steam Deck, que já resolve config por arquivo, verificação de BIOS,
scraping e templates de Steam Input. **A ressalva é estrutural e vale registrar:
sandbox monolítica não permite trocar builds individuais de componente**, o que
colide frontalmente com pinning fino por emulador — que é justamente a nossa
premissa. Serve como validação de conceito, não como caminho.

## 14. WI proposto

**WI-R0 — Spike de decisão: MesenCE standalone × core no RetroArch**

- **Objetivo:** responder a única pergunta que decide o primário do NES (e, por
  arrasto, dos outros cinco sistemas cobertos pelo MesenCE).
- **Pergunta:** o core Mesen dentro do RetroArch carrega a **base de dados
  interna de jogos** que conecta periférico automaticamente (Zapper em Duck
  Hunt)? Se sim, o RetroArch acumula todas as vantagens sem perder o pilar.
- **Entregáveis:** resposta com evidência; recomendação de primário para NES;
  se o RetroArch vencer, o `nes.md` é reescrito e o `retroarch.adapter.json`
  existente vira o caminho, sem manifesto novo.
- **Gates:** os quatro de sempre (é estudo — nenhum código de produto).
- **Dependências:** nenhuma. **Barato e bloqueante:** decide seis dossiês.
