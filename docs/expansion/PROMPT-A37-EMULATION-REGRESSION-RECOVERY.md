# Prompt — recuperação P0 da emulação após a release a37

Copie o bloco abaixo para uma nova tarefa Codex.

```text
# Tarefa P0 — corrigir regressões de emulação e promoção da release a37

Você está corrigindo uma regressão observada fisicamente após a promoção da release
SteamZero `0.1.0a37`, source commit
`2aaa01d9d8b638b3d8e8c396ffbeed133da50ec2`.

Esta não é uma tarefa de acrescentar botões nem de reimportar dados do usuário. Primeiro
restaure a coerência da release em execução e prove a causa. Depois torne a expansão de
emuladores operacional de ponta a ponta.

## Sintomas informados pelo operador

- a integração Switch perdeu ícones na UI;
- keys e firmware antes válidos deixaram de aparecer;
- os demais emuladores/sistemas mergeados aparecem, mas não estão ligados nem funcionais.

## Evidências já confirmadas — não repita conclusões vagas

### E1 — release no disco e daemon em execução pertencem a gerações diferentes

Leituras feitas em 2026-07-26/27, sem mutar o host:

- `/opt/steamzero/current` aponta para
  `releases/0.1.0a37-2aaa01d9d8b6`;
- o `manifest.json` declara `packageVersion=0.1.0a37` e o source commit completo acima;
- `/usr/local/bin/steamzero --version` responde `0.1.0a37`;
- porém `steamzero-core.service` continua com o processo:
  `/opt/steamzero/releases/0.1.0a35-7a1916e1e711/venv/bin/python3`;
- por isso `steamzero doctor --json` respondia `version=0.1.0a35`;
- `tools/install_host.py::_activate()` troca units/links/current, mas não reinicia nem
  verifica a geração do daemon persistente.

Consequência: CLI/IPC podem carregar código a37 e receber snapshots do daemon a35.
Não aceite uma promoção que deixe versões misturadas.

### E2 — os dados Switch não foram apagados

Executando diretamente o `DesktopDashboard` do pacote a37, sem o daemon antigo:

- `truthState=ready`;
- keys: `status=ok`, `installed=rev21`;
- firmware: `status=ok`, `installed=22.5.0`;
- 15 jogos;
- Eden, Citron e Ryubing detectados como instalados;
- os três publicam `iconAsset`;
- fallback Switch é `../assets/switch.svg`.

Logo, não mande o usuário reimportar keys/firmware e não altere conteúdo protegido.
Primeiro corrija geração/processo/projeção. Preserve integralmente state.db, keys,
firmware, ROMs, mídia e configuração existentes.

### E3 — os assets estão no wheel, mas a prova visual é incompleta

O wheel a37 instalado contém os 28 assets em `steamzero/ui/assets`, inclusive:

- `switch.svg`;
- `eden.svg`;
- `citron.svg`;
- `ryubing.png`;
- assets de PS2, PSP, Dreamcast, DS, 3DS, Wii U, PS3, Xbox e Xbox 360.

Os testes atuais verificam apenas strings como `../assets/eden.svg` e
`fallbackArtworkAsset`. Eles não esperam `Image.status === Image.Ready` no QML instalado.
Portanto “arquivo empacotado” ainda não prova “imagem renderizada”.

### E4 — manifests foram confundidos com integração funcional

`build_switch_workspace()` compõe Switch operacionalmente e acrescenta todas as outras
plataformas por `platform_placeholder(manifest)`.

No snapshot a37:

- existem 36 plataformas;
- todas as plataformas emuladas fora de Switch estão `state=planned`;
- seus emuladores estão `installState=unverified`, `installable=false`;
- não há `iconAsset` nem ação operacional nessas linhas.

Além disso:

- `_MANAGED_EMULATORS` contém somente `eden`, `citron`, `ryubing`;
- `_EMULATOR_PRESENTATION` contém somente esses três;
- `_launch_argv()` só aceita esses três e usa regras Switch;
- `launch_game()` usa `SwitchLibraryScanner` e exige keys Switch para qualquer jogo;
- `AdapterEngine.plan_install()` rejeita fonte `flatpak`;
- PS2, PSP, Dreamcast, DS, 3DS, Wii U, PS3 e Xbox usam fontes Flatpak;
- Xbox 360 usa AppImage, mas continua bloqueado pela allowlist Switch;
- RetroArch tem `platforms:["multi"]`, mas não há composição de core por plataforma;
- os manifests atuais não possuem contrato suficiente de argv/core para iniciar ROMs.

Assim, não resolva isto apenas mudando `enabled=true`. A ação só pode ser habilitada
quando status, instalação, verificação e launch reais existirem.

## Governança e preflight

1. Leia integralmente:
   - `AGENTS.md`;
   - `/home/misael/.codex/RTK.md`;
   - ADR-0019 e os contratos de adapter, plataforma, transação, segurança e UI;
   - `docs/05-data/PLATFORM-MANIFEST-V1.md`;
   - `docs/03-architecture/ADAPTER-MODEL.md`;
   - `docs/07-ui-ux/DESKTOP-MODE-UI.md`;
   - `docs/08-testing/TEST-STRATEGY.md`;
   - este prompt.
2. Consulte a memória do projeto antes de propor arquitetura.
3. Crie uma branch própria `codex/a37-emulation-recovery` a partir do tip de `main`
   aprovado pelo operador.
4. Confirme todos os preflights de base atualizada do `AGENTS.md`.
5. Use um worktree próprio. Outra sessão está alterando esta árvore.
6. Todo comando shell começa com `rtk`; edições usam `apply_patch`.
7. Preserve alterações e untracked de outras frentes.
8. Antes de editar arquivo compartilhado, confirme que ele não mudou desde o preflight.

## Proibições

- Não use `sudo` ou `bigsudo`.
- Não instale, reinicie, pare ou reverta nada no host sem autorização explícita do
  operador na sua própria tarefa.
- Não construa wheel/release antes de autorização explícita.
- Não abra, copie, imprima ou regrave conteúdo de keys/firmware/ROMs.
- Não remova state.db nem “resolva” o problema limpando cache/configuração.
- Não habilite ação que ainda termina em stub, placeholder ou erro previsível.
- Não introduza shell, argv concatenado ou path não validado.
- Não reintroduza referências proibidas pelo ADR-0019.
- Não force-push.

## Ordem obrigatória de implementação

### R0 — reproduções e testes de regressão

Antes de corrigir, escreva testes que falhem no estado atual:

1. promoção a35 → a37 com daemon a35 vivo não pode terminar verde;
2. cliente a37 não pode aceitar silenciosamente daemon de outra geração;
3. snapshot anterior com keys/firmware válidos deve continuar válido após upgrade;
4. assets do wheel devem chegar a `Image.Ready`, não apenas ter path correto;
5. plataforma com adapter declarado não pode ser publicada como operacional se ainda for
   `platform_placeholder`;
6. fonte Flatpak deve usar o executor correto, não `AdapterEngine`;
7. launch não-Switch não pode passar por `SwitchLibraryScanner` nem exigir prod.keys.

Use fixtures sintéticas. Nunca use dados reais do operador em testes.

Commit: `test(regression): reproduce a37 emulation and runtime split`

### R1 — coerência transacional da release e do daemon

Implemente um protocolo seguro de ativação:

- a identidade do runtime deve expor ao menos package version, release ID e source commit;
- cliente e daemon fazem handshake e detectam geração divergente;
- leitura pode falhar de forma estruturada ou usar fallback local comprovadamente
  read-only; mutação nunca é repetida nem enviada ao daemon errado;
- ativação atualiza o user manager, reinicia apenas os units SteamZero gerenciados e
  aguarda a identidade da nova geração;
- socket activation não pode ressuscitar a release anterior;
- falha de reload/restart/handshake restaura `current`, units e daemon anterior, ou
  encerra com estado recuperável claramente documentado;
- rollback também valida a identidade final;
- nenhuma unit de terceiro é tocada;
- o instalador não depende de variáveis de sessão frágeis sem validação.

Escolha a forma correta de falar com o user manager no fluxo autorizado do instalador.
Não mate PID diretamente como solução principal. Respeite ownership e marcadores.

Acrescente um teste de upgrade com processo fake/manager fake e um smoke read-only que
compare:

`manifest.sourceCommit == daemon.sourceCommit == doctor.sourceCommit`.

Commit: `fix(release): prevent mixed daemon generation after activation`

### R2 — resolução real dos assets QML

Reproduza com o QML carregado a partir do pacote instalado/unpacked, não apenas da árvore
fonte.

Implemente resolução explícita e allowlisted dos assets empacotados. Pode ser
`Qt.resolvedUrl()` a partir do componente correto ou outra solução de recursos Qt, desde
que:

- funcione em source tree e wheel instalado;
- aceite somente assets empacotados declarados;
- preserve fallback por plataforma/emulador;
- não aceite URL/path arbitrário vindo de dados externos;
- mostre fallback iconográfico somente em erro real.

Teste `Image.Ready` para:

- Switch;
- Eden, Citron e Ryubing;
- cada asset distinto das plataformas standalone;
- RetroArch compartilhado;
- fallback de mídia de jogo.

Commit: `fix(qml): resolve packaged emulation artwork at runtime`

### R3 — preservação Switch ponta a ponta

Crie fixture de upgrade contendo apenas metadados sintéticos equivalentes a:

- key catalogada e projeções válidas;
- firmware catalogado;
- três emuladores instalados;
- biblioteca escaneada e mídia fallback/custom.

Prove, depois da migração/upgrade:

- daemon e dashboard publicam os mesmos requisitos;
- UI mostra keys/firmware como presentes;
- os três emuladores preservam estado, ícone, ação e padrão;
- nenhuma importação é solicitada quando os arquivos/projeções permanecem válidos;
- ausência real de projeção oferece reparo, sem apagar a origem;
- nenhum refresh substitui `ok` por `unverified` por usar builder simplificado.

Elimine ou adapte `emulation workspace` para usar o mesmo composer operacional do
Dashboard. Não mantenha dois snapshots com verdades diferentes.

Commit: `fix(emulation): preserve switch truth across release generations`

### R4 — composer operacional orientado a manifests

Substitua a composição exclusiva de Switch por um `EmulationWorkspace`/composer genérico.
Preserve compatibilidade de contrato quando possível.

Requisitos:

- `PlatformRegistry` define plataformas e precedência;
- `AdapterRegistry` define lifecycle e fontes;
- status real vem do executor correspondente;
- apresentação/ícone vêm de contrato versionado, não de dict Python hardcoded;
- `_MANAGED_EMULATORS` e `_EMULATOR_PRESENTATION` deixam de ser allowlists manuais;
- `platform_placeholder` permanece apenas para capability explicitamente planejada,
  nunca para esconder adapter já declarado;
- um adapter compartilhado, como RetroArch, pode aparecer em várias plataformas sem
  duplicar instalação física;
- falha de um adapter degrada somente suas plataformas;
- o read model informa `installed`, `installable`, `running`, versão, origem,
  health, ações e motivo verdadeiro.

Atualize schema e documentação no mesmo commit. Crie migração de contrato apenas se
necessária; não faça migração de banco por conveniência.

Commit: `refactor(emulation): compose operational platforms from registries`

### R5 — lifecycle unificado para AppImage e Flatpak

Crie uma porta/fachada comum para lifecycle, mantendo executores especializados:

- AppImage/portátil continua no engine transacional com digest;
- Flatpak usa `FlatpakExecutor`, remote/ref/commit pinados;
- status detecta instalação real no escopo `--user`;
- plan/apply/verify/rollback continuam obrigatórios;
- install/update/uninstall nunca executam diretamente pela UI;
- `component-lock` e manifesto precisam concordar;
- source EOL/incompatível falha fechado;
- abrir apenas emulador instalado é permitido;
- stop só atua sobre processo comprovadamente iniciado/gerenciado pelo SteamZero.

Cubra no mínimo:

- RetroArch, DuckStation e Dolphin;
- PCSX2, PPSSPP, Flycast, melonDS, Azahar, Cemu, RPCS3 e xemu;
- Xenia Canary;
- Eden, Citron e Ryubing sem regressão.

Commit: `feat(emulation): route emulator lifecycle by pinned source type`

### R6 — launch declarativo e biblioteca por plataforma

O contrato atual não contém informação suficiente para launch genérico. Estenda o
manifesto com um contrato fechado e seguro, por exemplo:

- modo de execução derivado da source, nunca comando livre do usuário;
- `openArgs` e `gameArgs` como arrays;
- placeholders allowlisted (`{rom}`, e somente os estritamente necessários);
- ref Flatpak derivada da source;
- core RetroArch declarado por plataforma;
- requisitos/BIOS declarados por plataforma/emulador;
- nenhum shell e nenhum template textual concatenado.

O desenho final pode variar, mas precisa ser versionado, validado por schema e documentado.

Integre o `PlatformRomScanner`:

- agrupe jogos na plataforma classificada;
- preserve evidência de classificação e ambiguidades;
- use `SwitchLibraryScanner` somente para conteúdo Switch;
- updates/DLC Switch continuam não lançáveis como base;
- requisitos Switch não bloqueiam outras plataformas;
- seleção global e por jogo escolhe apenas emulator compatível/instalado;
- argv mantém ROM como argumento atômico;
- sessão/playtime registra `platformId` real.

RetroArch:

- declare core por sistema;
- verifique disponibilidade do core antes de habilitar Jogar;
- core ausente aparece com ação/remediação verdadeira, não como “pronto”;
- uma instalação RetroArch serve a todas as plataformas declaradas.

Standalone:

- PS2 → PCSX2;
- PSP → PPSSPP;
- Dreamcast → Flycast;
- DS → melonDS;
- 3DS → Azahar;
- Wii U → Cemu;
- PS3 → RPCS3;
- Xbox → xemu;
- Xbox 360 → Xenia Canary.

Commit: `feat(emulation): launch classified games through platform profiles`

### R7 — integração UI sem ações falsas

Atualize a UI para consumir exclusivamente o composer operacional:

- plataforma mostra artwork real;
- emulator mostra icon real;
- status/ações refletem executor e requisitos;
- instalar/atualizar/abrir/parar usam action IDs do backend;
- biblioteca muda com a plataforma selecionada;
- keys/firmware Switch permanecem na área Switch;
- BIOS/requisitos de outros sistemas aparecem somente onde declarados;
- controle/foco/scroll continuam válidos em 949×593 e 1280×800;
- zero warning QML com `QT_FORCE_STDERR_LOGGING=1` e `QT_LOGGING_RULES=""`.

Não remova o padrão de `applicability/enabled/reason`; corrija o backend para que as ações
reais se tornem aplicáveis.

Commit: `fix(ui): expose operational emulation platforms without regressions`

### R8 — gate de promoção que reproduz a jornada real

Adicione um preflight de release read-only que falhe se:

- wheel, manifest, `current`, daemon e doctor divergem em versão/source commit;
- daemon anterior continua vivo;
- schema/manifests/assets/perfis não foram empacotados;
- qualquer asset obrigatório não carrega;
- Switch perde keys/firmware catalogados em fixture de upgrade;
- plataforma standalone declarada volta a placeholder;
- fonte Flatpak não tem lifecycle;
- launch profile está ausente/inválido;
- entrypoints de boot direto estão ausentes.

O teste não baixa emuladores e não toca o host. Use fakes/fixtures para lifecycle. A
validação física no host só ocorre depois, com autorização do operador.

Commit: `test(release): gate runtime identity and emulation readiness`

## Gates após CADA item

```bash
rtk .venv/bin/pytest tests -q
rtk .venv/bin/ruff check src tools tests
rtk .venv/bin/mypy src
rtk make independence boundaries
```

Também execute:

- testes focados do item;
- `qmllint`;
- harnesses QML offscreen com stderr Qt reabilitado;
- `git diff --check`;
- verificação de cobertura sem regressão.

Se uma falha for preexistente, prove com o commit-base e não a esconda.

## Validação física futura — não autorizada por este prompt

Depois de todos os commits, retorne ao operador. Não faça build, promoção ou restart por
conta própria.

Quando houver autorização explícita, o protocolo físico deverá:

1. registrar release atual e rollback;
2. construir wheel/wheelhouse somente de commit limpo;
3. verificar hash, entrypoints e source commit;
4. promover com o instalador autorizado;
5. confirmar que o PID do daemon usa a nova release;
6. comparar manifest/daemon/doctor;
7. abrir a UI nova, não uma janela preexistente;
8. validar Switch: ícones, keys, firmware, jogos e launch;
9. validar um sistema RetroArch;
10. validar cada standalone sem baixar conteúdo protegido;
11. validar rollback e coerência do daemon após rollback;
12. registrar explicitamente o que ainda depende de hardware/conteúdo do operador.

## Relatório final obrigatório

Entregue:

| Item | Commit | Teste que prova | Quatro gates |
|---|---|---|---|

Inclua:

- causa raiz confirmada de cada sintoma;
- comparativo direto x daemon antes/depois;
- plataformas realmente operacionais, não apenas declaradas;
- matriz emulator → source → status/install/launch testados;
- evidência `Image.Ready`;
- preservação de keys/firmware/state;
- arquivos compartilhados reconciliados;
- riscos e validações físicas pendentes;
- ações de host executadas (esperado nesta tarefa: nenhuma);
- branch publicada, sem force-push.
```
