# WI-S1 — Plano de captura real via xdg-desktop-portal

Status: pronto para implementação por outro agente  
Base funcional validada: `a7506c1ca213ceba64ee53e0a49671a081885c03`  
Linha de origem: `codex/screencast-web-pipeline-signaling`  
Ponto de partida: tip desta linha que contém este plano  
Revisão: deve ser feita em sessão separada da implementação, antes de merge  
Instalação no host: fora de escopo

## 1. Objetivo

Completar o caminho de captura real do `web-receiver` em Wayland:

1. o motor pede uma sessão `org.freedesktop.portal.ScreenCast`;
2. o usuário escolhe e autoriza uma fonte;
3. o motor recebe o remote PipeWire e o stream autorizado;
4. `pipewiresrc` consome exclusivamente esse remote/stream;
5. o navegador recebe quadros reais pelo pipeline WebRTC existente;
6. cancelamento, revogação, erro ou `STOP_SESSION` liberam todos os recursos.

Este WI não instala dependências, não constrói release, não ativa nada no host e
não altera o fluxo `game-stream`.

## 2. Decisão arquitetural obrigatória

### 2.1 `CaptureConsent` não transporta recursos do portal

`CaptureConsent` continua sendo um valor puro do contrato público. Ele representa
a intenção explícita do usuário, o escopo pedido e se áudio foi solicitado. Não
recebe:

- file descriptor;
- node ID ou serial do PipeWire;
- session/request handle;
- restore token;
- objeto `Gio`, `GLib`, D-Bus ou GStreamer.

O comentário/docstring deve deixar de sugerir que `granted=True` prova que o portal
já concluiu. A autorização efetiva só existe após o `Response` bem-sucedido de
`ScreenCast.Start`.

### 2.2 O `cast_engine` é dono da sessão do portal

O processo `cast_engine.py` abre o portal e mantém localmente:

- handle da sessão;
- handle do request interativo ainda pendente;
- descritor duplicado retornado por `Gio.UnixFDList.get()`;
- node ID legado;
- `pipewire-serial`, quando presente;
- subscriptions D-Bus;
- pipeline GStreamer.

O `fd` nunca cruza o IPC JSON. Um inteiro de descritor só tem significado no
processo que o possui. Como o motor abre o portal, não há motivo para adicionar
`SCM_RIGHTS`.

Se no futuro o portal for aberto em outro processo, a mudança exige ADR próprio e
passagem por `SCM_RIGHTS`; serializar o número do `fd` continua proibido.

### 2.3 Recursos do portal são privados

Nenhum evento IPC, status público, SSE ou log pode publicar:

- número do `fd`;
- request/session handle;
- token do portal;
- título de janela;
- nome textual da fonte escolhida;
- restore token.

Eventos podem informar apenas fase, capacidade observada e causa estável.

## 3. Estado atual que o implementador deve preservar

No commit-base:

- o provider envia `START_SESSION` por uma conexão IPC persistente;
- offer, answer, candidatos ICE e `STOP` usam a mesma conexão;
- o pipeline de vídeo é send-only:
  `pipewiresrc -> videoconvert -> x264enc -> h264parse -> rtph264pay -> webrtcbin`;
- áudio Opus só é criado quando existe node de áudio validado;
- `SessionState` já reserva `portal_session` e `portal_fd`;
- `build_pipeline_description()` já valida escalares de fd/node;
- os quatro gates do repositório estão verdes.

Não reescrever sinalização, receptor HTML ou seleção de codec neste WI.

## 4. Fluxo do portal

Implementar cliente privado, por exemplo `PortalScreenCastClient`, dentro de
`cast_engine.py` ou em módulo irmão que continue respeitando a fronteira do motor:
somente stdlib + `gi`, sem importar `steamzero`.

Sequência:

1. obter o session bus;
2. consultar `ScreenCast.version`, `AvailableSourceTypes` e
   `AvailableCursorModes`;
3. gerar tokens únicos e não adivinháveis para request e session handles;
4. assinar `Request.Response` no caminho previsto **antes** de disparar cada
   método, evitando a corrida documentada pelo portal;
5. `CreateSession`;
6. `SelectSources`;
7. `Start`;
8. validar o array `streams`;
9. `OpenPipeWireRemote`;
10. extrair o descritor real de `Gio.UnixFDList`;
11. construir/iniciar o pipeline;
12. assinar `Session.Closed`.

Mapeamento de `CaptureConsent.scope`:

| Scope | Bit ScreenCast | Regra |
|---|---:|---|
| `monitor` | 1 | exigir `MONITOR` disponível |
| `window` | 2 | exigir `WINDOW` disponível |
| `virtual` | 4 | exigir `VIRTUAL` disponível; nunca degradar para monitor |

Usar `multiple=false`. Escolher somente cursor mode anunciado pelo backend; a
preferência inicial é `METADATA`, depois `EMBEDDED`, depois `HIDDEN`. Não enviar
valor que não esteja em `AvailableCursorModes`.

O `parent_window` pode começar vazio neste WI, desde que isso seja coberto por
teste e documentado como diálogo não parentado. Não inventar identificador
Wayland a partir de PID, título ou winId. Parentamento real exige contrato próprio
com a UI.

Referências normativas:

- <https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html>
- <https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Request.html>
- <https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Session.html>
- <https://docs.gtk.org/gio/class.UnixFDList.html>

## 5. Assincronia e máquina de estados

O diálogo do portal pode ficar aberto por tempo humano. Nenhuma chamada portal
deve:

- bloquear o handler IPC;
- aguardar sob `CastEngine._lock`;
- bloquear a thread da UI;
- usar timeout D-Bus síncrono como substituto de `Request.Response`.

Executar D-Bus/GStreamer em um `GLib.MainLoop` dedicado ou coordenador assíncrono
equivalente. O handler de `START_SESSION` apenas valida, registra a conexão de
controle, muda o estado e agenda o fluxo.

Estados mínimos:

```text
IDLE
  -> PORTAL_REQUESTING
  -> SOURCE_SELECTING
  -> CAPTURE_READY
  -> NEGOTIATING
  -> STREAMING
  -> STOPPING
  -> IDLE

qualquer estado ativo -> FAILED
qualquer request pendente -> CANCELLED -> IDLE
```

Eventos IPC mínimos:

| Evento | Significado |
|---|---|
| `START_SESSION_ACCEPTED` | pedido validado e portal agendado |
| `CAPTURE_READY` | remote fd e stream validados, sem dados sensíveis |
| `SESSION_STREAMING` | pipeline em `PLAYING` e negociação iniciada |
| `CAPTURE_DENIED` | usuário recusou |
| `CAPTURE_CANCELLED` | usuário ou `STOP_SESSION` cancelou |
| `CAPTURE_REVOKED` | `Session.Closed` durante sessão |
| `SESSION_FAILED` | falha técnica com causa estável |

Compatibilidade: se o nome atual `START_SESSION_OK` for preservado, sua semântica
deve ser explicitamente “aceito”, não “já transmitindo”. Não emitir
`OFFER_CREATED` antes de `CAPTURE_READY`.

Comandos continuam idempotentes:

- `START_SESSION` em fase pendente/ativa devolve o estado existente;
- `STOP_SESSION` fecha request pendente ou sessão ativa;
- segundo `STOP_SESSION` responde com sucesso;
- callbacks tardios de uma geração anterior são ignorados.

Usar generation/session token interno para impedir que callback tardio ressuscite
uma sessão encerrada.

## 6. Integração com o domínio e provider

Hoje `CastOrchestrator.start_stream()` move a sessão de `NEGOTIATING` para
`STREAMING` imediatamente após `provider.start()`. Isso é falso enquanto o portal
está pendente.

Corrigir de forma aditiva:

1. `provider.start()` cria o id opaco e agenda `START_SESSION`;
2. o domínio permanece em `NEGOTIATING`;
3. evento observado do provider/motor promove para `STREAMING`;
4. negação/cancelamento volta para `IDLE` com causa;
5. falha/revogação passa pelo plano de recuperação existente quando aplicável.

O implementador deve escolher o menor contrato aditivo capaz de expor a fase
observada ao orquestrador. Não usar `LinkSample` como canal improvisado de estado
e não fazer `isinstance(WebReceiverProvider)` dentro do domínio.

Antes de editar `ScreenCastProviderPort`, verificar todos os providers e doubles
de teste. Se a extensão obrigar mudança ampla fora de screencast, parar e relatar
ao revisor antes de continuar.

## 7. Ligação com PipeWire/GStreamer

Ao processar `Start.results["streams"]`, guardar:

- node ID como fallback legado;
- propriedade `pipewire-serial`, quando existir.

Para portal ScreenCast v6:

- preferir `pipewiresrc target-object=<pipewire-serial>`;
- usar `path=<node-id>` apenas quando o serial não estiver presente;
- manter o `fd` do remote do portal em `pipewiresrc fd=<fd>`.

O `path` aparece deprecated no plugin instalado e node IDs podem ser reutilizados.
Não remover o fallback legado neste WI.

O descritor obtido por `Gio.UnixFDList.get()` pertence ao motor e permanece aberto
durante toda a vida do pipeline. Ordem única de teardown:

1. impedir novos callbacks/eventos da geração;
2. pipeline para `Gst.State.NULL`;
3. remover subscriptions/watchers;
4. fechar o descritor com `os.close()`;
5. fechar a sessão do portal;
6. limpar `SessionState`;
7. publicar estado terminal.

Cada passo deve tolerar recurso ausente ou já fechado.

## 8. Áudio

Áudio não bloqueia a entrega de vídeo real.

Regras:

- não capturar microfone;
- não usar source/monitor padrão como fallback;
- não anunciar áudio sem node explicitamente autorizado/observado;
- se o backend ScreenCast não entregar áudio utilizável, iniciar vídeo-only e
  refletir capacidade reduzida honestamente.

Uma solução de áudio que exija portal ou política diferente deve virar WI
separado.

## 9. Causas estáveis

O adapter deve distinguir pelo menos:

| Causa | Condição |
|---|---|
| `portal-missing` | serviço/interface indisponível |
| `source-type-unavailable` | scope pedido não anunciado |
| `capture-denied` | `Response` indica recusa |
| `capture-cancelled` | usuário fecha diálogo ou STOP cancela request |
| `portal-invalid-response` | resposta sem session/streams válidos |
| `portal-timeout` | timeout interno explícito, se adotado |
| `pipewire-remote-failed` | falha em `OpenPipeWireRemote`/FD list |
| `capture-revoked` | sessão fechada pelo compositor |
| `pipeline-start-failed` | GStreamer não chega a iniciar |

Não incluir exceção D-Bus crua em resposta pública. Detalhe técnico pode ir ao log
local desde que não contenha handles/tokens/fonte.

## 10. Plano de commits e escopo de arquivos

O implementador cria branch própria com prefixo `codex/` a partir do tip de
`codex/screencast-web-pipeline-signaling` que contém este plano. Deve confirmar
também que `a7506c1ca213ceba64ee53e0a49671a081885c03` é ancestral da branch. Não
trabalha diretamente na linha de origem.

| Item | Commit sugerido | Arquivos esperados |
|---|---|---|
| P1 | `refactor(cast): separate consent intent from portal grant` | `ports.py`, testes de contrato, ADR/WI se necessário |
| P2 | `feat(cast): add asynchronous screencast portal client` | `cast_engine.py`, testes do motor |
| P3 | `feat(cast): bind portal remote to capture pipeline` | `cast_engine.py`, testes do pipeline |
| P4 | `fix(cast): reconcile portal lifecycle with session state` | provider/orchestrator e testes |
| P5 | `test(cast): cover portal denial revocation and fd ownership` | testes unitários/integrados |
| P6 | `docs: record real Wayland capture evidence` | este WI/ADR/WORKLOG apenas por append |

`cast_engine.py` é arquivo compartilhado entre P2/P3/P4. Se provider/orchestrator
também forem compartilhados por outra frente, deixar a edição correspondente em
commit isolado e por último, conforme `AGENTS.md`.

Após **cada** item:

```bash
.venv/bin/pytest tests -q
.venv/bin/ruff check src tools tests
.venv/bin/mypy src
make independence boundaries
```

Não alterar teste existente apenas para acomodar uma regressão. Não construir
wheel/wheelhouse.

## 11. Testes obrigatórios

### 11.1 Sem portal real

Injetar/falsificar a fronteira D-Bus; a suíte normal não abre diálogo:

- parsing de `Response` 0, 1 e 2;
- corrida evitada por subscription anterior à chamada;
- handle devolvido diferente do previsto atualiza a subscription;
- `CreateSession`, `SelectSources`, `Start` e `OpenPipeWireRemote` falhando
  individualmente;
- bitmask para monitor/window/virtual;
- virtual indisponível não degrada para monitor;
- cursor mode escolhido somente entre anunciados;
- resposta sem stream;
- stream com serial;
- stream legado apenas com node;
- índice de `UnixFDList` inválido;
- `os.pipe()` ou socketpair comprovando ownership/fechamento;
- `STOP_SESSION` durante diálogo;
- `STOP_SESSION` durante pipeline;
- STOP duplo;
- START duplicado;
- callback tardio depois do STOP;
- `Session.Closed` durante captura;
- SIGTERM durante request e durante streaming;
- IPC responde `GET_STATUS` enquanto diálogo está pendente;
- offer não é criado antes de `CAPTURE_READY`;
- status público e logs não vazam recursos.

### 11.2 Integração GStreamer

- pipeline recebe exatamente o fd duplicado;
- serial usa `target-object`;
- ausência de serial usa fallback `path`;
- fd permanece aberto até pipeline `NULL`;
- erro de bus dispara teardown único;
- vídeo-only continua válido quando áudio não está autorizado.

### 11.3 Prova manual do operador

Não automatizar clique de consentimento e não instalar no host.

Evidência esperada:

1. iniciar receptor web;
2. selecionar monitor no diálogo KDE;
3. confirmar quadros reais no `<video>`;
4. repetir com janela;
5. cancelar o diálogo e confirmar retorno utilizável;
6. encerrar pelo indicador do compositor e confirmar `CAPTURE_REVOKED`;
7. parar pelo SteamZero e confirmar ausência de sessão/remote residual.

Registrar comandos read-only, versão do portal/backend e resultado; não registrar
título da janela selecionada.

## 12. Critérios de aceite

- [ ] `CaptureConsent` permanece puro e sem recursos do portal.
- [ ] Nenhum fd é serializado no IPC.
- [ ] O motor abre e possui a sessão ScreenCast.
- [ ] Monitor e janela geram quadros reais em Wayland.
- [ ] Virtual falha honestamente quando indisponível.
- [ ] `pipewire-serial` é preferido quando presente.
- [ ] O orquestrador não declara `STREAMING` antes da captura real.
- [ ] IPC permanece responsivo durante o diálogo.
- [ ] Denial/cancel/revocation nunca deixam pipeline ou fd vivos.
- [ ] STOP e teardown são idempotentes.
- [ ] Nenhum segredo/recurso do portal aparece em log/status/SSE.
- [ ] Todos os gates passam após cada item e no tip final.
- [ ] Nenhuma ação de host ou artefato de release foi executado.

## 13. Protocolo de entrega ao revisor

O agente implementador não faz merge. Ao terminar, entrega:

1. nome da branch e commit-base;
2. tabela item -> commit -> testes que provam;
3. `git diff --stat` e lista de arquivos tocados;
4. saída resumida dos quatro gates no tip final;
5. testes novos por cenário;
6. limitações e itens fora de escopo;
7. ações de host executadas — esperado: nenhuma;
8. passos manuais ainda devidos pelo operador.

O revisor deve inspecionar o diff e reexecutar testes, sem confiar apenas no
relatório. Pontos de revisão prioritários:

- ownership e fechamento do fd;
- nenhuma espera sob `CastEngine._lock`;
- nenhuma transição prematura para `STREAMING`;
- cancelamento de request pendente;
- `Session.Closed` e callbacks tardios;
- idempotência de STOP/teardown;
- ausência de fallback de captura não autorizado;
- ausência de vazamento em IPC/log/status;
- compatibilidade com portal anterior à versão 6;
- manutenção das fronteiras de independência.

Qualquer divergência das decisões obrigatórias das seções 2, 5 ou 7 deve ser
explicada antes da revisão; não deve ser escondida como detalhe de implementação.
