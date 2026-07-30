# Diagnóstico operacional real da a41 no host

**Data da coleta:** 2026-07-30

**Release observada:** `0.1.0a41-31b30211ba85`

**Escopo:** journal do usuário e do sistema, SQLite, filesystem, coredumps,
systemd, CLI instalada e código em `origin/main` no commit
`175d83b79b6e472302c0a11ebc39d703078c02cc`.

Este documento complementa, sem substituir, a certificação física da a41. A
certificação provou instalação, convergência, idempotência e rollback
`a41 → a40 → a41`. A inspeção posterior encontrou defeitos operacionais que
aquele protocolo não exercitava.

## Vocabulário de evidência

- **Fato:** observado diretamente em fonte persistente, comando read-only ou
  código identificado.
- **Inferência:** conclusão compatível com mais de uma evidência, mas que ainda
  precisa de um teste causal.
- **Hipótese:** explicação plausível que não pode ser tratada como causa raiz.

Nenhuma coleta incluiu conteúdo de keys, credenciais, tokens ou ROMs. Nomes de
jogos e caminhos privados que não alteram o diagnóstico foram omitidos.

## Veredito

**Fato:** a41 continua instalada e convergida, e não houve evidência de OOM,
reset de GPU, erro de filesystem, crash da UI interativa ou perda de dados na
janela inspecionada.

**Fato:** o host não está operacionalmente limpo. Há dois jobs antigos
publicados como `running`, cerca de 1,1 GB de artefatos transacionais no state
home, divergência entre o lifecycle real dos emuladores e sua projeção,
falha remota de mídia escondida, GameMode com efeitos privilegiados recusados e
quatro abortos de `qml6` durante gates.

**Inferência:** os gates atuais cobrem corretamente a mecânica de release, mas
permitem falsos verdes na saúde de jobs, componentes, mídia, performance e
runtime visual. Por isso a próxima release deve ser exclusivamente de
estabilização.

## Fontes e reprodutibilidade

| Fonte | Evidência coletada | Limite |
|---|---|---|
| `journalctl --user` e journal do sistema | lifecycle da UI, emuladores, GameMode e serviço externo | retenção disponível no host |
| SQLite do state store | jobs, resultados, operações, sessões e mídia | leitura somente; valores sensíveis não foram publicados |
| state/data homes do SteamZero | contagem, tamanho, idade e referências de artefatos | nenhum arquivo foi removido |
| `systemctl`, `/proc` e symlink `current` | identidade e recursos agregados do serviço | o escopo agrega UI e filhos |
| `coredumpctl` | processos e sinais do boot corrente | quatro entradas não tinham dump armazenado |
| CLI e workspace instalados | doctor, componentes, mídia e prontidão | snapshot pontual |
| código em `origin/main` | caminhos que explicam a projeção observada | não prova sozinho o comportamento do host |

### Índice de evidência

Os comandos abaixo identificam a classe de coleta; saídas com dados privados
foram reduzidas a contagens, estados e códigos:

| ID | Fonte reproduzível |
|---|---|
| E-HOST-01 | `systemctl --user status/show`, identidade do daemon e `readlink` de `current` |
| E-HOST-02 | `journalctl --user` e journal do sistema filtrados pelo boot e pelas units/processos relevantes |
| E-HOST-03 | consultas read-only ao state store: jobs, operações, sessões e mídia |
| E-HOST-04 | contagem e uso de disco de journal, plans, backups e staging; cruzamento de IDs com a tabela `operation` |
| E-HOST-05 | `coredumpctl list` no boot corrente |
| E-CODE-25 | `src/steamzero/jobs/manager.py:191` (`cancel`) e `:293` (`recover`); busca de callers no bootstrap |
| E-CODE-27 | `src/steamzero/cli/main.py:550`/`:553`; `src/steamzero/adapters/emulation.py:2421`/`:2498` |
| E-CODE-28 | resultado do job no SQLite versus composição de `providerErrors` em `src/steamzero/adapters/emulation.py` |
| E-CODE-29 | capability `gamemode` em `src/steamzero/adapters/steam_gameplay.py:731` e policy instalada no host |
| E-CODE-31 | `tools/qml_capture_runner.py:306` |
| E-GOV-01 | APIs read-only do GitHub para branch protection, rulesets, security features, tags, releases e retenção dos workflows |

Os números de linha referem-se ao commit base declarado no cabeçalho e podem
mudar depois dos PRs técnicos.

## Timeline consolidada

Todos os horários abaixo são do host; onde a fonte estava em UTC isso é
declarado.

| Instante | Evento | Classificação |
|---|---|---|
| 2026-07-26 | dois jobs `media.global` passam a `running` e não chegam a estado terminal | fato, SQLite |
| 2026-07-29 | certificação física `a41 → a40 → a41`; convergência e idempotência aprovadas | fato, relatório de certificação |
| 2026-07-30 05:21–05:34 | sessão física da UI a41; encerramento normal com código 0 | fato, journal |
| 2026-07-30 05:28–05:29 | Eden aberto e encerrado | fato, journal/processos |
| 2026-07-30 05:29–05:33 | Ryubing aberto e encerrado | fato, journal/processos |
| 2026-07-30 08:25:02–08:28:00 UTC | refresh de mídia processa 15 jogos, atualiza zero e persiste quota excedida | fato, SQLite |
| boot corrente, quatro instantes | `qml6` termina em `SIGABRT` durante gates | fato, `coredumpctl` |
| 2026-07-30 | inspeção read-only confirma release a41, daemon convergido e gaps G25–G31 | fato, fontes acima |

Abrir Eden e Ryubing prova somente o lifecycle do executável. Não prova
lançamento canônico de ROM, criação de sessão, playtime ou encerramento de jogo.

## GAP-G25 — jobs stale, recuperação desconectada e doctor falso verde (P0)

**Fatos**

- Os jobs `01KYE7851FA16NWYTZRPQ052J2` e
  `01KYE77Y5PRQCT71CKZPDGQ1J4`, ambos `media.global`, permaneciam `running`
  desde 2026-07-26.
- O doctor da a41 publicou `ok`, schema 13 e zero operações pendentes.
- `JobManager.recover()` existe em
  `src/steamzero/jobs/manager.py`, mas a busca no bootstrap não encontrou
  chamada.
- `JobManager.cancel()` apenas registra o pedido quando o job está `running`.
  Para um job stale sem runner, não há consumidor que o leve a estado terminal.

**Inferência:** o daemon pode reiniciar preservando uma mentira operacional no
SQLite, e o doctor não a detecta porque seu gate atual não audita jobs stale nem
a coerência completa entre jobs, operações e artefatos.

**Impacto:** P0 por falso verde e por risco de decisões de cleanup sobre estado
que ainda parece ativo.

## GAP-G26 — testes contaminam o XDG real e acumulam artefatos (P0)

**Fatos**

- O state home real continha aproximadamente 1,1 GB:
  1.893 journals, 3.248 planos, 1.900 diretórios de backup, 651 MB de staging e
  353 MB de backups.
- Dos journals, 1.829 terminavam em rollback: 1.551
  `media.reconcile`, 209 `switch-library.rename` e 67
  `media.prune-orphan-cache`.
- A tabela de operações tinha somente 709 operações rolled-back e 25 commits,
  quantidade incompatível com os artefatos do filesystem.
- Duas árvores de staging antigas não tinham operação correspondente no banco.
- Testes usam `tmp_path` para payloads, mas parte do núcleo transacional resolve
  journal, planos e backups pelo XDG do processo. Grupos de três rollbacks
  `media.reconcile` coincidem com execuções da suíte.

**Inferência:** a suíte isola os alvos de dados, mas não isola integralmente os
cinco homes XDG antes da inicialização. A correlação temporal e a distribuição
por tipo são suficientes para registrar a contaminação; cada teste responsável
deverá ser provado no PR corretivo.

**Relação com GAP-G23:** G23 permanece fechado na forma em que foi diagnosticado
e corrigido. G26 prova que o risco mais amplo de isolamento XDG era real e não
estava restrito ao round-trip que originou G23.

**Impacto:** P0 por mutação de estado do usuário durante testes e por tornar
auditorias/cleanup não confiáveis. O acervo existente não deve ser apagado sem
plano, quarentena e autorização humana.

## GAP-G27 — lifecycle de componente perde a verdade (P1)

**Fatos**

- Eden e Ryubing estavam saudáveis; Citron tinha payload e metadata AppImage,
  mas `AdapterEngine.status("citron")` publicou `degraded` por drift de
  manifesto.
- A projeção da UI converteu Citron em “não instalado”.
- Citron continuava configurado como default, enquanto a plataforma publicava
  100% de prontidão.
- `component list` roteava adapters do registry por `FlatpakExecutor`, inclusive
  os de origem AppImage, e abortava com
  `E-COMPONENT-DEGRADED` ao chegar ao Citron.
- A composição de linhas trata estado diferente de `installed` como
  `not-installed`, eliminando a distinção `degraded`.

**Inferência:** CLI, workspace e QML mantêm mais de uma regra de lifecycle e
perdem informação ao atravessar as camadas.

**Impacto:** P1; pode induzir reparo, instalação ou lançamento com base em um
estado falso. O default não pode ser trocado silenciosamente.

## GAP-G28 — falha de mídia persistida não chega à UI (P1)

**Fatos**

- O refresh de mídia processou 15 jogos em cerca de 177 segundos, atualizou
  zero e terminou tecnicamente como `completed`.
- O resultado persistido contém
  `screenscraper: E-SCRAPE-QUOTA-EXCEEDED`.
- SteamGridDB não produziu correspondências úteis; isso, isoladamente, não é
  erro.
- A projeção do workspace publicou `providerErrors: {}`.
- Das 16 linhas inspecionadas na tabela de mídia, 14 eram fallback de ícone,
  uma custom e uma fallback de erro; não havia evidência de mídia remota útil.
- Credenciais estavam configuradas no cofre, mas sem validação registrada. Seus
  valores não foram lidos nem expostos.

**Inferência:** o resultado terminal do job e a saúde dos providers não são a
fonte usada pela projeção atual. “Completed” descreve o runner, não o sucesso do
objetivo do usuário.

**Impacto:** P1; o usuário espera por minutos, recebe zero atualização e não vê
a causa nem a ação corretiva.

## GAP-G29 — GameMode mede presença, não efeitos ativos (P1)

**Fatos**

- `gamemoderun` e `gamemoded` estavam presentes.
- O journal registrou recusa de autorização para governor, `split_lock` e
  operações de prioridade.
- A policy instalada autoriza membros do grupo `gamemode`; o usuário da sessão
  não era membro.
- A prontidão atual em `steam_gameplay.py` é derivada principalmente da
  presença do binário.

**Inferência:** “ready” confunde quatro estados diferentes: binário presente,
daemon disponível, helper autorizado e efeito realmente aplicado.

**Impacto:** P1 de confiança e desempenho. A falha pode degradar performance,
mas não precisa bloquear o lançamento. Alteração de grupo/Polkit exige
autorização humana e nova sessão.

## GAP-G30 — recursos agregados não permitem atribuição (P1)

**Fatos**

- O escopo systemd observado atingiu 5,7 GB de memória e 661,7 MB de swap.
- O mesmo escopo agregava UI e processos filhos dos emuladores.
- Não houve OOM, reset de GPU ou erro de filesystem na janela.

**Hipótese rejeitada como conclusão:** esses números, sozinhos, não provam
vazamento da UI.

**Impacto:** P1 para robustez: sem PSS e lifecycle separados de UI, job de mídia
e emuladores, o gate não consegue detectar regressão nem atribuir consumo.

## GAP-G31 — probe Qt aceita processo abortado como evidência (P2)

**Fatos**

- `coredumpctl` registrou quatro processos `qml6` terminados em `SIGABRT`
  durante gates; nenhum dump estava armazenado.
- A UI interativa a41 encerrou normalmente.
- `check_runtime_version()` em `tools/qml_capture_runner.py` executa
  `qml6 --version`, mas não rejeita explicitamente `returncode != 0` antes de
  interpretar a saída.

**Hipótese forte:** o probe de versão gerou os abortos. A proximidade funcional
e o defeito de validação sustentam investigação, mas não provam causalidade.

**Impacto:** P2; um runtime abortado pode produzir falso verde visual e
coredumps/ruído. O gate corretivo precisa provar zero novo `SIGABRT`.

## Evidências negativas e limites

- Não houve OOM, reset de GPU, erro de filesystem/NVMe nem crash da UI
  interativa na janela inspecionada.
- Playtime zero não é defeito comprovado: não houve prova de lançamento
  canônico de uma ROM.
- Zero resultados SteamGridDB não é, por si, falha do provider.
- O pico de 5,7 GB não é atribuído à UI sem medição por processo/PSS.
- A relação entre `check_runtime_version()` e os quatro `SIGABRT` permanece
  hipótese.
- Nenhum emulador estava instalado no instante da certificação a41. Eden,
  Citron e Ryubing foram instalados depois; esse fato posterior não altera o
  veredito histórico.

## Ruído externo que invalida benchmark

**Fato:** o serviço externo `9router` estava em restart storm por
`EADDRINUSE` na porta local que tentava ocupar, com milhares de reinícios na
janela observada. O serviço não pertence ao SteamZero.

**Inferência:** benchmarks de CPU/latência feitos enquanto essa tempestade
persistir não são comparáveis. O SteamZero não deve tentar corrigir ou parar o
serviço, mas o preflight de benchmark deve registrar a contaminação.

## Governança e documentação stale

Verificações read-only do repositório e do GitHub em 2026-07-30 registraram:

- branch `main` sem proteção/ruleset;
- Dependabot, secret scanning/push protection e code scanning desabilitados;
- ausência de releases GitHub duráveis para a linha atual; artefatos de CI têm
  retenção finita;
- a37 aparecia como “Latest”, apesar da tag a41 existente;
- `IMPLEMENTATION-REPORT.md` ainda descreve 434 testes e daemon ausente, embora
  a certificação a41 registre 3.254 testes e daemon persistente;
- `docs/00-vision/NON-GOALS.md` ainda descreve boot como fora do escopo, embora
  exista implementação e certificação parcial de Game Mode/boot.

Esses itens são dívidas de governança/documentação, não evidência de regressão
funcional da a41. Este PR apenas os registra; não altera configuração remota,
tags ou releases.

## Impacto no roadmap e ordem obrigatória

1. **a42 somente estabilização:** GAP-G26, GAP-G25, GAP-G27, GAP-G28,
   GAP-G29 e GAP-G30/G31, nessa ordem causal.
2. **Depois da a42:** retomar P0-03, acessibilidade e os marcos M10–M15.
3. **Antes de certificar a42:** todos os P0/P1 acima mesclados, gates verdes e
   novas autorizações para build, instalação, alteração administrativa,
   cleanup e ciclo físico.
4. **Certificação física:** `a42 → a41 → a42`, incluindo doctor sem falso verde,
   state audit, truth de componentes/mídia/GameMode, UI física e lançamento
   canônico de uma ROM.

Nenhum resultado desta coleta promove mídia, primeiro jogo, GameMode ou o
produto como um todo a `verified-hw`.
