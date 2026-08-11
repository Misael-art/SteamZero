# PROMPT — Fechar lacunas da auditoria visual UI SteamZero (2026-08-11)

Copie **tudo abaixo da linha** para o agente implementador.

---

## 1. Papel e missão

Você é o implementador sênior de UI/UX do **SteamZero** (Desktop Qt/QML). Sua missão é **corrigir as lacunas da auditoria visual de 2026-08-11** — não redesenhar o produto, não inventar backend, não instalar no host.

**Fonte da auditoria (leia antes de codar):**

1. `docs/09-operations/evidence/2026-08-11-ui-audit/AUDIT-REPORT.md` — achados P0–P3, jornadas, backend↔UI  
2. Prints de referência: `docs/09-operations/evidence/2026-08-11-ui-audit/live/*.png`  
3. `docs/07-ui-ux/UX-PRINCIPLES.md`, `ERROR-UX.md`, `STEAMZERO-EDITORIAL-DESIGN-BIBLE.md`  
4. `docs/07-ui-ux/HANDHELD-BACKEND-UI-COVERAGE.md` — o que a bridge **não** publica (não invente botões de mutação)  
5. `src/steamzero/ui/qml/FUNCTION-PROVENANCE-UI-AUDIT.md` e `RESPONSIVE-DIAGNOSTIC.md`  
6. `AGENTS.md` na raiz — gates, escopo, proibições de host

**Princípios inegociáveis nesta tarefa:**

- QML só apresenta e chama rotas allowlisted. Sem shell, sem mutação direta de host.  
- Ausência de contrato = empty-state / disabled com **razão**, nunca falso “ok”.  
- Tema claro e tema escuro + alto contraste devem permanecer legíveis.  
- Não enfraquecer testes; se o contrato visual mudou de verdade, documente no commit.  
- Não construir wheel/release; não instalar com `bigsudo`; não editar `/opt`, `/etc`, `/boot`.  
- Independência PhaseZero/RetroDECK/LinuxToys (sem strings de referência).

---

## 2. Branch e escopo de arquivos

```bash
git fetch origin
git checkout -b fix/ui-audit-2026-08-11 origin/main   # ou a base que o operador indicar
```

**Escopo permitido (só estes caminhos, salvo alias mínimo já existente):**

| Área | Caminhos |
|---|---|
| Shell / seções | `src/steamzero/ui/qml/Main.qml` |
| Controles base | `src/steamzero/ui/qml/DarkButton.qml`, `UiTokens.qml`, `ThemeBridge.qml`, `SectionCard.qml`, `EmptyState.qml` |
| Home / biblioteca | `EditorialHome.qml`, `EditorialLibrary.qml` |
| Steam | `SteamGameplay.qml` |
| Emulação | `Emulation.qml`, trechos de dispatch em `Main.qml` (`performRowAction` / `performEmulationAction` / `onComponentActionRequested`) |
| Workspace emulação (se CTA do card exigir) | `src/steamzero/adapters/emulation.py` (`build_global_management` / platformCards) — **só** se necessário para action de instalar no card; manter contratos honestos |
| Testes emulação/component | `tests/qml/*`, `tests/unit/*emulation*`, `tests/integration/*` relacionados a plan/install |
| Temas UI | `ThemeEditorPanel.qml` |
| Cast UI | trecho de cast em `Main.qml` (apresentação) |
| Perfis UI | trecho de perfis em `Main.qml` |
| Sistema UI | trecho de sistema em `Main.qml` (ordem/hierarquia) |
| Assets | `src/steamzero/ui/assets/*` (só se ícone já existir e allowlisted via `PackagedAssets`) |
| Testes | `tests/qml/*`, `tests/unit/*` / integration se tocar bridge só em apresentação |
| Tooling de prova | `tools/ui_audit_capture.qml`, `tools/ui_audit_runner.py` (opcional, só se precisar de captura de regressão) |

**Fora de escopo (registre no relatório final, não implemente):**

- Game Mode Godot, QAM/Decky  
- CloudPort / mutações de sync (backend ausente)  
- Orquestrador de cast real se não estiver configurado  
- Jobs top-level / BIOS center / Storage top-level na nav (exige IA + contratos novos)  
- G12 escala de fonte do host (KNOWN-GAPS — só se sobrar tempo e sem reflow massivo)  
- Instalação de release no host  

Se precisar de arquivo compartilhado além do escopo: **não edite**; liste no relatório.

Antes de começar: leia `docs/ACTIVE-WORK.md` e registre workstream em `docs/status/workstreams/` se o operador exigir.

---

## 3. Ordem de execução (obrigatória)

Feche em ondas. **Não pule P0.** Após cada onda: gates da seção 6.

### Onda A — P0 (instalação de emuladores + contraste)

> **Prioridade do operador (2026-08-11):** a auditoria inicial sub-representou a
> instalação dos demais emuladores. **A0 é obrigatória e vem antes de polish visual.**
> Detalhe completo: seção “Instalação de emuladores” em `AUDIT-REPORT.md`.

#### A0. Instalação de emuladores: falso botão + deslocamento (P0-4, P0-5) — **PRIMEIRO**

**Sintomas (host real):**

1. Em **Gestão geral**, cards de plataforma mostram bloqueador *“o emulador desta plataforma não está instalado”* mas o único botão é **“Abrir plataforma”** — a instalação não está no primeiro fold da jornada.  
2. No painel **“Componentes e emuladores”** (muitas vezes abaixo da dobra) existem botões **“Instalar”** / **“Reparar”** com `enabled: true`.  
3. Esses botões chamam `componentActionRequested` → `performRowAction`, que só trata `action.kind` (`component-plan`, …).  
4. O workspace publica ações no formato de emulação:  
   `action = { id: "emulator.install:dolphin", label: "Instalar", enabled: true }` (**sem** `kind`).  
5. Resultado: **clique habilitado, zero efeito, sem erro** = botão falso.  
6. O handler correto já existe: `performEmulationAction` trata `emulator.install:` / `update:` / `uninstall:` / `repair:` via `emulator.plan` + diálogo de confirmação.  
7. Lista legada de emuladores em `Main.qml` (`visible: false`) usa outro contrato (`dashboard.components` + `component-plan`) — instalação **deslocada** para código morto.  
8. Lifecycle tem **~33** componentes instaláveis; `globalManagement.emulators` mostra **~13** — o resto some da UI.

**Faça (ordem interna de A0):**

1. **Wiring (obrigatório)**  
   - Em `Main.qml` `onComponentActionRequested`: se `component.action.id` existir (padrão emulação), chamar `performEmulationAction(component.action)`; se `component.action.kind` existir (padrão dashboard), manter `performRowAction(component)`.  
   - Alternativa aceitável: `performRowAction` delega para `performEmulationAction` quando `kind` ausente e `id` casa com `emulator.(install|update|uninstall|repair|launch|stop):`.  
   - Nunca engolir o clique em silêncio: se action enabled mas não roteada → `notify(..., true)` com mensagem clara.

2. **Prova automatizada (obrigatório)**  
   - Teste QML ou unitário do dispatch: payload sintético `emulator.install:dolphin` **deve** resultar em pedido `emulator.plan` (mock/spy da bridge), não no-op.  
   - Caso `kind: "component-plan"` continua a funcionar (não regredir dashboard).

3. **Reestruturar a jornada de instalação (obrigatório na UI)**  
   - Painel **“Componentes e emuladores”** sobe para o **primeiro fold** da Gestão geral (antes ou ao lado dos cards de plataforma), com título humano (“Instalar e reparar emuladores”) e contagem instalados/ausentes/atenção.  
   - Card de plataforma com emulador ausente:  
     - CTA primário: **Instalar &lt;emulador principal&gt;** se o workspace já expuser action de install do default (senão, CTA “Ver emuladores para instalar” que rola/foca o painel de componentes — **não** inventar plan sem action).  
     - CTA secundário: “Abrir plataforma”.  
   - Não mentir: se installable=false, botão disabled + `reason` do backend.

4. **Runtime honesto no card (obrigatório)**  
   - Não listar 10 emuladores não instalados como “Runtime: …”. Preferir: instalados por nome + “N não instalados” ou só o primary + contagem.  
   - Implementação preferida na **projeção QML** se o payload for rico o bastante; senão ajuste mínimo em `build_global_management` mantendo schema.

5. **Uma superfície de instalação**  
   - Ou remove o bloco legado `visible: false` da lista de emuladores em `Main.qml` (morto), ou documenta no commit por que fica — **não** manter dois fluxos divergentes sem dono.  
   - Preferência: dono único = `Emulation.qml` + `performEmulationAction` / `emulator.plan`.

6. **Cobertura dos “demais” emuladores (mínimo honesto)**  
   - Se os 20+ componentes fora dos 13 forem intencionalmente filtrados, a UI deve dizer “Mostrando emuladores das plataformas ativas” + caminho para o restante **somente se** já houver read model (ex. `dashboard.components`).  
   - Se `dashboard.components` já lista os 33 com `component-plan`, pode haver seção “Outros componentes” que usa `performRowAction` corretamente — sem misturar shapes de action no mesmo botão sem normalizar.  
   - **Não** chamar install real no host nos testes; só plan mock / UI.

7. **Diálogo de plano**  
   - Confirmar que `emulationDialog` abre após plan bem-sucedido e que cancelamento não deixa estado sujo.  
   - Copy do diálogo: nome do emulador, executor (flatpak/appimage) se já vier no plan, rollback prometido.

**Prova visual A0:**

- Recaptura `emulation-global-management` / `studio-emulators`: painel de instalação visível sem scroll infinito; cards não prometem runtime fantasma.  
- Manual ou harness: clique Instalar em item missing → diálogo de plano (com bridge mock) ou erro explícito se bridge recusar — **nunca** silêncio.

**Critério de aceite A0:**

- [ ] `emulator.install:*` enabled → entra em `emulator.plan` (ou erro visível)  
- [ ] Zero botão “Instalar” que seja no-op  
- [ ] Plataforma sem emulador não oferece só “Abrir” como se bastasse  
- [ ] Lista de instalação no primeiro fold da gestão geral  
- [ ] Runtime do card não lista ausentes como se estivessem ativos  
- [ ] Teste de regressão do dispatch verde  

#### A1. `DarkButton` tema-aware (P0-1, P0-2)

**Problema:** `DarkButton.qml` força `#f2f6fb` no texto. No tema mineral claro, os botões “AÇÕES DO SISTEMA” (Quick Reset, Cloud Sync, doctor) e outros CTAs ficam **retângulos brancos sem label**.

**Faça:**

1. Refatore `DarkButton.qml` para **não hardcodar** cor de texto.  
   - Aceitar `palette.buttonText` / propriedade opcional `labelColor` do pai, **ou**  
   - Consumir cor via `required property color textColor` / binding do shell.  
2. Em `Main.qml`, nos `DarkButton` da sidebar e demais usos com fundo claro, passar `textColor` / `mutedColor` do tema (`root.textColor`).  
3. Manter legível em: tema claro default, tema escuro se houver, `highContrast`.  
4. Se o botão for “primary” (fundo accent), texto deve ser o de contraste do accent (ex. branco sobre ciano), via propriedade `primary: true` — **sem** voltar a hardcodar o caso geral.  
5. Ícones: se `icon.name` do tema KDE some no software renderer, preferir `ModernIcon` / `NavigationIcon` já do produto onde o shell já usa isso, **sem** criar SVG artesanal.

**Prova:**

- Harness QML ou teste existente de high-contrast/shell: texto dos três botões de AÇÕES DO SISTEMA com contraste suficiente (não branco-em-branco).  
- Recaptura:  
  `python tools/ui_audit_runner.py --offline --outdir /tmp/ui-audit-p0`  
  e inspecionar `studio-overview.png` / `fullhd-overview.png` — labels legíveis.

#### A2. Biblioteca com presença visual (P0-3)

**Problema:** 14 jogos Steam, carousel/grid sem capas; só título no rodapé; chips “Gênero/Ano/Desenvolvedor: não publicado” parecem filtros mortos.

**Faça (somente com dados já publicados no read model):**

1. Em `EditorialLibrary.qml`:  
   - Se `coverUrl` / asset de mídia existir no jogo, mostrar capa (`SceneImage` / fluxo já usado).  
   - Se **não** existir: empty de capa com marca do sistema + título (não área em branco).  
2. Ocultar chips de metadados cujo valor seja vazio / “não publicado” / não presente no payload — **não** mostrar chip morto.  
3. Empty-state quando `visibleGames.length === 0`: mensagem + CTA allowlisted se existir (`library.scan` / navegar para Emulação), senão só orientação honesta.  
4. Não inventar URLs de capa; não baixar mídia no QML.

**Prova:** captura `library-games-carousel` / `grid` / `list` com ao menos título + tile legível; chips ausentes quando não há metadados.

---

### Onda B — P1 (jornadas e hierarquia)

#### B1. Um único “inbox” de atenção Desktop (P1-1)

**Problema:** banner stale em 100% das telas + card “Estado desatualizado” na sidebar + card Pendências na home competem.

**Faça:**

1. Manter honestidade do `truthState === "stale"` / conflicts / recovery.  
2. Banner global:  
   - CTA único claro (“Revisar perfis” → seção `profiles` **ou** Steam→Modo Desktop se for o fluxo canônico já ligado).  
   - Permitir **reconhecer/dispensar** na sessão (já existe padrão de alerta compacto nos goldens `deck-alert-compact`); não apagar o truth do backend.  
3. Evitar três cópias do mesmo texto na mesma viewport: se o banner está expandido, o card de Pendências na home pode apontar resumido ou esconder duplicata.  
4. Sidebar attention button: manter, mas alinhar copy com o banner (mesmo verbo).

**Prova:** com fixture/status `stale`, no máximo **um** bloco explicativo longo visível por vez; dismiss compacta o banner sem mentir o estado.

#### B2. Seção Perfis com quadro 4-estados (P1-2)

**Problema:** só combobox “Automático”.

**Faça (UI sobre payload já em `desktopStatus`):**

1. Cards ou segmented control para perfis conhecidos: **Automático / Portátil / Dock / Seguro** (ids já usados no domínio: `auto`/`handheld-desktop`/`docked-desktop`/`safe` — confira no código, não invente ids).  
2. Em cada card ou no resumo: **Recomendado · Desejado · Aplicado · Observado** (campos já no status; se `null`/`unverified`, rótulo “não verificado”, nunca falso aplicado).  
3. CTA “Revisar alterações” / plan+apply **somente** via rotas já allowlisted (`desktop.profile.plan` / `apply`).  
4. Reutilize padrões visuais de `SteamGameplay` área Modo Desktop se já mostrarem esse quadro — **não duplique lógica de domínio no QML**.

**Prova:** `studio-profiles` deixa de ser uma linha vazia; estados distintos visíveis com fixture stale.

#### B3. Sync — empty-state de produto (P1-3)

**Problema:** três zeros + texto técnico de CloudPort.

**Faça:**

1. Quando provider ausente: um `EmptyState` com título humano, o que falta (CloudPort autenticado), e o que o usuário **não** pode fazer ainda.  
2. Esconder ou colapsar os três contadores 0/0/0 quando não há provider (ou mostrar como “—” desabilitados).  
3. Manter “Atualizar status” se a rota existir.  
4. **Não** criar botões de retry/resolve de conflito (backend N/A — ver HANDHELD-BACKEND-UI-COVERAGE).

#### B4. Transmissão — shell de produto (P1-4)

**Problema:** botões nativos empilhados.

**Faça:**

1. Envolver em `SectionCard` / layout editorial: título, status do orquestrador, empty-state se “não configurado”.  
2. Agrupar ações primárias vs secundárias; desabilitar ações impossíveis com `reason` se o payload trouxer.  
3. Sem inventar pairing real se o backend disser não configurado.

#### B5. Aba Temas funcional de ponta a ponta (P0-6 + P1-5) — **obrigatória**

> A passagem visual só marcou layout (P1-5). Revalidação de código mostrou a aba
> **incompleta como produto**: backend de apply/editor existe; a UI não fecha a jornada.
> Detalhe: seção “Aba Temas” em `AUDIT-REPORT.md`.

**Sintomas:**

1. **Não há botão Aplicar / “Usar este tema”** — contratos `theme.apply` + `theme.apply.confirm` existem e a CLI aplica; a lista só tem “Editar”.  
2. **Export** chama `document.createElement` / `document.body` (API de browser) → **não funciona no Qt/QML**.  
3. Temas **builtin** abrem com “Editar” mas vêm **readOnly** (Salvar morto) — parece bug; falta “Duplicar e editar” / “Aplicar”.  
4. Lista: nome sob o botão Editar; sem swatch; sem marca de tema **ativo** (`activeId`).  
5. `ThemeEditorPanel` é `Rectangle` com `ColumnLayout` filho usando `Layout.*` (anexos inválidos fora de Layout) + embed em `ScrollView` sem altura explícita — sizing frágil.

**Faça (ordem interna B5):**

1. **Aplicar tema (P0)**  
   - Em cada linha da lista: CTA **Aplicar** (ou “Usar”) se o tema não for o ativo.  
   - Fluxo: `requestAction("theme.apply", {themeId})` → mostrar plano (preview + rollback guarantee) → confirmar com `theme.apply.confirm` `{planId, confirmToken}`.  
   - Reutilizar padrão de diálogo de plano já usado no Desktop/emulação (não inventar apply sem token).  
   - Após sucesso: `refreshStatus` / `refreshThemeList` e destacar ativo.  
   - Tema já ativo: badge “Em uso”, Aplicar disabled ou oculto.

2. **Nativos vs usuário (P0)**  
   - Builtin: primário **Aplicar**; secundário **Duplicar e editar** (`theme.editor.create` com `extends: themeId` — o POST `/theme/editor/create` já aceita `extends` no dashboard).  
   - Não rotular “Editar” um tema read-only sem aviso; se só houver load read-only, copy: “Ver (somente leitura)”.

3. **Export (P0)**  
   - Remover qualquer uso de `document.*`.  
   - Opções aceitáveis:  
     a) desabilitar Export com `reason` honesto + notify;  
     b) FileDialog Qt + bytes do export, sem shell.  
   - Preferir (a) se (b) exigir superfície nova não allowlisted.

4. **Layout da lista (P1-5)**  
   - Row: `[swatch]` · `nome + autor · vX + origem` · `[Aplicar] [Editar|Duplicar]`.  
   - `elide` no texto; ações com largura reservada; altura ≥ 48/72 touch.  
   - Empty-state se lista vazia ou bridge down.

5. **Shell do painel**  
   - `ThemeEditorPanel`: `anchors` / `implicitHeight` corretos; conteúdo rolável sem cortar “Criar”.  
   - Em `Main.qml`, dar altura útil à seção Temas (não só `width`).

6. **Erros e contratos**  
   - create/load/save/apply: sempre feedback (`notify` ou ErrorCard); zero silêncio.  
   - Confirmar que `/status` publica `uiContracts.byId["theme.apply"]` etc. — se faltar, corrigir publicação; não hardcodar URL na QML.

7. **Testes**  
   - Estender `tests/qml/check_theme_editor_aura.qml` (ou novo harness):  
     - mock `theme.apply` + confirm na ordem certa;  
     - export **não** referencia `document`;  
     - tema ativo exibe badge;  
     - read-only não oferece Salvar enabled.

**Prova B5:**

- Bridge live ou mock: aplicar AURA/steamdeck → `activeId` muda e UI reflete.  
- Captura `studio-themes`: nomes legíveis, Aplicar visível, ativo marcado.  
- Export: disabled honesto **ou** ficheiro sem DOM.

**Critério de aceite B5:**

- [ ] Utilizador aplica um tema instalado só pela UI (plan+confirm)  
- [ ] Tema ativo visível na lista  
- [ ] Builtin: Aplicar + edição que não finja Salvar em read-only  
- [ ] Export sem `document.*`  
- [ ] Layout sem overlap nome/botão  
- [ ] Teste de regressão apply + export verde  

#### B6. Home: capa + sem stack legado (P1-6, P1-10)

**Problema:** destaque sem capa; EditorialHome + blocos legados (“Visão geral / Continuar jogando / …”) empilhados.

**Faça:**

1. `EditorialHome`: se o jogo em destaque tem `coverUrl`/arte no payload, mostrar; senão placeholder com sistema.  
2. Em `Main.qml` seção overview: **remover ou ocultar** o stack legado que duplica EditorialHome (labels “Visão geral”, repeater de playtime duplicado, etc.), **desde que** nenhuma ação allowlisted fique sem caminho (playtime/continue devem existir na home editorial ou em atalho explícito).  
3. Sistemas com 0 jogos: na home, preferir “com biblioteca” primeiro ou limitar o rail; “Todos os sistemas” leva à grade completa (Biblioteca).

#### B7. Handheld reflow (P1-7)

**Problema:** 949×593 corta cards e footer cobre CTAs.

**Faça:**

1. Respeitar `bottomSafeInset` / footer em `EditorialHome` e overview.  
2. Em `handheldLayout` / `compactLayout`: reduzir margens, garantir scroll até o último CTA, não esconder primary action sob o footer.  
3. Reusar padrões de `check_handheld_*` / goldens deck.

#### B8. Sistema: saúde primeiro (P1-8)

**Faça:**

1. Reordenar a seção Sistema: **Doctor / prontidão / attention** acima de “Consumo de memória”.  
2. Memória permanece, mas não é o primeiro fold em estado degraded/stale.  
3. Sem novos endpoints.

#### B9. Steam truncamento (P1-9)

**Faça:**

1. Em Ambiente, labels de estado com `wrapMode` ou duas linhas; “Feral GameMode — …” não deve cortar no meio da palavra sem tooltip/`Accessible.name` completo.  
2. Alvo mínimo de toque preservado.

---

### Onda C — P2 (organização e polish de produto) — se tempo permitir na mesma branch

Priorize nesta ordem:

| ID | Ação mínima |
|---|---|
| P2-10 | Chips metadados: só se valor real (ligado a A2) |
| P2-3 / P2-4 | Biblioteca: ícones de plataforma via `PackagedAssets` quando o id tiver asset; sistemas 0 jogos menos proeminentes |
| P2-6 | Cards de gestão global: resumir runtimes (“N emuladores”) + expandir detalhe, não lista de 10 nomes no primeiro fold |
| P2-5 | Nav Steam: label estável (“Steam”), sem subtítulo “Gameplay” só quando selecionado — ou subtítulo sempre se for intencional |
| P2-9 | Footer de glifos: ocultar ou suavizar quando não há indício de gamepad (`currentInput` / capability); se o payload não tiver, **não inventar** — no máximo reduzir ênfase visual no Desktop pointer |
| P2-11 | Coleções: copy “ainda não há coleções” + como criar **se** rota existir; senão disabled com reason |
| P2-12 | TDP: se valor default for mínimo do hardware, rotular “mínimo do dispositivo” / alinhar ao recommended do perfil — sem inventar watts |

**Não faça nesta branch (P2-1 Jobs/BIOS nav):** mudar IA da sidebar exige decisão de produto + contratos; só documente como follow-up.

---

## 4. O que NÃO fazer

- Não inventar CloudPort, jobs UI, BIOS center, first-run, Game Mode Godot.  
- Não “consertar” empty-state mentindo dados.  
- Não adicionar dependências, wheels em `dist/`, nem tocar instalador.  
- Não rodar `bigsudo` / install host.  
- Não copiar código de `reference/`.  
- Não formatar o repo inteiro; só arquivos da mudança.  
- Não commitar binários de auditoria em massa se forem pesados — evidência de regressão pode ir em `/tmp` ou `docs/09-operations/evidence/` só se o operador pedir.

---

## 5. Testes e gates (após CADA onda)

```bash
.venv/bin/python tools/run_tests_isolated.py tests -q
# se a suíte integral for pesada demais entre ondas, no mínimo:
.venv/bin/python tools/run_tests_isolated.py tests/qml tests/unit/test_desktop_dashboard.py tests/integration/test_desktop_ui_bridge.py -q

.venv/bin/ruff check src tools tests
.venv/bin/ruff format --check src tools tests
.venv/bin/mypy src
make independence boundaries
```

QML:

- `qmllint` nos arquivos QML tocados (se disponível no host).  
- Harnesses existentes que cobrem shell/emulation/library/high-contrast: não piorar.  
- Recaptura seletiva:  
  `python tools/ui_audit_runner.py --offline --outdir /tmp/ui-audit-after-A`  
  (e live se o operador autorizar bridge local).

**Critério de aceite (onda A):**

- [ ] **A0 completo** (dispatch install + jornada + teste)  
- [ ] Labels Quick Reset / Cloud Sync / doctor legíveis no tema claro  
- [ ] DarkButton primary e secondary legíveis claro + alto contraste  
- [ ] Biblioteca não é um vazio branco com 14 jogos  

**Critério de aceite (onda B):**

- [ ] Perfis mostram quadro de estados, não só combobox  
- [ ] Sync/Cast com empty-state/layout de produto  
- [ ] **B5 Temas completo** (Aplicar + ativo + export sem DOM + layout + testes)  
- [ ] Overview sem stack legado duplicado  
- [ ] Handheld: último CTA alcançável por scroll  
- [ ] Sistema: doctor/atenção acima de memória  

---

## 6. Commits sugeridos (pequenos e temáticos)

1. `fix(ui): wire emulator install actions to performEmulationAction`  
2. `fix(ui): resurface emulator install panel and honest platform CTAs`  
3. `test(ui): reject silent no-op on emulator.install dispatch`  
4. `fix(ui): make DarkButton consume theme text colors`  
5. `fix(ui): restore library tiles and hide unpublished metadata chips`  
6. `fix(ui): unify desktop attention banner and reduce duplication`  
7. `fix(ui): profile section four-state cards from desktopStatus`  
8. `fix(ui): product empty-states for sync and cast`  
9. `fix(ui): theme apply journey and list layout without DOM export`  
10. `test(ui): theme apply plan-confirm and reject browser export`  
11. `fix(ui): overview single editorial home and handheld safe insets`  
12. `fix(ui): system health above memory and steam env label wrap`  

Mensagens em prosa completa; sem “WIP”.

---

## 7. Entrega final (obrigatória)

Relatório ao operador com:

| Coluna | Conteúdo |
|---|---|
| Item (P0-x / P1-x) | Commit SHA |
| Testes que provam | nome do teste / harness / captura |
| Fora de escopo | o que sobrou e por quê |
| Host | **nenhuma** mutação de host (esperado) |
| Próximos passos do operador | recaptura live, validação física 1280×800, se quiser |

Atualizar se a governança do repo exigir: item em `docs/status/items/`, `make status-check`, fecho em `docs/WORKLOG.md` (**apenas append**).

Push **somente** da sua branch; sem force-push.

---

## 8. Evidência de partida (para você, agente)

Screenshots **antes** (não apague):

`docs/09-operations/evidence/2026-08-11-ui-audit/live/`

Arquivos âncora do bug P0:

- `studio-emulators.png` / `emulation-global-management.png` — cards só “Abrir plataforma”; install deslocado  
- `studio-overview.png` — botões AÇÕES DO SISTEMA brancos  
- `library-games-carousel.png` — biblioteca sem mídia  
- `studio-profiles.png` — perfis vazios  
- `studio-sync.png` / `studio-cast.png` / `studio-themes.png` — Temas: sem Aplicar, layout  
- `handheld-overview.png`  
- `studio-steam.png` — truncamento GameMode  

Código âncora Temas (B5):

```118:140:src/steamzero/ui/qml/ThemeEditorPanel.qml
// Criar Novo Tema — existe; falta Aplicar na lista
```

```209:220:src/steamzero/ui/qml/ThemeEditorPanel.qml
// só "Editar" → theme.editor.load; sem theme.apply
```

```340:350:src/steamzero/ui/qml/ThemeEditorPanel.qml
// export com document.createElement — inválido no QML
```

```1221:1248:src/steamzero/adapters/desktop_contracts.py
// theme.apply / confirm / rollback — contratos órfãos na UI
```

Código âncora (A0 — **começar aqui**):

```3545:3548:src/steamzero/ui/qml/Main.qml
// onComponentActionRequested → performRowAction  (ERRADO para action.id de emulação)
```

```928:958:src/steamzero/ui/qml/Main.qml
// performRowAction só lê action.kind — ignora emulator.install:*
```

```1014:1027:src/steamzero/ui/qml/Main.qml
// performEmulationAction JÁ trata emulator.install → emulator.plan + diálogo
```

```1890:1919:src/steamzero/ui/qml/Emulation.qml
// painel Componentes e emuladores: Button Instalar → componentActionRequested
```

```6:16:src/steamzero/ui/qml/DarkButton.qml
// palette/contentItem hardcoded #f2f6fb — corrigir na onda A1
```

```2824:2898:src/steamzero/ui/qml/Main.qml
// AÇÕES DO SISTEMA: quickResetButton, cloudSyncButton, doctorButton
```

Comece pela **Onda A0** (install de emuladores). Só depois A1/A2 e onda B.  
Na onda B, **B5 (Temas) é obrigatória** — não encerre só com polish de lista.  
Não declare a tarefa completa sem os checkboxes da seção 5 verdes, **incluindo A0 e B5**.
