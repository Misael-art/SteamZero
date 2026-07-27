# Prompt — normalização pré-release (emulação + temas + transmissão)

Copie o bloco abaixo para uma nova tarefa do agente executor.

O revisor desta tarefa é um segundo agente, que auditará commit a commit e
reexecutará todos os gates. Não escreva no relatório final nada que você não
possa provar com comando reexecutável.

```text
# Tarefa — normalizar o SteamZero para uma release íntegra e instalável

Você está normalizando o repositório SteamZero em
`/mnt/sdcard/Projects/Port_Steam` (use SEMPRE este caminho absoluto; existe
outro repositório parecido nesta máquina e agentes já auditaram o errado).

O objetivo NÃO é acrescentar funcionalidade nova. É tornar funcional, robusto,
integrado e resiliente aquilo que já foi construído e mergeado, de modo que a
próxima release possa ser buildada, instalada no host e testada fisicamente sem
repetir a quebra da `0.1.0a37`.

P2P / pareamento remoto fica EXPLICITAMENTE FORA DE ESCOPO. Não comece, não
esboce, não deixe stub novo. É o único item que permanece pendente por decisão
do operador.

## Contexto verificado — não regenere estas conclusões

Tudo abaixo foi confirmado por leitura direta da árvore em 2026-07-27, no
commit `a830b88` mais as mudanças QML ainda não commitadas. Cite estes achados;
não os reinvestigue do zero. Mas CONFIRME que continuam válidos antes de editar
cada arquivo, porque outra sessão pode ter mexido na árvore.

### Estado real dos gates (reexecutado, não copiado de relatório)

No commit `a7505ae`, em worktree isolado com `PYTHONPATH` forçado:

- `pytest tests -q` → 1844 passed in 161.45s
- `ruff check src tools tests` → All checks passed
- `mypy src` → 162 source files, no issues
- `check_independence.py` → OK; `lint_boundaries.py --root src` → 0 violações

No working tree atual (`a830b88` + QML não commitado):

- `pytest tests -q` → 1949 passed in 158.73s
- `ruff check src tools tests` → All checks passed
- `mypy src` → 169 source files, no issues
- `make independence boundaries` → OK, 0 violações
- `pytest tests/integration/test_qml_handheld_offscreen.py -q` → 10 passed
  (`qml6` ESTÁ instalado em `/usr/sbin/qml6`; os harnesses NÃO são pulados)

Ou seja: os quatro gates estão verdes, e continuaram verdes durante toda a
regressão da a37. Gates verdes foram exatamente a falsa segurança que levou o
host a quebrar. Todo defeito listado abaixo convive com gates verdes. Seu
trabalho só está pronto quando existir um teste que FALHE sem a sua correção.

### D1 — o instalador ainda não reinicia o daemon (causa raiz da a37, NÃO corrigida)

`tools/install_host.py::_activate()` (definido na linha 707, chamado em 891,
960 e 971) troca `current`, links e units, mas não contém nenhuma chamada de
`systemctl`, `daemon-reload` ou restart. A única ocorrência da palavra
`restart` no arquivo inteiro é um comentário na linha 444.

Consequência já observada fisicamente: após promover a a37, o
`steamzero-core.service` continuou executando o Python da release a35, e a CLI
a37 recebia snapshots do daemon a35 — o que produziu os sintomas de "ícones
sumiram" e "keys/firmware sumiram". Promover qualquer release nova hoje
reproduz o mesmo defeito. Este é o item de maior risco da tarefa e bloqueia
qualquer instalação no host.

### D2 — a central de emulação continua Switch-only

- `src/steamzero/domain/emulation_workspace.py:113-120`: o payload publica o
  Switch composto operacionalmente e TODAS as demais plataformas via
  `platform_placeholder(manifest)`.
- `src/steamzero/adapters/emulation.py:127`:
  `_MANAGED_EMULATORS = frozenset({"eden", "citron", "ryubing"})`.
- `src/steamzero/adapters/emulation.py:129`: `_EMULATOR_PRESENTATION` cobre os
  mesmos três.
- `emulation.py:5253`, `:5300` e `:6065` bloqueiam por essa allowlist.
- `src/steamzero/adapters/manifests/` declara 16 adapters: azahar, cemu,
  citron, dolphin, duckstation, eden, flycast, melonds, pcsx2, ppsspp,
  retroarch, rpcs3, ryubing, sunshine, xemu, xenia-canary. Treze emuladores
  declarados; três operacionais.
- Mesmo no Switch, `emulation_workspace.py:322-346` publica `keys.import` e
  `firmware.import` com `enabled=False` e motivo "Importação pela interface
  ainda não está conectada ao serviço"; `requirements.verify` idem.

Ou seja: os merges de plataformas clássicas e standalone entregaram manifests,
não integração. Isto é o item R4/R5/R6 do prompt da a37, nunca executado.

### D3 — marketplace de temas aponta para infraestrutura inexistente

- `src/steamzero/domain/theme_marketplace.py:20`:
  `_DEFAULT_CATALOG_URL = "https://themes.steamzero.org/catalog-v1.json"`.
  Essa string aparece SOMENTE nessa linha em todo o repositório: não há ADR,
  documento, runbook nem fixture que descreva quem opera esse host.
- `_catalog_url()` aceita `STEAMZERO_THEMES_CATALOG_URL` do ambiente sem
  nenhuma validação de esquema ou host.
- `ThemeMarketplace.install()` faz `checksum = entry.checksum_sha256 or None`:
  se o catálogo omitir o campo, o pacote é instalado SEM verificação de
  integridade.
- `src/steamzero/domain/theme_install.py:130` usa
  `allowed_hosts=frozenset({"*"})`. É a ÚNICA `NetworkPolicy` com curinga em
  todo o código; anula a fronteira de allowlist que `core/net.py` existe para
  impor.
- `MarketplaceTheme.from_dict` levanta `KeyError` cru em `raw["id"]` e
  `ValueError` cru em `int(str(raw.get("size") or 0))` e
  `float(str(raw.get("rating") or 0.0))`. Catálogo malformado quebra fora do
  catálogo de erros estruturados, violando AGENTS.md §8 ("falha degrada, nunca
  trava").

Combinados: um catálogo não confiável, sem checksum obrigatório, com host
curinga, instalando conteúdo que a UI vai carregar. É a superfície mais
perigosa introduzida pelos commits não validados.

### D4 — editor visual de temas tem caminho que reporta sucesso sem fazer nada

- `src/steamzero/domain/theme_editor.py:190-202` — `set_asset()` valida slot,
  tamanho e extensão, marca `dirty=True`, retorna `{"asset": {...}}` e
  **descarta o parâmetro `data`**. Nunca escreve em `session.assets`, nunca
  persiste bytes. É sucesso reportado sobre operação inexistente.
- `set_asset` também não está entre as 8 ações declaradas em
  `src/steamzero/adapters/desktop_contracts.py:982-1055` (load, create,
  set-tokens, set-metadata, preview, save, export, cancel). Logo é código morto,
  inalcançável pela API e não testado.
- `theme_editor.py:269-297` — `export_zip()` grava o manifesto em
  `{theme_id}/theme.json`, mas os assets em `assets/...` na RAIZ do zip
  (`rel = asset_path.relative_to(session.theme_dir)`). Como
  `ThemeInstaller._find_theme_dir` (`theme_install.py:157-166`) escolhe o
  diretório que contém `theme.json`, um ciclo export → install PERDE todos os
  assets. O round-trip do editor está quebrado e nenhum teste cobre isso.
- `theme_editor.py:329-336` — `_validate_save()` valida o id com
  `mid.replace(".", "").replace("-", "").isalnum()`. Isso bloqueia `../`, mas
  `str.isalnum()` é Unicode-aware, então ids não-ASCII passam. Esse valor vira
  caminho de filesystem (`target = paths.themes_dir() / theme_id`, linha 218) e
  alvo de `fs.remove_tree(target)` quando `overwrite=true` (linhas 253-254). A
  validação precisa ser a do schema, ancorada, não heurística.

### D5 — integração de UI dos temas está inconsistente (mudanças NÃO commitadas)

- `src/steamzero/ui/qml/ModernIcon.qml:189` acrescenta o glyph
  `preferences-desktop-theme`, que **não é referenciado em lugar nenhum**. A
  navegação em `Main.qml:2293` e `Main.qml:2595` usa `applications-graphics`,
  ícone já usado por "Cache gráfico" em `Emulation.qml`. Glyph novo morto mais
  colisão semântica no glyph efetivamente usado.
- `Main.qml` coloca `ThemeEditorPanel` dentro de um `ScrollView` e define
  `Layout.fillWidth`/`Layout.fillHeight`. `ScrollView` não é um Layout: as
  propriedades anexadas são inertes e ainda conflitam com o `width:` explícito
  definido logo acima.
- A lista de seções existe TRÊS vezes sem fonte única: o mapa
  `{"overview": 0, ..., "themes": 7}` em `Main.qml:518`, o model de navegação
  duplicado em `Main.qml:2289` e `Main.qml:2591`, e a asserção
  `responsiveDrawerNavigation.count === 8` em
  `tests/qml/check_handheld_shell.qml`. O segundo model está com indentação
  quebrada, sinal de copy-paste. Qualquer seção futura vai dessincronizar.
- `src/steamzero/ui/qml/ThemeEditorPanel.qml:211` usa
  `panel.request("GET", "/theme/editor/load?themeId=" + ...)`, concatenando na
  query sem encoding, enquanto todas as outras operações do mesmo painel usam
  `panel.requestAction(...)`. Dois transportes para uma feature, e um deles
  ignora o envelope de ações.

### D6 — lacunas de teste que os gates não enxergam

- Nenhum teste em toda a árvore afirma `Image.status === Image.Ready`. A prova
  de que artwork de emulação realmente renderiza continua inexistente (era o
  item R2 do prompt da a37 e nunca foi feito). Os testes atuais só comparam
  strings de caminho.
- Nenhum harness QML exercita os fluxos interativos de `ThemeEditorPanel` ou
  `ColorPickerDialog`. Eles são instanciados indiretamente por
  `check_handheld_shell.qml`, o que prova ausência de warning, não comportamento.
- Nenhum teste afirma que o instalador reinicia o daemon, porque esse código
  não existe (D1).

### D7 — higiene da árvore

`git status` mostra, não rastreados: `wheelhouse/` (7,2 MB) e
`docs/diagnostics/` (28 KB). AGENTS.md §4 proíbe o agente de produzir artefatos
de release. NÃO os commite e NÃO os apague por conta própria: pergunte ao
operador a quem pertencem e registre a resposta no relatório.

### D8 — inventário de merge: o que main ainda NÃO tem

`main` existe localmente em `2aaa01d` ("release: prepare 0.1.0a37"). Atenção:
`origin/HEAD` aponta para `origin/codex/steam-gameplay-readiness-ui`, que está
em `456c7c6`, da era a35 — **`origin/HEAD` está desatualizado e não é a linha
principal**. Use `main` local como referência e confirme isso com o operador.

`codex/theme-framework` (a830b88) → `main`: **fast-forward puro**, 12 commits à
frente, 0 commits de `main` ausentes. Merge sem risco de perda.

O risco de perda está nas branches abaixo, medido com
`git merge-tree --write-tree main <branch>`:

| Branch | Commits fora de main | Conflitos | Conteúdo |
|---|---|---|---|
| `codex/ui-emulacao` | 11 | `Main.qml`, `docs/WORKLOG.md` | 3023 inserções em 39 arquivos: acessibilidade, rail com ícones, erro→impacto/ação, responsivo; **golden screenshots + `tst_responsive.qml` (414 linhas)** |
| `origin/codex/desktop-experience-input` | 8 | 8 arquivos, incl. `__init__.py`, `desktop_kde.py`, `install_host.py`, `Main.qml` | OSK wvkbd-mobintl/onboard, `KDEShortcutsEffect` com rollback, detector de input do Deck em status/doctor, runbook de instalação |
| `codex/estudo-emuladores-onda0-1` | 6 | só `docs/expansion/WI-S0.md` (add/add) | 1569 linhas de pesquisa: `STUDY-LEDGER.md`, `nes.md`, `retroarch.md`, `switch.md` |
| `codex/desktop-ergonomia-d0` | 3 | `ErrorCard.qml` (add/add), `Main.qml` | ERROR-UX estruturado do contrato error-v1 |
| `codex/midia-switch-scraping-ui-host-release-record` | 1 | `docs/WORKLOG.md` | só registro de WORKLOG |
| `codex/a37-emulation-recovery-prompt` (`4ecc7a6`) | 1 | — | **DUPLICATA**: `git diff 4ecc7a6 735fd2a -- src tests` é VAZIO. Mesmo código do commit já presente em `theme-framework`, só difere em docs |

Leituras obrigatórias deste inventário:

- `4ecc7a6` NÃO deve ser mergeado. É o mesmo contrato de tema que já entrou
  como `735fd2a`. Mergear duplica história e gera conflito inútil. Retire a
  branch com o operador em vez de integrá-la.
- `codex/ui-emulacao` é a branch que foi deliberadamente NÃO mergeada na a34
  por causa do volume de conflito no `Main.qml`; na ocasião só a acessibilidade
  foi portada. Ela ainda carrega a ÚNICA infraestrutura de teste responsivo
  golden do projeto. Descartá-la de novo significa perder isso definitivamente.
- `codex/desktop-ergonomia-d0` conflita em `ErrorCard.qml` como **add/add**:
  `main` já tem um `ErrorCard.qml` (veio de `codex/id-errorux-estruturado` na
  a34). Compare os dois antes de decidir; pode ser trabalho já superado.
- `origin/codex/desktop-experience-input` conflita em `src/steamzero/__init__.py`
  porque faz bump para `0.1.0a34`. É a assinatura de base obsoleta descrita em
  AGENTS.md §3. Rebase antes de integrar; nunca mergeie o bump de versão.
- `codex/estudo-emuladores-onda0-1` é só documentação e conflita em um único
  arquivo. É o insumo de pesquisa que alimenta N4/N5/N6 — integre cedo para o
  trabalho de emulação não redescobrir o que já foi estudado.

## Governança

1. Leia integralmente antes de editar:
   - `AGENTS.md` — as nove regras são inegociáveis;
   - `docs/expansion/PROMPT-A37-EMULATION-REGRESSION-RECOVERY.md` — esta tarefa
     é a continuação dele; os itens R1-R8 de lá permanecem válidos e não feitos;
   - `docs/05-data/PLATFORM-MANIFEST-V1.md`;
   - `docs/03-architecture/ADAPTER-MODEL.md`;
   - `docs/07-ui-ux/DESKTOP-MODE-UI.md`;
   - `docs/08-testing/TEST-STRATEGY.md`;
   - ADR-0019 (independência) e ADR-0020 (precedência de sessão).
2. Consulte a memória do projeto antes de propor arquitetura.
3. Trabalhe em branch própria, criada do tip que o operador aprovar. Nunca
   commite na branch de outro agente. Nunca force-push.
4. Se usar worktree, force `PYTHONPATH` para o `src` do worktree — gates
   rodados de worktree importam o `src` do checkout principal e mentem. Prove
   com `python -c "import steamzero; print(steamzero.__file__)"` antes do
   primeiro gate. O `Makefile` referencia `.venv/bin/python` por caminho
   relativo, então em worktree chame `tools/check_independence.py` e
   `tools/lint_boundaries.py` diretamente com o interpretador correto.
5. Todo comando shell começa com `rtk`.
6. Preserve alterações e untracked de outras frentes. Antes de tocar arquivo
   compartilhado (`Main.qml`, `desktop_dashboard.py`, `emulation.py`), confirme
   que não mudou desde o seu preflight, e isole a mudança em commit próprio, por
   último.

## Proibições

- Não use `sudo` nem `bigsudo`.
- Não instale, promova, reinicie, pare ou reverta nada no host. Esta tarefa NÃO
  autoriza ação de host.
- Não construa wheel, wheelhouse ou manifesto de release.
- Não abra, copie, imprima ou regrave conteúdo de keys, firmware ou ROMs.
- Não remova `state.db` nem "resolva" problema limpando cache ou configuração.
- Não habilite ação cujo caminho ainda termine em stub, placeholder ou erro
  previsível. Prefira `enabled=false` com motivo verdadeiro a botão que mente.
- Não enfraqueça, pule ou apague teste para passar gate.
- Não introduza shell, argv concatenado ou path não validado.
- Não reintroduza referências proibidas pelo ADR-0019.
- Não inicie P2P.

## Ordem obrigatória

Rode os quatro gates após CADA item, não só no fim.

### N0 — linha de base auditável e triagem de merge

Sem alterar código: registre commit-base, saída dos quatro gates nesse commit e
`git status` completo. Pergunte ao operador sobre `wheelhouse/` e
`docs/diagnostics/`. As mudanças QML hoje não commitadas só serão commitadas
depois de corrigidas em N8; até lá, apenas preserve.

Reproduza o inventário de D8 por conta própria — branches podem ter se movido:

```bash
rtk git rev-list --count main..<branch>
rtk git merge-tree --write-tree main <branch>
```

Apresente ao operador uma decisão explícita por branch — **integrar, rebasear
antes de integrar, portar seletivamente, ou aposentar** — com justificativa. Não
integre nada em N0 além do que for docs-only e sem conflito. Nenhuma branch é
descartada sem decisão registrada do operador: "não mergear" é uma decisão
válida, "esqueci dela" não é.

Ordem importa: as decisões sobre `codex/ui-emulacao`,
`origin/codex/desktop-experience-input` e `codex/desktop-ergonomia-d0` precisam
ser tomadas AGORA, porque as três tocam `Main.qml`, que N8 também reescreve.
Integrar depois de N8 duplica o conflito de propósito.

Commit: nenhum (relato e decisão apenas).

### N1 — coerência entre release, daemon e CLI  [P0, bloqueia release]

Corrija D1:

- a identidade de runtime expõe, no mínimo, package version, release id e
  source commit;
- cliente e daemon fazem handshake e detectam geração divergente;
- leitura pode falhar de forma estruturada ou cair em fallback comprovadamente
  read-only; mutação NUNCA é repetida nem enviada ao daemon errado;
- `_activate()` recarrega o user manager, reinicia apenas os units gerenciados
  pelo SteamZero e aguarda a identidade da nova geração;
- activation por socket não pode ressuscitar a release anterior;
- falha de reload/restart/handshake restaura `current`, units e daemon
  anteriores, ou termina em estado recuperável explicitamente documentado;
- `rollback` valida a identidade final do mesmo modo;
- nenhuma unit de terceiro é tocada; marcadores de ownership preservados;
- não mate PID diretamente como solução principal.

Testes: upgrade com process fake e manager fake; smoke read-only comparando
`manifest.sourceCommit == daemon.sourceCommit == doctor.sourceCommit`.

Commit: `fix(release): restart managed units and verify runtime generation`

### N2 — artwork de emulação comprovadamente renderizado

Corrija o primeiro item de D6. Resolva os assets empacotados de forma explícita
e allowlisted, funcionando em source tree E em wheel instalado. Aceite somente
assets declarados; nunca URL ou path vindo de dado externo; fallback
iconográfico apenas em erro real.

Teste `Image.status === Image.Ready`, com QML carregado a partir do pacote
instalado/desempacotado, para: Switch; Eden, Citron e Ryubing; cada asset
distinto das plataformas standalone; RetroArch compartilhado; e o fallback de
mídia de jogo.

Commit: `fix(qml): resolve packaged emulation artwork at runtime`

### N3 — preservação da verdade do Switch entre gerações

Fixture sintética de upgrade com key catalogada, firmware catalogado, três
emuladores instalados, biblioteca escaneada e mídia. Nunca use dado real do
operador em teste.

Prove que, após migração/upgrade: daemon e dashboard publicam os mesmos
requisitos; a UI mostra keys/firmware presentes; os três emuladores preservam
estado, ícone, ação e padrão; nenhuma reimportação é pedida enquanto as
projeções seguem válidas; ausência real oferece reparo sem apagar a origem;
nenhum refresh troca `ok` por `unverified` por usar builder simplificado.

Elimine a divergência entre o snapshot do `emulation workspace` e o do
Dashboard: um único composer operacional. Não mantenha duas verdades.

Commit: `fix(emulation): preserve switch truth across release generations`

### N4 — composer operacional dirigido por registries

Corrija D2. Substitua a composição Switch-only por composer genérico:

- `PlatformRegistry` define plataformas e precedência;
- `AdapterRegistry` define lifecycle e fontes;
- status real vem do executor correspondente;
- apresentação e ícone vêm de contrato versionado, não de dict Python;
- `_MANAGED_EMULATORS` e `_EMULATOR_PRESENTATION` deixam de ser allowlist
  manual;
- `platform_placeholder` permanece SOMENTE para capacidade explicitamente
  planejada, nunca para esconder adapter já declarado;
- adapter compartilhado (RetroArch) aparece em várias plataformas sem duplicar
  instalação física;
- falha de um adapter degrada apenas as plataformas dele;
- o read model informa `installed`, `installable`, `running`, versão, origem,
  health, ações e motivo verdadeiro.

Atualize schema e documentação no mesmo commit.

Commit: `refactor(emulation): compose operational platforms from registries`

### N5 — lifecycle por tipo de fonte (AppImage e Flatpak)

Fachada comum, executores especializados:

- AppImage/portátil continua no engine transacional com digest;
- Flatpak usa `FlatpakExecutor` com remote/ref/commit fixados;
- status detecta instalação real no escopo `--user`;
- plan/apply/verify/rollback continuam obrigatórios;
- install/update/uninstall nunca executam direto pela UI;
- `component-lock` e manifesto precisam concordar;
- fonte EOL ou incompatível falha fechado;
- abrir só emulador instalado; `stop` só atua sobre processo comprovadamente
  iniciado e gerenciado pelo SteamZero.

Cobrir: RetroArch, DuckStation, Dolphin, PCSX2, PPSSPP, Flycast, melonDS,
Azahar, Cemu, RPCS3, xemu, Xenia Canary, e Eden/Citron/Ryubing sem regressão.

Commit: `feat(emulation): route emulator lifecycle by pinned source type`

### N6 — launch declarativo e biblioteca por plataforma

Estenda o manifesto com contrato fechado, versionado, validado por schema e
documentado: modo de execução derivado da fonte (nunca comando livre);
`openArgs`/`gameArgs` como arrays; placeholders allowlisted (`{rom}` e o mínimo
necessário); ref Flatpak derivada da fonte; core RetroArch declarado por
plataforma; requisitos/BIOS declarados por plataforma. Nenhum shell, nenhum
template textual concatenado.

Integre o `PlatformRomScanner`: agrupe jogos na plataforma classificada;
preserve evidência de classificação e ambiguidades; use `SwitchLibraryScanner`
somente para conteúdo Switch; updates/DLC Switch seguem não lançáveis como
base; requisitos Switch não bloqueiam outras plataformas; seleção global e por
jogo escolhe apenas emulador compatível e instalado; argv mantém a ROM como
argumento atômico; sessão/playtime registra `platformId` real.

RetroArch: core declarado por sistema; disponibilidade verificada antes de
habilitar Jogar; core ausente com remediação verdadeira, não como "pronto"; uma
instalação serve todas as plataformas declaradas.

Standalone: PS2→PCSX2, PSP→PPSSPP, Dreamcast→Flycast, DS→melonDS, 3DS→Azahar,
Wii U→Cemu, PS3→RPCS3, Xbox→xemu, Xbox 360→Xenia Canary.

Commit: `feat(emulation): launch classified games through platform profiles`

### N7 — endurecer o framework de temas  [revisão técnica dos commits não validados]

Os commits `735fd2a`, `fab6ab6`, `fe77fd2`, `2944d0c`, `292e8cb`, `46eb694`,
`df5d339`, `0e7468b`, `d536c09` e `a830b88` nunca passaram por revisão técnica.
Corrija D3 e D4.

Marketplace — **o operador já decidiu: desligado por padrão, atrás de
configuração explícita.** Não reabra essa decisão; implemente-a:

- o marketplace remoto nasce DESABILITADO. Sem opt-in explícito e persistido,
  `theme search`, `theme info` e `theme install <id-do-marketplace>` recusam com
  erro estruturado e motivo verdadeiro ("marketplace remoto não configurado"),
  nunca com stack trace, timeout longo ou falha de DNS vazando para o usuário;
- `theme install` a partir de URL direta e de caminho local continua
  funcionando com o marketplace desligado — são caminhos independentes;
- a UI não oferece ação de marketplace enquanto ele estiver desligado. Use o
  padrão `applicability/enabled/reason` já existente; nada de botão que mente;
- remova `themes.steamzero.org` como default embutido. Não substitua por outro
  host inventado: sem configuração, não há catálogo. O host passa a vir da
  configuração explícita do operador;
- `STEAMZERO_THEMES_CATALOG_URL` precisa ser validado (esquema `https`, host
  não vazio, sem credencial embutida) e o override registrado em log. Variável
  de ambiente sozinha NÃO habilita o marketplace: o opt-in é configuração
  persistida, a variável apenas escolhe o endereço quando já habilitado;
- documente o opt-in (onde mora, como ligar, o que ele passa a confiar) no
  mesmo commit. Feature de rede sem documentação de confiança não entra;
- checksum passa a ser OBRIGATÓRIO para instalação vinda de catálogo; entrada
  sem checksum é rejeitada, não instalada;
- substitua `allowed_hosts=frozenset({"*"})` por allowlist real derivada do
  catálogo/configuração;
- catálogo malformado produz `SteamZeroError` do catálogo de erros, nunca
  `KeyError`/`ValueError` cru. Teste com entrada sem `id`, com `size`
  não-numérico e com `entries` contendo lixo.

Editor:
- `set_asset()` persiste de verdade ou é removido. Não deixe caminho que
  reporta sucesso sem efeito. Se persistir, declare a ação no contrato e teste
  o ciclo completo;
- `export_zip()` e `ThemeInstaller` passam a concordar sobre o layout do
  pacote; teste de round-trip export→install que prova que os assets
  sobrevivem;
- `_validate_save()` passa a usar a validação ancorada do schema
  `theme-manifest-v1`, aplicada ANTES de qualquer `ensure_dir`/`remove_tree`;
  teste com id não-ASCII, id vazio e id com separador de caminho;
- prove que `overwrite=true` jamais aponta `remove_tree` para fora de
  `paths.themes_dir()`.

Commit: `fix(theme): harden marketplace trust and editor persistence`

### N8 — normalizar a integração de UI

Corrija D5:
- fonte única para a lista de seções, consumida pelo mapa de argumentos, pelos
  dois models de navegação e pelo harness; a asserção de contagem deriva dessa
  fonte;
- escolha um ícone e use-o: ou referencie `preferences-desktop-theme` na
  navegação de Temas, ou remova o glyph. Não deixe glyph morto nem colisão com
  "Cache gráfico";
- remova as propriedades `Layout.*` inertes dentro do `ScrollView` e resolva o
  conflito com o `width:` explícito;
- unifique o transporte do painel de temas em `requestAction`; se algum GET
  precisar permanecer, encode a query corretamente e justifique no commit;
- controle, foco e scroll continuam válidos em 949×593 e 1280×800;
- zero warning QML com `QT_FORCE_STDERR_LOGGING=1` e `QT_LOGGING_RULES=""`;
- harness QML novo que exercite o painel de temas de verdade (criar, editar
  token, preview, cancelar), não apenas instanciar.

Commit: `fix(ui): unify navigation source and theme panel integration`

### N9 — transmissão de tela: provar o que existe

Não acrescente feature. Valide e torne resiliente o que já existe em
`cast_engine.py`, `cast_orchestrator.py`, `screencast_web.py` e
`game_stream.py`:

- o host NÃO tem encoder VA no GStreamer (falta `gst-plugin-va`) e `gi` só
  existe no Python do sistema. A ausência de encoder precisa degradar com causa
  registrada, nunca travar nem exibir sessão "pronta";
- o caminho de portal (captura) fecha recursos em erro e em cancelamento;
- a ação de transmissão só fica habilitada quando o pipeline é realmente
  construível no host corrente; caso contrário, motivo verdadeiro;
- teste com fake de GStreamer simulando encoder ausente.

P2P / pareamento remoto permanece fora de escopo.

Commit: `fix(cast): degrade explicitly when host lacks encoder support`

### N10 — gate de promoção que reproduz a jornada real

Preflight read-only que FALHA se: wheel, manifest, `current`, daemon e doctor
divergirem em versão ou source commit; o daemon anterior continuar vivo;
schemas, manifests, assets ou perfis não estiverem empacotados; algum asset
obrigatório não carregar; a fixture de upgrade Switch perder keys/firmware
catalogados; plataforma standalone declarada voltar a placeholder; fonte
Flatpak ficar sem lifecycle; launch profile estiver ausente ou inválido;
entrypoints de boot direto estiverem ausentes.

O teste não baixa emulador e não toca o host. Use fakes e fixtures.

Commit: `test(release): gate runtime identity and emulation readiness`

### N11 — integração em main sem perder nada

Só depois de N1-N10 verdes. Execute a triagem decidida em N0.

Regras de integração:

- `codex/theme-framework` entra por fast-forward. Confirme com
  `git merge-base --is-ancestor main <branch>` ANTES; se deixou de ser FF,
  pare e reporte em vez de improvisar merge;
- toda branch aprovada para integrar entra com merge commit próprio, uma por
  vez, com os quatro gates verdes ENTRE cada uma. Merge em lote esconde qual
  integração quebrou o quê;
- conflito em `docs/WORKLOG.md` resolve-se SEMPRE por união append-only: as
  duas sessões sobrevivem, em ordem cronológica. Nunca sobrescreva sessão
  alheia (AGENTS.md §2);
- conflito em `Main.qml` resolve-se preservando as duas intenções. Se uma
  intenção precisar ser descartada, isso é decisão do operador e vai para o
  relatório com o motivo;
- branch de base obsoleta (o caso de `desktop-experience-input`, que faz bump
  para `0.1.0a34`) é rebaseada antes de integrar. O bump de versão da branch
  antiga é descartado, nunca mergeado — a versão de `main` é a autoritativa;
- conflito add/add (`ErrorCard.qml`, `WI-S0.md`) exige comparar os dois lados
  e justificar a escolha por escrito. "Peguei o meu" não é justificativa;
- branch aposentada é registrada no relatório com motivo e com o commit exato
  onde seu conteúdo vive, para poder ser resgatada depois. `4ecc7a6` entra aqui:
  duplicata de `735fd2a`, aposentar, não mergear;
- NADA é apagado. Não delete branch, local ou remota. Aposentar significa
  documentar, não remover.

Prova de não-perda, obrigatória no relatório: para cada branch do inventário,
mostre `git rev-list --count main..<branch>` DEPOIS da integração. Deve ser 0
para as integradas, e para as aposentadas o número deve vir acompanhado da
decisão do operador que autorizou deixá-las fora.

Commit: merges próprios, um por branch integrada.

## Critérios transversais — coesão, resiliência e robustez

Estes critérios valem para TODO item, não são um item separado. O revisor vai
cobrá-los em cada commit.

**Coesão**
- uma verdade por conceito: um composer de emulação, uma fonte de seções de UI,
  um catálogo de erros, um contrato de ação. Se você encontrar dois produtores
  do mesmo dado, unifique ou justifique por escrito por que os dois existem;
- apresentação vem de contrato versionado, nunca de dict Python paralelo ao
  manifesto;
- nomenclatura e envelope de ação iguais entre CLI, HTTP e UI. A mesma operação
  não pode ter três nomes;
- schema, código e documentação mudam no MESMO commit. Schema atualizado sem
  doc, ou doc sem teste, volta na revisão.

**Resiliência** (AGENTS.md §8: falha degrada, nunca trava)
- toda falha termina em estado utilizável com causa registrada em
  journal/status/doctor. Tela preta, loop, spinner infinito e falha silenciosa
  reprovam;
- rede, host e conteúdo externo são hostis por padrão: timeout, limite de
  tamanho, allowlist, e falha fechada quando a integridade não puder ser
  verificada;
- falha de um adapter, plataforma ou emulador degrada só o escopo dele; o
  restante da central continua navegável;
- toda mutação tem plan/apply/verify/rollback. Rollback que nunca foi executado
  em teste não conta como rollback;
- ausência de capacidade no host (encoder VA, core RetroArch, keys) é um estado
  de primeira classe com remediação verdadeira, não uma exceção.

**Robustez**
- entrada externa é validada por schema ancorado antes de virar caminho,
  argumento ou alvo de remoção. Nunca `isalnum()` no lugar do schema;
- nenhum shell, nenhum argv concatenado, ROM sempre como argumento atômico;
- erro estruturado do catálogo `E-*` em vez de exceção crua vazando;
- nenhuma ação habilitada cujo caminho termine em stub. `enabled=false` com
  motivo verdadeiro é sempre preferível a botão que mente;
- todo defeito corrigido ganha um teste que FALHA sem a correção. É o critério
  de aceite de cada item deste prompt.

## Gates após CADA item

```bash
rtk .venv/bin/pytest tests -q
rtk .venv/bin/ruff check src tools tests
rtk .venv/bin/mypy src
rtk make independence boundaries
```

Mais, a cada item: testes focados do item; `rtk .venv/bin/pytest
tests/integration/test_qml_handheld_offscreen.py -q`; `qmllint`;
`git diff --check`; cobertura sem regressão (`fail_under = 85`).

Se uma falha for preexistente, prove com o commit-base e não a esconda.

## Merge, release, instalação e push — o que você pode e não pode

Você PODE: criar e commitar na sua branch; rodar gates; escrever o relatório;
fazer push APENAS da sua própria branch.

Você NÃO PODE, sem autorização explícita do operador nesta thread: mergear na
linha principal; construir wheel, wheelhouse ou manifesto; promover, instalar
ou reverter no host; reiniciar units; tocar branch alheia; force-push.

Nunca, com ou sem autorização: `git push --force`, `git branch -D` de branch
alheia, reescrita de história já publicada, ou descarte de trabalho não
mergeado sem decisão registrada do operador. Antes de qualquer comando que
possa destruir trabalho não commitado (`checkout`, `restore`, `reset`,
`clean`, `rm -rf`), rode `git status` e faça `git stash -u` do que existir.

O push só acontece depois dos quatro gates verdes no commit final e do
relatório escrito. Push com gate vermelho é o mesmo erro que quebrou o host.

Quando a autorização vier, o protocolo físico será:

1. registrar release ativa e alvo de rollback;
2. construir wheel e wheelhouse SOMENTE de commit limpo e commitado;
3. conferir hash, entrypoints de boot direto e source commit;
4. promover com `bigsudo /usr/bin/python3 tools/install_host.py install ...`;
5. confirmar que o PID do daemon usa a NOVA release — este é o teste que a a37
   não tinha e o que N1 torna possível;
6. comparar manifest, daemon e doctor;
7. abrir uma UI nova, não uma janela preexistente;
8. validar Switch: ícones, keys, firmware, jogos e launch;
9. validar um sistema via RetroArch;
10. validar cada standalone sem baixar conteúdo protegido;
11. validar rollback e a coerência do daemon após o rollback;
12. registrar o que ainda depende de hardware ou conteúdo do operador.

Reinicialização física continua sendo ação do operador.

## Relatório final obrigatório

| Item | Commit | Teste que prova (comando) | 4 gates |
|---|---|---|---|

Inclua:

- para cada defeito D1-D7: corrigido / mitigado / fora de escopo, com o porquê;
- comparativo antes/depois de identidade release × daemon × doctor;
- plataformas REALMENTE operacionais, separadas das apenas declaradas;
- matriz emulador → fonte → status/install/launch efetivamente testados;
- evidência `Image.Ready`;
- prova de preservação de keys/firmware/state;
- round-trip export→install de tema;
- arquivos compartilhados reconciliados e como;
- riscos e validações físicas pendentes;
- ações de host executadas (esperado: NENHUMA);
- confirmação de que P2P não foi tocado;
- branch publicada, sem force-push.

Tabela obrigatória de não-perda no merge, uma linha por branch de D8:

| Branch | Decisão | `rev-list --count main..branch` depois | Onde o conteúdo vive | Quem autorizou |
|---|---|---|---|---|

E a confirmação explícita de que o marketplace remoto nasce desligado, com o
comando que prova o comportamento quando não há configuração.

Não declare gate verde sem colar a saída. Relatórios anteriores neste
repositório já afirmaram "ruff verde" estando vermelho, e o revisor vai
reexecutar tudo.
```
</content>
</invoke>
