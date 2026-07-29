# A38 — resultado da certificação física

**Data:** 2026-07-29 · **Host:** misael-jupiter · BigLinux/Manjaro · kernel 6.18.38-1
**Sessão:** Wayland/KDE · **Usuário:** misael (uid 1000)

**Veredito: certificação PARCIAL. A tag `v0.1.0a38` NÃO foi criada.**

A a38 instala, converge e faz roll-forward corretamente. O que reprovou foi a
perna do **rollback**: voltar para a a37 deixa um daemon a38 vivo, e a a37 não
tem comando algum capaz de detectar ou corrigir isso.

## Estado final do host

```
current:  /opt/steamzero/releases/0.1.0a38-48f4034dfe36
daemon:   /opt/steamzero/releases/0.1.0a38-48f4034dfe36/venv/bin/python3
CLI:      0.1.0a38
socket:   active     service: active
doctor:   ok (0 checks não-ok)
gamemode: ok         host status: ok: true
```

O host **não** ficou na a37. O roll-forward foi executado e convergiu.

## Tabela de verificação

| Verificação | Esperado | Resultado observado | Evidência | Estado |
|---|---|---|---|---|
| Hashes dos artefatos | 10/10 | 10/10 SUCESSO | `sha256sum -c` no diretório correto | ✅ |
| Procedência do manifesto | commit/versão/árvore | commit `48f4034d`, `0.1.0a38`, `clean`, lock e wheel conferem | 6 comparações | ✅ |
| Instalação a38 | sucesso | `ok: true`, `release: 0.1.0a38-48f4034dfe36` | JSON do instalador | ✅ |
| `current` após instalação | a38 | `/opt/steamzero/releases/0.1.0a38-48f4034dfe36` | `readlink -f` | ✅ |
| Estado pós-instalação | `pending` declarado | `daemonRefresh.state = pending` | JSON do instalador | ✅ |
| Convergência do daemon | `converged` | `converged`, restart real, 1 tentativa | JSON do refresh | ✅ |
| CLI | 0.1.0a38 | `0.1.0a38` | `--version` | ✅ |
| Doctor | saudável | `ok`, 0 checks não-ok | JSON | ✅ |
| Socket | active | `active` | systemd | ✅ |
| Game Mode check | sucesso | `state: ready`, exit 0 | saída JSON | ✅ |
| Host status | `ok: true` | `ok: true` | JSON | ✅ |
| Idempotência do refresh | sem restart | `converged`, `restarted: false` | JSON | ✅ |
| UI Desktop | abre/navega | processo vivo 25 s, sem crash | `ps`, stderr | ⚠️ |
| **Rollback a38→a37** | sucesso | `current` mudou, **daemon ficou na a38** | `pgrep` | ❌ |
| **Daemon na a37** | `converged` | **não convergiu; a37 não tem o comando** | usage da a37 | ❌ |
| Roll-forward a37→a38 | sucesso | `ok: true` | JSON | ✅ |
| Daemon final na a38 | `converged` | `converged`, `restarted: true` | JSON do refresh | ✅ |
| Tag | commit certificado | **não criada** | — | ⛔ |
| Pre-release | publicada | **não publicada** | — | ⛔ |

## Bloqueador 1 — rollback deixa daemon stale e a a37 não tem gate

**Severidade: P0.** É a regressão da a37 reproduzida ao vivo, agora com evidência
direta.

Depois de `rollback --release 0.1.0a37-2aaa01d9d8b6`:

```
current aponta para: /opt/steamzero/releases/0.1.0a37-2aaa01d9d8b6
daemon executa:      /opt/steamzero/releases/0.1.0a38-48f4034dfe36/venv/bin/python3
```

O `current` mudou; o processo não. E a a37 **não possui o comando
`service refresh`** — a listagem de domínios da a37 não o inclui, e invocá-lo
devolve `E-CLI-USAGE`. Ou seja: ao voltar para a a37, o gate de convergência
volta junto, e não há como detectar nem corrigir o daemon defasado pela CLI
ativa.

O rollback em si funcionou (`ok: true`, manifesto verificado). O que não existe
é a convergência verificável do outro lado.

**Inferência, não medição:** o `ExecStart` da unit é
`/opt/steamzero/current/venv/bin/steamzero-core`, e o refresh da a38 convergiu
justamente reiniciando a unit. Logo, `systemctl --user restart
steamzero-core.service` provavelmente converge a a37 manualmente. **Isso não foi
executado nesta sessão** e não deve ser tratado como verificado.

## Bloqueador 2 — códigos do HOST-ACTIVATION-01 fora do catálogo de erros

**Severidade: P1.** Defeito introduzido por mim no HOST-ACTIVATION-01.

Quando o gate detecta falha de restart, o envelope quebra:

```
E-INTERNAL-UNEXPECTED: código de erro não registrado no catálogo:
'E-HOST-RESTART-FAILED'
```

Os cinco códigos (`E-HOST-RELEASE-MISMATCH`, `E-HOST-DAEMON-PENDING`,
`E-HOST-CONVERGENCE-TIMEOUT`, `E-HOST-RESTART-FAILED`,
`E-HOST-CURRENT-UNREADABLE`) foram definidos no adapter e **nunca registrados no
catálogo**. O caminho de sucesso funciona — por isso a instalação passou —, mas o
diagnóstico específico é substituído por erro interno genérico exatamente quando
mais importa.

Os testes não pegaram porque exercitam `converge()` diretamente, sem atravessar
`build_error`.

## Bloqueador 3 — `emulation workspace` não lê o estado real do host

**Severidade: P1. Pré-existente, não introduzido pela a38** — confirmado por
comparação direta nas duas releases.

| release | truthState | plataformas | com jogos |
|---|---|---|---|
| a38 | `unverified` | 36 | 0 |
| a37 | `unverified` | 36 | 0 |

O host tem `prod-4b5808630667.keys` (14.612 bytes) e **15 jogos** em
`emulation-library-cache-v1.json`. Mesmo assim toda plataforma volta com
`status: None` e `gameCount: None`.

A causa está em `cli/main.py::_cmd_emulation_workspace`:

```python
workspace = build_switch_workspace(
    probe=lambda emulator_id: shutil.which(emulator_id) is not None,
)
```

`build_switch_workspace` aceita `keys`, `firmware`, `games`,
`emulator_capabilities` e `emulator_facts` — e **nenhum é passado**. O read model
é construído sem o estado do host, então chaves e biblioteca válidas aparecem
como ausentes. É a assinatura descrita no diagnóstico da a37.

## Warnings não bloqueantes

A UI Desktop emitiu 46 warnings de QML em 25 s. **Todos** de
`qrc:/qt/qml/org/kde/breeze/*` — o estilo Breeze do KDE, terceiro. Nenhum de
QML do SteamZero. Não bloqueia, mas polui o log e atrapalha a coleta de warnings
próprios.

## Limitação do teste de UI

O processo subiu e sobreviveu 25 s sem crash nem loop. **Não houve navegação
interativa verificada** — biblioteca, página de emulação, página Steam e retorno
ao Desktop não foram exercitados por interação real. Marcado ⚠️, não ✅.

## Por que a tag não foi criada

A sequência exigida era:

```
instalar → convergir → smokes → rollback real → smokes → roll-forward → smokes
```

A perna do rollback não produziu daemon convergido na a37. Criar a tag agora
declararia certificado um ciclo que não fechou.

## Reproduzir a evidência

```bash
cd /mnt/sdcard/Projects/Port_Steam/release-artifacts/a38-48f4034dfe36
test "$(basename "$PWD")" = "a38-48f4034dfe36" && sha256sum -c VERIFIED-SHA256SUMS

steamzero service refresh --expect-release 0.1.0a38-48f4034dfe36 --json
pgrep -af 'steamzero-core --systemd'
readlink -f /opt/steamzero/current

# bloqueador 3, idêntico nas duas releases:
steamzero emulation workspace --json | python3 -c \
  "import json,sys; w=json.load(sys.stdin)['data']; \
   print(w['truthState'], len(w['platforms']), sum(1 for p in w['platforms'] if p.get('gameCount')))"
ls -l ~/.local/share/steamzero/keys/switch/
```
