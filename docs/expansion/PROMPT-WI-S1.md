# Prompt de implementação — WI-S1: via `web-receiver` (navegador) de ponta a ponta

Este documento é o briefing completo para o agente implementador do WI-S1. Ele é
autossuficiente: leia-o inteiro antes de escrever código. Um agente supervisor valida
o resultado e é ele — não você — que executa qualquer ação no host.

Leitura obrigatória antes de começar, nesta ordem:

1. `AGENTS.md` (governança; cada regra existe por causa de um incidente real)
2. `docs/adr/0022-compartilhamento-de-tela-multi-provedor.md` (a decisão que você
   implementa)
3. `docs/expansion/WI-S0.md` (a fundação já entregue e testada)
4. `src/steamzero/domain/screencast.py` e a seção "Compartilhamento de tela" de
   `src/steamzero/ports.py` (o contrato que você consome)
5. `docs/03-architecture/MODULE-BOUNDARIES.md` (fronteiras verificadas em CI)

## 1. Objetivo

Fazer a função "Transmitir para a TV" funcionar de ponta a ponta com **um receptor
de navegador**, sem TV e sem exposição de rede, para que a experiência inteira
(consentimento → captura → encoder → transporte → decodificação → degradação →
reconexão) fique verificável no aparelho de desenvolvimento.

O operador determinou que **todas** as famílias de receptor serão suportadas —
Android TV/Google TV, Tizen/webOS, outro PC e navegador — e que a implementação
**começa pelo navegador**, por ser o único alvo que dispensa hardware de terceiros
para o teste inicial. As demais famílias chegam na via `game-stream` (host de baixa
latência + clientes já publicados), em WI posterior. Você **não** implementa
`game-stream` aqui.

Não invente escopo. Se algo parecer necessário e não estiver na seção 4, registre no
relatório final em vez de implementar.

## 2. Fatos medidos do host alvo (não re-derive, não presuma)

Medidos com sondagem read-only no Steam Deck com BigLinux/KDE em Wayland:

| Fato | Valor | Consequência para você |
|---|---|---|
| Portal | `kde.portal` expõe `ScreenCast` **e** `RemoteDesktop` | captura autorizada por portal é viável |
| PipeWire | 1.6.7, `gst-plugin-pipewire` instalado (`pipewiresrc` OK) | fonte de vídeo e de áudio |
| GStreamer | 1.28.4; `webrtcbin`, `x264enc`, `opusenc`, `rtpvp8pay` OK | plano de mídia delegado ao GStreamer |
| `webrtcsink` | **ausente** (`gst-plugins-rs` não instalado) | sinalização é sua, sobre `webrtcbin` cru |
| Encoder VA no GStreamer | **ausente** — falta o pacote `gst-plugin-va` | **o caminho de software (`x264enc`) é o padrão hoje** |
| VA-API do sistema | H.264 e HEVC com `VAEntrypointEncSlice` | o hardware sabe codificar; só falta o plugin |
| PyGObject (`gi`) | 3.56.3 no **python do sistema**; ausente no `.venv` | o motor roda em processo separado com o python do sistema |
| AV1 | somente decode nesta GPU | não ofereça encode AV1 |

Duas consequências que não são negociáveis:

- **O encoder por hardware não está disponível hoje.** O produto deve funcionar com
  `x264enc` (`tune=zerolatency`, `speed-preset` conservador), publicar
  `hardwareEncoder: false` no contrato e informar ao usuário, com ação concreta, que
  instalar o plugin VA do GStreamer habilita o encoder do aparelho. Detecte o
  elemento em tempo de execução e prefira-o quando existir. **Não** instale o pacote.
- **`gi` não está no `.venv`.** Não adicione PyGObject ao lock de runtime. O motor é
  um processo separado executado com `/usr/bin/python3`, conforme a seção 3.

## 3. Arquitetura obrigatória

```
QML / CLI
    │  ações nomeadas da allowlist (service/methods.py)
    ▼
domain.screencast (puro, já entregue — NÃO reescrever)
    │  decide: alvo, modo, negociação, degradação, recuperação
    ▼
adapters.screencast_web  (implementa ScreenCastProviderPort)
    │  supervisiona o motor + serve a página do receptor
    │  IPC: Unix socket, JSON por linha, versionado, idempotente
    ▼
steamzero-cast-engine   (processo separado: /usr/bin/python3 + gi + GStreamer)
    │  portal ScreenCast → pipewiresrc → encoder → webrtcbin
    ▼
navegador (página receptora servida pelo próprio produto)
```

Regras de arquitetura que o CI verifica ou que o supervisor vai ler no diff:

- `domain.*` continua puro: sem I/O, sem rede, sem `subprocess`, sem importar
  `adapters.*`. Toda decisão nova de política vai para domínio puro e testado.
- O motor **não importa nada de `steamzero`** — apenas stdlib e `gi`. Ele é resolvido
  como arquivo dentro do pacote (`importlib.resources`) e executado por caminho.
  Assim ele roda no python do sistema sem o `.venv`.
- `import gi` precisa ficar tolerável para o mypy: adicione um override
  `ignore_missing_imports` para `gi.*` em `pyproject.toml`, no mesmo padrão do
  override existente de `jsonschema`.
- Escrita em disco só por `core.fs`. Rede só pelo que esta tarefa define
  explicitamente. Nenhuma string de shell; `subprocess` com lista de argumentos.
- Falha do motor **não pode derrubar o launcher**, e reinício da UI **não pode
  derrubar a sessão** (ADR-0022 §8).

## 4. Escopo, item por item

Rode os quatro gates (seção 6) **depois de cada item** e faça um commit por item.

### Item 1 — ADR-0023 e ordem das vias

Escreva `docs/adr/0023-via-receptor-navegador.md` (status: aceito) registrando:

- `web-receiver` é a primeira via implementada, com dupla função: veículo de
  verificação sem hardware de terceiros e receptor de contingência real;
- o plano de mídia é delegado ao GStreamer (`webrtcbin` + encoder do sistema); o
  produto não escreve codec, congestionamento nem retransmissão;
- ordem revisada das vias: `web-receiver` (agora) → `game-stream` para Android
  TV/Google TV, Tizen/webOS e outro PC → `steam-remote-play` → `screen-mirror` →
  `media-cast`;
- por que o navegador não substitui a via nativa: sem app na TV, a decodificação e o
  controle dependem do navegador do aparelho, e a latência é pior;
- fronteira preservada: em WI-S1 a sinalização é **loopback**; nada de rede local
  ainda, portanto B0 (`backlog-protected`) continua intocado.

### Item 2 — política pura de pareamento e a via no domínio

- Novo módulo puro `src/steamzero/domain/screencast_pairing.py`:
  - política de PIN: comprimento e alfabeto declarados (sem ambiguidade visual),
    janela de validade, limite de tentativas, exigência de comparação em tempo
    constante expressa no contrato da função;
  - registro de receptor confiável (forma do dado, expiração, revogação);
  - decisão pura "aceita / recusa / expirou / excedeu tentativas" devolvendo o código
    de erro do catálogo quando recusa. **Nenhuma geração de aleatoriedade aqui** — o
    valor vem de fora, de `secrets`, no adapter.
- Em `domain/screencast.py`, adição **mínima e aditiva**: novo valor
  `CastProtocol.WEB_RECEIVER = "web-receiver"`, entrada em `_PROTOCOL_MODES`
  (`GAME`, `GAME_WINDOW`, `MIRROR`) e posição na preferência de cada modo **depois**
  de `GAME_STREAM` (app nativo ganha do navegador em latência) e antes de
  `STEAM_REMOTE_PLAY`. Não altere semântica existente; os 43 testes atuais de
  `tests/unit/test_screencast.py` devem continuar passando sem edição. Se algum
  precisar mudar, pare e explique no relatório — mudar teste para passar é proibido.
- `src/steamzero/schemas/screen-cast-v1.schema.json`: acrescente `web-receiver` ao
  enum de `protocol`. Mudança aditiva; `schemaVersion` continua 1. Justifique no
  WI-S1.

### Item 3 — motor de transmissão em processo separado

`src/steamzero/adapters/cast_engine.py` — stdlib + `gi` apenas:

- pede a sessão de captura ao **xdg-desktop-portal** (`ScreenCast`), respeitando a
  escolha do usuário entre monitor, janela e — quando o backend suportar — monitor
  virtual. Sem autorização, encerra com causa; nunca tenta contornar;
- pipeline de vídeo: `pipewiresrc` (fd do portal) → conversão → encoder
  (elemento VA quando existir, senão `x264enc` com latência mínima) →
  `rtph264pay` → `webrtcbin`;
- pipeline de áudio opcional: monitor do PipeWire → `opusenc` → `webrtcbin`;
- protocolo de IPC em socket Unix, JSON por linha, com campo de versão:
  `START_SESSION`, `STOP_SESSION`, `PAUSE_SESSION`, `RESUME_SESSION`, `SET_QUALITY`,
  `REQUEST_KEYFRAME`, `GET_STATUS`, mais sinalização (`OFFER`, `ANSWER`, `CANDIDATE`).
  **Todo comando é idempotente**: `STOP_SESSION` duas vezes não é erro (ADR-0022 e
  spec §19);
- publica telemetria periódica derivada das estatísticas do `webrtcbin` (RTT, perda,
  fila do decodificador, tempo de codificação) no formato que `LinkSample` espera.
  Nunca publica conteúdo de tela, nome de janela, PIN ou chave;
- encerra limpo em SIGTERM, liberando a sessão do portal.

### Item 4 — provedor `web-receiver`

`src/steamzero/adapters/screencast_web.py`, implementando `ScreenCastProviderPort`:

- `preflight()` verifica, em ordem, portal, PipeWire, `gi`, elementos GStreamer e
  encoder por hardware, devolvendo motivo estável e específico
  (`portal-missing`, `engine-missing`, `element-missing`, `encoder-software-only` —
  este último **não** é falha, é capacidade reduzida honesta);
- `local_capabilities()` reflete o que foi medido agora, não o que se espera;
- `discover()` devolve o receptor de navegador local como candidato, com capacidade
  observada da própria página quando ela já se anunciou, e capacidade mínima honesta
  antes disso;
- supervisão do motor: spawn, health check, backoff progressivo de reinício,
  detecção de morte. Motor morto vira falha de enlace tratada pelo domínio
  (`plan_recovery`), **nunca** exceção que sobe até a UI;
- serve a página receptora e a sinalização **somente em 127.0.0.1**, com token
  efêmero por sessão, no mesmo padrão da bridge de `adapters/desktop_ui.py`
  (loopback, allowlist, corpo limitado). Nenhum bind em `0.0.0.0` neste WI;
- `stop()` idempotente e sempre libera a captura.

### Item 5 — página receptora

`src/steamzero/ui/receiver/` (HTML + JS + CSS, carregados por `importlib.resources`):

- `RTCPeerConnection` somente-recepção, vídeo em tela cheia, áudio sincronizado;
- zero recurso externo: nenhum CDN, nenhuma fonte remota, nenhum script de terceiros
  (funciona offline e sobrevive a política restritiva de conteúdo);
- estado visível: conectando, transmitindo, qualidade reduzida, reconectando, e a
  causa quando falha — texto pt-BR do catálogo de erros, nunca "erro desconhecido";
- botão grande "Encerrar transmissão", alcançável por teclado e por gamepad
  (`navigator.getGamepads`), com foco visível — a tela roda em TV e no Deck;
- não exibe PIN nem endereço em nenhum log do console.

### Item 6 — ações, CLI e diagnóstico

- `src/steamzero/service/methods.py`: acrescente ao `METHOD_SPECS`, seguindo
  exatamente o padrão existente — `cast.status` (read), `cast.discover` (read),
  `cast.receiver` (read; devolve a URL local do receptor e o texto do QR),
  `cast.start` (mutation), `cast.stop` (mutation). A tabela alimenta CLI e serviço de
  uma vez; não crie um caminho paralelo;
- CLI correspondente em `src/steamzero/cli/main.py`, com envelope padrão, para que a
  via seja verificável sem UI;
- `diagnostics/doctor`: um check novo que reporta a prontidão da transmissão e,
  explicitamente, se o encoder é de hardware ou de software. Check em falha não pode
  virar blocker de boot.

### Item 7 — testes

Além de unidade para tudo que é puro:

- **falha injetada** (`tests/failure_injection/`, marca `fi`): motor morre no meio da
  sessão; consentimento negado; consentimento revogado durante a sessão; porta de
  sinalização ocupada; `STOP_SESSION` duas vezes; motor que não responde ao health
  check; troca de resolução no meio da sessão. Em todos: estado utilizável e causa
  registrada, launcher vivo;
- **segurança** (`tests/security/`, marca `security`): sinalização recusa origem não
  loopback; requisição sem token é recusada; PIN não aparece em log, envelope, evento
  ou payload público; nome e endereço do receptor não aparecem no contrato público;
  nenhuma string de shell chega ao `subprocess`;
- **integração real** (marca `integration` e `slow`, com `skipif` quando `gi` ou os
  elementos GStreamer faltarem): sobe o motor, usa um **segundo `webrtcbin` como
  receptor no lugar do navegador** e prova que quadros reais chegam, que
  `SET_QUALITY` muda o bitrate aplicado e que `STOP_SESSION` libera a captura. Este
  teste é a evidência objetiva de que a via funciona sem depender de um humano
  olhando a tela.

### Item 8 — documentação

- `docs/expansion/WI-S1.md` no formato dos WI existentes (entrega, robustez,
  segurança, evidência com números reais, estado final);
- linha S1 do `docs/EXPANSION-LEDGER.md` para `verified-dev` (ou
  `verified-offscreen`, se a evidência for só o teste com o segundo peer);
- códigos novos, se houver, em `core/errors.py` + i18n pt-BR + `ERROR-CATALOG.md`
  (todo código exige os cinco campos e um teste que o dispara);
- `docs/WORKLOG.md`: **somente acrescente** sua sessão ao final. Não edite nada
  anterior.

## 5. Proibições explícitas

Violar qualquer uma destas invalida a entrega:

1. **Nenhuma ação no host.** Sem `sudo`, sem `bigsudo`, sem `pacman`/instalação de
   pacote de sistema, sem unit systemd, sem escrever em `/opt`, `/usr`, `/etc` ou
   `/boot`. A autorização de `bigsudo` concedida pelo operador é da sessão do
   supervisor e, por `AGENTS.md` §1, **não se transfere para você**. Se o encoder por
   hardware exigir `gst-plugin-va`, isso é ação do operador — registre no relatório.
2. **Nenhum artefato de release.** Sem `pip wheel`, sem wheelhouse, sem manifesto.
   Se aparecer algo em `dist/` no seu diff, remova.
3. **Nenhuma exposição de rede local.** A sinalização é loopback neste WI. Bind em
   `0.0.0.0`, mDNS, descoberta em sub-rede e pareamento remoto ficam para WI-S2, com
   o endurecimento próprio. B0 segue `backlog-protected`.
4. **Nenhum teste enfraquecido ou removido para passar.** Cobertura não regride
   (mínimo global 85%). Se um contrato mudou de verdade, o commit explica qual e por
   quê.
5. **Nenhuma referência a projetos de pesquisa** (PhaseZero, RetroDECK, LinuxToys) em
   código, string, path ou comentário — `make independence` exige a ausência.
6. **Nenhuma edição fora do seu escopo de arquivos.** Em especial: não commite em
   `codex/compartilhar-tela-um-toque` nem em qualquer branch de outro agente; não
   reescreva `domain/screencast.py` além da adição aditiva do item 2; não toque em
   sessões anteriores do WORKLOG.
7. **Nenhum contorno de proteção de conteúdo.** Sem injeção em processo de jogo, sem
   burlar HDCP/DRM, sem captura por caminho não oficial do compositor.
8. **Nenhum `force push`.** Push apenas da sua branch.

## 6. Gates — depois de cada item, não só no fim

```
.venv/bin/pytest tests -q
.venv/bin/ruff check src tools tests
.venv/bin/ruff format --check src tests tools
.venv/bin/mypy
make independence boundaries
```

Linha de base a preservar (medida no commit `85153b9`): **1.518 testes aprovados**,
Ruff limpo, mypy em 156 módulos, independência e fronteiras OK, cobertura total
**85,62%**. Cobertura não regride; módulos puros novos devem ficar em 100% ou
justificar cada linha descoberta.

Não declare um gate verde sem ter executado o comando naquele commit. O supervisor
reexecuta todos, e já houve caso neste repositório de relatório declarando Ruff verde
com Ruff vermelho.

## 7. Branch e entrega

- Crie `codex/compartilhar-tela-s1-web-receiver` a partir de `85153b9` (tip de
  `codex/compartilhar-tela-um-toque`), preferencialmente em worktree própria para não
  perturbar o checkout do supervisor.
- Confirme a base pelos marcadores de `AGENTS.md` §3: `__version__ = "0.1.0a34"`,
  instalador com `"schemaVersion": 4`, `adapters/steam_boot.py` e
  `adapters/steam_session.py` presentes, e `domain/screencast.py` presente.
- Um commit por item, mensagem no idioma e formato dos commits recentes.
- Relatório final com, obrigatoriamente:

| Seção | Conteúdo |
|---|---|
| Item → commit → testes | um por item, com os testes que **provam** cada um |
| Números dos gates | contagem de testes, cobertura total, cobertura dos módulos novos |
| Fora de escopo | o que você viu e não fez, e por quê |
| Ações de host | deve ser "nenhuma"; qualquer exceção é violação a explicar |
| Pendências do operador | o que exige decisão ou hardware humano (ex.: `gst-plugin-va`) |
| Riscos conhecidos | onde a via ainda é frágil e o que WI-S2 precisa endurecer |

## 8. Como o supervisor vai validar

Construa para este crivo:

1. **Gates reexecutados do zero** no seu commit. Divergência entre o relatado e o
   medido reprova a entrega inteira, não só o item.
2. **Leitura do diff** buscando: pureza do domínio; ausência de import de
   `steamzero` no motor; bind estritamente loopback; `stop()` idempotente; morte do
   motor não propagando exceção à UI; nenhum PIN, nome ou endereço em log, evento ou
   payload público; `subprocess` sem shell.
3. **Teste de integração real** executado no host: quadros de verdade saindo do
   pipeline, `SET_QUALITY` alterando o bitrate, captura liberada no fim.
4. **A página receptora aberta num navegador de verdade**, com verificação de vídeo,
   de degradação sob rede ruim e de reconexão após queda.
5. **Falhas provocadas à mão**: matar o motor durante a sessão; negar o
   consentimento; revogar o consentimento no meio; fechar a aba do receptor. Critério
   de aprovação em todos: estado utilizável, causa registrada, launcher vivo, captura
   encerrada.
6. Só depois disso, e só com a autorização do operador já concedida ao supervisor, a
   release canônica é construída do seu commit e instalada para o teste físico. O
   teste de boot e a inspeção visual continuam sendo do operador.

## 9. Critérios de aceite do WI-S1

- [ ] O usuário inicia a transmissão para o navegador com um comando (ou um toque,
      quando a UI chegar em WI-S3) e vê a tela do aparelho na página.
- [ ] Nada é capturado sem autorização explícita do portal.
- [ ] O encoder por hardware é usado quando existe; quando não existe, a sessão
      funciona em software e a interface **diz isso** com ação concreta.
- [ ] A qualidade cai antes da sessão cair, e sobe de volta quando o enlace melhora.
- [ ] Troca de resolução não encerra a sessão.
- [ ] Matar o motor não derruba o launcher; reiniciar a UI não derruba a sessão.
- [ ] `STOP_SESSION` repetido não é erro, e sempre libera a captura.
- [ ] Nenhum log, evento ou payload público contém conteúdo de tela, nome de janela,
      endereço ou PIN.
- [ ] A sinalização não aceita nada que não seja loopback neste WI.
- [ ] Os quatro gates verdes em cada commit, sem regressão de cobertura.
