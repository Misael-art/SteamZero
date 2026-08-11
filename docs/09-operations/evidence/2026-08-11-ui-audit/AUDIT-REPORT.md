# Auditoria visual e de experiência — SteamZero Desktop UI

**Data:** 2026-08-11  
**Release host:** `0.1.0a44-07802589e985` (também observada no doctor)  
**Runtime de captura:** Qt 6.11.1, `QT_QUICK_BACKEND=software`, `QT_QPA_PLATFORM=offscreen`  
**Bridge:** live (`DesktopControlServer` efêmera) + offline (fallbacks embutidos)

---

## Onde estão os prints

| Pasta | Conteúdo |
|---|---|
| **`docs/09-operations/evidence/2026-08-11-ui-audit/live/`** | **55 PNGs com dados reais da bridge** (recomendado para design QA) |
| `docs/09-operations/evidence/2026-08-11-ui-audit/` (raiz) | 55 PNGs offline (fixtures/fallback, sem bridge) |
| `docs/09-operations/evidence/2026-08-11-ui-audit/live/MANIFEST.json` | Metadados, contagens, snapshot host |
| Goldens históricos | `src/steamzero/ui/qml/golden/` (não substituídos) |

### Inventário da captura live (55)

| Prefixo | Qtd | O que cobre |
|---|---:|---|
| `deck-*` | 9 | Todas as seções em 1280×800 |
| `studio-*` | 9 | Todas as seções em 1600×1000 |
| `fullhd-*` | 9 | Todas as seções em 1920×1080 |
| `handheld-*` | 3 | overview / emulação / biblioteca em 949×593 |
| `ultrawide-*` | 2 | overview + sync em 2560×1080 |
| `steam-area-*` | 4 | Desempenho, Controles, Biblioteca Steam, Modo Desktop |
| `emulation-*` | 12 | Gestão global + 11 áreas da plataforma Switch |
| `library-*` | 4 | Sistemas + jogos (carousel/grid/list) |
| `overlay-*` | 3 | task drawer, nav drawer, credentials (parcial — ver limitações) |

**Como regenerar:**

```bash
.venv/bin/python tools/ui_audit_runner.py \
  --outdir docs/09-operations/evidence/2026-08-11-ui-audit/live
# ou offline:
.venv/bin/python tools/ui_audit_runner.py --offline --outdir …
```

---

## Mapa navegável real (produto)

Sidebar / `navigationSections` em `Main.qml`:

1. Visão geral (EditorialHome + blocos legados de overview)
2. Emulação (gestão global + 36 plataformas técnicas / 11 áreas por plataforma)
3. Steam / Gameplay (Desempenho·LSFG | Controles | Biblioteca | Modo Desktop)
4. Perfis
5. Saves e Sync
6. Transmissão
7. Sistema
8. Temas
9. Biblioteca (editorial: sistemas → jogos carousel/grid/list)

**Ausentes na UI em relação à IA documentada** (`docs/07-ui-ux/INFORMATION-ARCHITECTURE.md`): Jobs top-level, BIOS como centro próprio, Armazenamento top-level, QAM/Game Mode Godot, first-run wizard.

---

## Achados por severidade

### P0 — quebra visual / usabilidade imediata

| ID | Achado | Evidência | Causa provável |
|---|---|---|---|
| **P0-1** | **Botões “AÇÕES DO SISTEMA” sem texto** (3 retângulos brancos: Quick Reset, Cloud Sync, doctor) | Qualquer `studio-*` / `fullhd-*` live | `DarkButton.qml` força `contentItem` e `palette.buttonText` em `#f2f6fb` (texto claro). No tema mineral claro ativo, o texto some sobre `surfaceColor` claro. Ícones KDE também falham no software renderer. |
| **P0-2** | **Tema claro + DarkButton = contraste morto** em qualquer CTA que use DarkButton com fundo claro | Sidebar + vários CTAs emuladores | Componente não consome tokens do tema; nasce “dark-only”. |
| **P0-3** | **Biblioteca de jogos visualmente vazia** apesar de “14 jogo(s)” | `library-games-carousel.png`, `library-games-grid.png` | Carousel/list: só o título “Gimmick! 2 Demo” no rodapé; sem capas, sem rail de mídia, filtros de metadados todos “não publicado”. Experiência “biblioteca morta”. |
| **P0-4** | **Botão “Instalar” dos demais emuladores é falso (não-op)** | `globalManagement.emulators` + código | Ver seção **Instalação de emuladores** abaixo. O workspace publica `action.id = "emulator.install:<id>"`, mas a UI chama `performRowAction`, que só entende `action.kind` (`component-plan`). Clique habilitado → **zero efeito**. |
| **P0-5** | **Instalação deslocada / jornada fragmentada** | `studio-emulators.png`, `emulation-global-management.png` | Cards de plataforma: bloqueador “emulador não instalado” + CTA só **“Abrir plataforma”** (não Instalar). Lista “Componentes e emuladores” com Instalar fica **abaixo da dobra**. Lista legada em `Main.qml` (`component-plan`) está `visible: false`. 33 componentes no lifecycle vs 13 na gestão global — resto “sumiu” da jornada. |

### Instalação de emuladores (análise dedicada — ausente na 1ª passagem visual)

#### O que o backend publica (host real, 2026-08-11)

| Fonte | Contagem | Exemplo de ação |
|---|---:|---|
| `component list` (lifecycle) | **33** | `installable=true` para Dolphin, PPSSPP, DuckStation, libretro-*, etc.; Citron/Eden/Ryubing `installed` |
| `emulation workspace` → `globalManagement.emulators` | **13** | Dolphin: `{id: "emulator.install:dolphin", label: "Instalar", enabled: true}` **sem** campo `kind` |
| Cards de plataforma | **36** | Bloqueador “o emulador desta plataforma não está instalado” + `{id: "platform.open", label: "Abrir plataforma"}` |

Runtimes listados no card Switch incluem Dolphin, PPSSPP, melonDS, Azahar… **mesmo não instalados** — ruído que parece disponibilidade falsa.

#### Cadeia quebrada (falso botão)

```
Emulation.qml  Componentes e emuladores
  Button "Instalar" → componentActionRequested(modelData)
Main.qml
  onComponentActionRequested → performRowAction(component)
performRowAction:
  lê action.kind  // undefined no payload de emulação
  só trata: component-plan | component-verify | component-launch | steam-open | keyboard
  // NÃO trata action.id "emulator.install:*"
  // resultado: return implícito, silêncio total

performEmulationAction (caminho CORRETO, não ligado a este botão):
  action.id.indexOf("emulator.install:") === 0
  → requestAction("emulator.plan", {emulatorId, action: "install"})
  → emulationDialog.open()
```

#### Deslocamento da instalação (IA da jornada)

```
[Primeiro fold — Gestão geral]
  Cards de plataforma
    status: "emulador não instalado"
    CTA: "Abrir plataforma"     ← NÃO instala; só navega
    Runtime: lista 10+ nomes    ← mistura instalados e ausentes

[Abaixo da dobra / painel lateral]
  "Componentes e emuladores" (13 itens)
    CTA: "Instalar" / "Reparar" ← PARECE real, é no-op (P0-4)

[Código morto / deslocado]
  Main.qml lista legada filter Todos/Atenção/Instalados
    visible: false
    usaria performRowAction + action.kind=component-plan (dashboard.components)
    caminho paralelo ao workspace, nunca exposto

[Fora da gestão editorial]
  component list 33 ids (libretro cores, duckstation, sunshine…)
    não aparecem em globalManagement.emulators
    instalação “existe” na CLI, não na jornada visual principal
```

#### O que o usuário sente

1. Vê plataforma “sem emulador” → clica **Abrir plataforma** → não instala.  
2. Se acha a lista de componentes → clica **Instalar** → nada acontece (sem toast de erro).  
3. Emuladores “secundários” (libretro, DuckStation, etc.) não estão na lista de 13 — parecem inexistentes.  
4. Switch parece ter 13 runtimes; só 3 estão instalados — sensação de produto mentiroso.

#### Correção mínima (produto + wiring)

| # | Correção | Onde |
|---|---|---|
| 1 | Ligar botões da lista de emuladores a `performEmulationAction(action)` (ou adaptar `performRowAction` para despachar `action.id` de emulação) | `Main.qml` + `Emulation.qml` |
| 2 | Feedback se plano falhar (erro estruturado, não silêncio) | diálogo / notify |
| 3 | No card de plataforma com emulador ausente: CTA primário **Instalar emulador principal** (action allowlisted) + secundário “Abrir plataforma”; ou “Abrir e instalar” só se o plano existir | `build_global_management` / cards + QML |
| 4 | Painel “Componentes e emuladores” **acima da dobra** ou âncora “Instalar emuladores” no header da gestão geral | `Emulation.qml` layout |
| 5 | Runtime no card: só instalados + “+N disponíveis” (não listar 10 ausentes como se fossem runtime ativo) | payload ou projeção QML |
| 6 | Reconciliar 33 lifecycle vs 13 workspace: documentar filtro; expor “Ver todos os componentes” se o resto for intencional | produto + opcional bridge |
| 7 | Remover ou reativar lista legada `visible: false` — uma única superfície de instalação | `Main.qml` |
| 8 | Teste QML/integração: clique em `emulator.install:dolphin` dispara `emulator.plan` (mock), nunca no-op | `tests/qml` / integration |

### P1 — jornada quebrada ou honesta mas inútil

| ID | Achado | Evidência |
|---|---|---|
| **P1-1** | **Banner global “Perfil do Desktop desatualizado” em 100% das telas** com truth `stale` (handheld aplicado vs docked desejado). Domina hierarquia visual; “Revisar perfis” e card de atenção na sidebar competem com o mesmo problema. | Todas as capturas live |
| **P1-2** | **Seção Perfis esvaziada** — um combobox “Automático” + “Revisar alterações”; sem cards handheld/dock/safe com recommended/desired/applied/observed (prometidos no diagnóstico responsivo e no design de perfis). | `studio-profiles.png` |
| **P1-3** | **Saves e Sync** — três zeros + “Nenhum CloudPort configurado”; único CTA “Atualizar status”. Backend sem mutação (já documentado em HANDHELD-BACKEND-UI-COVERAGE). UI honesta, mas parece produto incompleto na IA. | `studio-sync.png` |
| **P1-4** | **Transmissão** — stack de botões nativos sem cartão, sem estados, sem empty-state orientativo; layout de protótipo CLI, não de central de jogos. “Orquestrador não configurado”. | `studio-cast.png` |
| **P0-6** | **Aba Temas: jornada incompleta / parcialmente não-funcional** | `studio-themes.png` + código | Ver seção **Aba Temas** abaixo. Backend tem `theme.apply` + editor; a UI **não expõe Aplicar**, Export usa API de browser inexistente no QML, layout da lista quebra nomes, nativos só “Editar” (read-only) sem “Usar este tema” / “Duplicar”. |
| **P1-5** | **Editor de Temas — layout da lista** (subconjunto visual de P0-6) | `studio-themes.png` | Nomes truncados sob “Editar”; sem swatch de paleta. |

### Aba Temas (revalidação funcional — 2026-08-11)

#### O que o backend já oferece (ok)

| Contrato / rota | Estado |
|---|---|
| `theme.list` GET `/theme/list` | 3 builtin (default, AURA, steamdeck) — CLI ok |
| `theme.apply` + `theme.apply.confirm` + rollback | Plan/token real no dashboard |
| `theme.editor.load/create/set-tokens/save/export/cancel` | Contratos `enabled=True`, `applicability=applicable` |
| Bridge `desktop_ui` | Rotas GET/POST do editor e apply implementadas |

#### O que a UI faz de fato

| Ação do usuário | UI | Resultado real |
|---|---|---|
| Ver lista | `ThemeEditorPanel` + `GET /theme/list` via `request` | Lista aparece (3 nativos) |
| **Aplicar / ativar tema** | **Inexistente** na lista | Usuário **não consegue** trocar o tema ativo pela aba (só CLI `theme plan/apply`) |
| Criar novo tema | “Criar Novo Tema” → `theme.editor.create` | Caminho wired; depende bridge + `uiContracts` |
| Editar nativo | “Editar” → `theme.editor.load` | Abre sessão; nativos vêm **readOnly** → Salvar disabled — parece “não funciona” |
| Salvar edição | `theme.editor.save` | Só tema de usuário sujo; nativo bloqueado sem CTA “Duplicar” |
| Exportar ZIP | `theme.editor.export` + **`document.createElement("a")`** | **Quebrado no Qt/QML** (API de browser DOM; não existe `document`) |
| Preview ao vivo | ThemeBridge no painel | Existe no editor; G37: extends/AURA no preview do editor pode cair no default |
| Layout lista | Row nome + Editar | **Editar sobrepõe/trunca nome** (captura live) |
| Shell | `ThemeEditorPanel` em `ScrollView` sem altura explícita | ColumnLayout filho de `Rectangle` com `Layout.*` (anexos de Layout **não** aplicam em Rectangle) — sizing frágil |

#### Cadeia / gaps

```
[Lista de temas]
  Criar  → theme.editor.create     (wired)
  Editar → theme.editor.load       (wired; nativo = só leitura)
  Aplicar → ???                    NÃO HÁ BOTÃO (contrato theme.apply órfão na UI)
  Ativo? → não marca o activeId    status tem activeId; lista não destaca

[Editor]
  set-tokens / save / cancel       wired via requestAction
  export → base64 + document.*     QUEBRADO em QML

[Main.qml]
  requestAction exige uiContracts.byId[action].enabled
  contratos theme.* estão applicable — OK se /status publicou uiContracts
  sem bridge: request/requestAction falham com notify (honesto) mas lista vazia + CTAs mortos visualmente
```

#### Correção mínima (funcional + layout)

| # | Correção | Severidade |
|---|---|---|
| 1 | CTA **Aplicar** / “Usar este tema” por linha: `theme.apply` → diálogo de plano → `theme.apply.confirm` (mesmo padrão plan+token do Desktop) | P0 |
| 2 | Destacar tema **ativo** (`dashboard.theme` / `activeId` do status) | P0/P1 |
| 3 | Nativos: botão primário **Aplicar**; secundário **Duplicar e editar** (create extends=id) em vez de “Editar” que só abre read-only | P0 |
| 4 | **Export**: gravar ZIP via caminho allowlisted do host **ou** desabilitar com reason “export indisponível neste shell” — **nunca** `document.createElement` | P0 |
| 5 | Layout lista: swatch + nome/autor/versão + ações sem overlap; alvos ≥48px | P1 (já P1-5) |
| 6 | `ThemeEditorPanel`: âncoras/`implicitHeight` corretos dentro do `ScrollView` do shell | P1 |
| 7 | Erros de create/load/save: `notify`/ErrorCard (não silêncio) | P1 |
| 8 | Teste QML: apply plan mock; export não chama DOM; lista mostra ativo | P0 prova |
| 9 | G37 preview extends (AURA): se tocar editor, alinhar `_make_resolved` — senão registrar follow-up | P3 / KNOWN-GAP |
| **P1-6** | **Home editorial sem capa** do jogo em destaque (placeholder ícone genérico para Gimmick! 2 Demo com 14 títulos Steam). | `studio-overview.png` |
| **P1-7** | **Handheld 949×593** corta a home: cards Favoritos/Pendências incompletos, footer cobre ações, nav some (só header). | `handheld-overview.png` |
| **P1-8** | **Sistema** mostra memória e LSFG no topo; checks do doctor, recovery, operações e export ficam abaixo da dobra sem âncoras claras na captura (e na primeira tela). | `studio-system.png`, `fullhd-system.png` |
| **P1-9** | **Steam · Ambiente** trunca “Feral GameMode — Não fo…”; legibilidade ruim. | `studio-steam.png` |
| **P1-10** | **Dupla identidade na Visão geral**: EditorialHome (“Início”) + secções legadas “Visão geral / Continuar jogando / Sistema e manutenção” empilhadas — scroll longo, conceitos repetidos (prontidão vs pendências vs banner). | código `Main.qml` ~3153–3400 + `ultrawide-overview.png` |

### P2 — organização, layout, IA e categorias

| ID | Achado | Detalhe |
|---|---|---|
| **P2-1** | **IA da nav desalinhada da doc** | Doc: Jobs, BIOS, Armazenamento, Diagnóstico. Produto: Transmissão, Temas, Biblioteca; Jobs não têm seção; BIOS vive dentro de Emulação. |
| **P2-2** | **Biblioteca vs Emulação vs Steam** triplicam “onde estão meus jogos” | Steam games na Home, na Biblioteca editorial, e na aba Steam→Biblioteca (manutenção). Emulação tem 0 ROMs inventariados mas 15 IDs no painel Switch. |
| **P2-3** | **Cloud gaming misturado com consoles** na grade de sistemas (GeForce NOW, Xbox Cloud, Amazon Luna) com o mesmo ícone de gamepad genérico. | `studio-library.png` |
| **P2-4** | **Plataformas com 0 jogos dominam a home e a biblioteca**; Steam (14) é o único com conteúdo — ruído de grade. | overview + library |
| **P2-5** | **Nav “Steam / Gameplay”** com subtítulo só quando selecionado; inconsistente com as outras seções. | sidebar Steam |
| **P2-6** | **Emulação: densidade técnica excessiva** nos cards (lista de 10+ runtimes, “Keys/Firmware/BIOS”, bloqueadores longos) para persona casual. | `studio-emulators.png` |
| **P2-7** | **Áreas de emulação** (11) com estrutura boa (rail + cards), mas várias áreas repetem o mesmo skeleton Keys/Firmware ou ficam vazias sem empty-state rico. | `emulation-area-*.png` |
| **P2-8** | **Ultrawide**: conteúdo limitado (bom), mas banner global ainda full-width e rail de sistemas truncado. | `ultrawide-overview.png` |
| **P2-9** | **Footer de glifos de controle** (“D-PAD NAVEGAR…”) sempre presente no Desktop Mode com mouse — ruído se `currentInput` não é gamepad. | todas |
| **P2-10** | **Metadados da biblioteca** (Gênero/Ano/Desenvolvedor) expostos como “não publicado” em chips mortos — parece filtro quebrado. | `library-games-*.png` |
| **P2-11** | **Coleções “indisponíveis”** sem explicação de como publicar/criar. | overview |
| **P2-12** | **TDP default 3 W** com range 0–15 W e slider no mínimo visual — pode assustar ou parecer bug. | steam performance |

### P3 — polish, tokens, acessibilidade

| ID | Achado |
|---|---|
| **P3-1** | Escala de texto do host não honrada (KNOWN-GAPS G12) — `font.pixelSize` fixo |
| **P3-2** | 46 warnings QML por sessão do estilo Breeze (G21) — ruído em QA real |
| **P3-3** | Ícones de plataforma: só Steam tem marca própria na grade; resto gamepad genérico apesar de assets em `ui/assets/*.svg` |
| **P3-4** | Botão “Tarefas” branco genérico no tema claro — contraste e hierarquia fracos vs attention card |
| **P3-5** | Progress bar de prontidão Steam (67%) e emulação (45%) sem ação primária acoplada no mesmo card |
| **P3-6** | Captura live saiu com `qmlReturncode=-11` (SIGSEGV) após as 55 gravações — investigar lifecycle do harness/bridge (não bloqueou PNGs) |

---

## Backend ↔ UI (gaps de contrato)

| Domínio | Backend | UI observada | Gap |
|---|---|---|---|
| Desktop profile | truth `stale`, desired docked, applied handheld | Banner + Perfis mínimos | Fluxo de apply pouco visível; Perfis não mostra o quadro 4-estados |
| Emulação | 36 plataformas, Switch 45%, keys/firmware ok, Citron instalado, 15 IDs; 13 emuladores no GM com `emulator.install:*` enabled; 33 no lifecycle | Gestão global densa; 0 jogos “reais”; **Instalar no-op**; cards só “Abrir plataforma” | **P0-4/P0-5**: wiring + deslocamento da instalação; descompasso 15 IDs vs 0 jogos |
| Steam gameplay | Gimmick demo, 67% pronto, launch options | Tela rica e a melhor da central | GameMode degradado; capas ausentes |
| Sync | sem CloudPort | Empty honesto | Mutações allowlisted ainda N/A |
| Cast | orquestrador não configurado | Botões crus | Falta shell de produto e estados |
| Temas | CLI list/status/apply/editor ok; 3 nativos; `theme.apply` no catálogo | Lista com Editar; **sem Aplicar**; Export DOM; layout cortado; nativo read-only | **P0-6**: UI não fecha a jornada de ativar/editar tema |
| Jobs / operações | CLI `jobs` / `operations` existem | Sem seção; task drawer não capturado | Jobs de emulação vs tarefas UI pouco descobertos |
| Credentials | diálogo existe | Overlay não abriu no harness | Ação de open depende de refresh da bridge |
| Coleções / favoritos | read model vazio | Empty + botão morto “Coleções indisponíveis” | Sem onboarding |
| Playtime | 0 s / 0 games | Home sem “Continuar” real | OK honesto; home depende de Steam fixture |
| BIOS | domínio existe (FUNCTION-PROVENANCE) | Só dentro de Emulação por plataforma | Sem centro BIOS multiplataforma |
| Doctor | degraded, orphan backup | Sistema foca memória primeiro | Hierarquia de diagnóstico invertida |

---

## Jornadas auditadas (resumo)

| Jornada | Estado da experiência |
|---|---|
| Abrir central → entender o que fazer | **Ruim**: banner stale + home semi-vazia + botões de sistema invisíveis |
| Continuar jogando | **Fraca**: 1 demo Steam sem capa; playtime vazio |
| Preparar emulação Switch | **Média**: painel e áreas existem; keys/fw ok; **instalar demais emuladores é no-op / deslocado** (P0-4/P0-5) |
| Instalar emulador ausente (Dolphin, RetroArch, …) | **Quebrada**: botão Instalar falso; card de plataforma não oferece instalar; lista abaixo da dobra |
| Ajustar perfil Steam por jogo | **Boa**: melhor tela; escopos, LSFG, controles, manutenção |
| Resolver perfil Desktop | **Confusa**: banner, attention card, seção Perfis e Steam→Modo Desktop competem |
| Sync de saves | **Vazia honesta** |
| Transmitir tela | **Protótipo** |
| Personalizar / aplicar tema | **Não-funcional como produto**: sem Aplicar na UI; Export quebrado; nativo “Editar” read-only; layout cortado (P0-6) |
| Explorar biblioteca multi-sistema | **Fraca**: 0 ROMs, chips de metadados mortos, sem capas |
| Diagnosticar sistema | **Parcial**: memória e LSFG; doctor pouco proeminente |

---

## Oportunidades de layout (prioridade design)

1. **Corrigir DarkButton para tokens de tema** (P0) — texto/ícone herdados de `textColor` / `ThemeBridge`.
2. **Reconhecer o banner stale** após dismiss ou fundir com o card Pendências (um único “inbox” de atenção).
3. **Perfil Desktop em 4 cards** (Auto / Portátil / Dock / Seguro) com recommended/desired/applied/observed — a UI de Steam→Modo Desktop já tem pedaços disso.
4. **Biblioteca**: empty-state com CTA de scan/import; capas Steam via media package; esconder chips de metadados não publicados.
5. **Home**: uma hierarquia só (editorial) sem stack legado; sistemas com 0 jogos em “Ver todos”, não no primeiro fold.
6. **Transmissão e Temas**: aplicar SectionCard / empty-state / primary CTA como em Emulação e Steam.
7. **Sidebar**: ícones de seção + remover/ocultar AÇÕES se DarkButton não renderiza; ou migrar para Button tematizado.
8. **Sistema**: “Saúde” / doctor no topo; memória em secundário.
9. **Emulação global**: resumir runtimes (“N emuladores”) com expand; não listar 10 nomes no card.
10. **Handheld**: rail/drawer-first sem depender de botões de sistema do shell desktop.

---

## Limitações desta auditoria

- Captura **offscreen + software**: ícones de tema KDE e alguns overlays podem diferir do Plasma real.
- Overlays `task-drawer` e `credentials` **não abriram de forma confiável** no harness (timer/assíncrono); a UI desses fluxos precisa de captura on-screen ou `open()` após frame estável.
- Não exercitou: diálogos de confirmação/plan token, theme editor detalhe, dossiê de jogo editorial, first-run, Game Mode Godot (ausente).
- Não é gate de CI; é evidência para design QA.

---

## Artefatos de tooling criados

| Arquivo | Função |
|---|---|
| `tools/ui_audit_capture.qml` | Percorre seções, sub-áreas Steam, áreas de emulação, views de biblioteca |
| `tools/ui_audit_runner.py` | Sobe bridge real, grava PNGs + `MANIFEST.json` |
| Alias `editorialLibraryControl` em `Main.qml` | Permite o harness controlar a biblioteca editorial |

---

## Veredito executivo

A central **já tem ossatura de produto forte** em **Steam Gameplay** e **Emulação (Switch)**, com honestidade operacional (stale, CloudPort ausente, cast não configurado). O tema editorial mineral claro **expõe um bug P0 de contraste** (`DarkButton`), e várias seções de segundo nível (**Perfis, Sync, Cast, Temas, Biblioteca sem mídia**) ainda parecem **fundação técnica**, não jornadas fechadas. Para auditoria de design, use preferencialmente:

**`docs/09-operations/evidence/2026-08-11-ui-audit/live/`**
