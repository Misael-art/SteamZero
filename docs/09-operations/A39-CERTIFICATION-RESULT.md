# A39 — resultado da certificação física

**Data:** 2026-07-29 · **Host:** misael-jupiter · BigLinux/Manjaro · kernel
6.18.38-1 · **Sessão:** Wayland/KDE · **Usuário:** misael (uid 1000)

**Veredito: certificação APROVADA.** O ciclo físico
`a39 → a37 → a39` convergiu nas duas direções e a tag `v0.1.0a39` aponta para o
commit exato certificado.

## Identidade certificada

| Dimensão | Valor |
|---|---|
| Release | `0.1.0a39-8e17159d5122` |
| Commit | `8e17159d51222adf2efaa445c19de40999954d8b` |
| Wheel | `steamzero-0.1.0a39-py3-none-any.whl` |
| SHA-256 do wheel | `591ae8a07205192d67cbcd78a072ff07e98d41d6ec11561e27d41e939cc4c161` |
| SHA-256 do lock | `33c7f069591207278a82da262ecbe7a54f161b9d047774c8776f1cb9ab251da0` |
| SHA-256 do instalador estável | `a393d742eb94076fb93b3a81a045dc60ada307d08cdf148bd5b23e5975586857` |
| Run do wheelhouse certificado | `30447201705` |
| Tag | `v0.1.0a39` no mesmo commit |
| CI da tag | `30448986791` (CI) e `30448987083` (QML visual), ambos verdes |

O wheel declarou `sourceTreeState=clean`, `packageVersion=0.1.0a39` e o commit
completo acima. O wheelhouse contém seis dependências, todas conferidas contra o
manifesto; `pip-audit` não encontrou vulnerabilidades.

O rebuild disparado pela tag foi comparado com o conjunto instalado. O wheel
SteamZero, o lock, o `pip-audit` e as seis wheels de dependência são
**byte-idênticos**. O tar do wheelhouse, o SBOM, a proveniência e o arquivo de
checksums não são byte-idênticos por desenho: o manifesto registra outro
`githubRunId`/`generatedAt`, a proveniência troca `refs/heads/main` por
`refs/tags/v0.1.0a39`, e o gerador CycloneDX cria UUIDs, referências e timestamp
novos. A comparação semântica preserva as mesmas oito componentes e versões;
nenhuma diferença de código ou dependência foi encontrada.

## Resultado do ciclo físico

| Verificação | Resultado observado | Estado |
|---|---|---|
| Checksums dos artefatos | 5/5 `OK`; manifesto, lock, wheel e instalador conferidos | ✅ |
| Gates locais | 3.219 testes; Ruff check/format; mypy 188; independence; boundaries | ✅ |
| CI do commit | todos os jobs verdes após rerun isolado do Python 3.12 | ✅ com lacuna G23 |
| Instalação inicial a39 | `ok: true`, `daemonRefresh.state=pending` | ✅ |
| Convergência inicial a39 | 1 tentativa, `restarted=true`, identidade completa | ✅ |
| Idempotência inicial | 0 tentativas, `restarted=false`, mesmo PID | ✅ |
| Rollback a39→a37 | `current` mudou; daemon stale a39 observado antes do gate | ✅ |
| Convergência a37 | 1 tentativa; versão, PID e executável a37 confirmados | ✅ |
| Idempotência a37 | 0 tentativas, `restarted=false`, mesmo PID | ✅ |
| Roll-forward a37→a39 | `current` mudou; daemon stale a37 observado antes do gate | ✅ |
| Convergência final a39 | 1 tentativa; release, commit, PID e executável confirmados | ✅ |
| Idempotência final | 0 tentativas, `restarted=false`, PID `687338` preservado | ✅ |
| CLI / doctor | `0.1.0a39`; doctor `ok`, schema 13, zero operações pendentes | ✅ |
| Socket / serviço | ambos `active`; socket `running` | ✅ |
| Game Mode check | `state=ready`, Steam/Gamescope/runtime/fallback disponíveis | ✅ |
| Host status | manifesto a39 exato e `ok: true` | ✅ |
| Tag | `v0.1.0a39` publicada no SHA certificado | ✅ |

## Prova do fechamento do G18

O gate foi exercitado nos dois estados que antes produziam falso sucesso.
Depois de publicar a a37, mas antes de convergir:

```text
current: /opt/steamzero/releases/0.1.0a37-2aaa01d9d8b6
daemon:  /opt/steamzero/releases/0.1.0a39-8e17159d5122/venv/bin/python3
```

O gerenciador estável permaneceu fora de `current`, com o hash a39, e executou:

```text
converged; restarted=true; attempts=1; daemonVersion=0.1.0a37
converged; restarted=false; attempts=0; mesmo PID
```

No roll-forward, o estado intermediário foi o inverso — `current` a39 e daemon
a37 — e o mesmo gate convergiu para a identidade completa a39 em uma tentativa.
Assim, G18 deixa de ser “coberto sinteticamente” e passa a **fechado por prova
física**.

## Estado final do host

```text
current: /opt/steamzero/releases/0.1.0a39-8e17159d5122
daemon:  /opt/steamzero/releases/0.1.0a39-8e17159d5122/venv/bin/python3
CLI:     0.1.0a39
doctor:  ok
socket:  active
service: active
Game Mode check: ready
```

A a37 continua preservada como rollback. Nenhuma configuração de boot foi
alterada e nenhum reboot foi executado.

## Limites honestos desta certificação

- O check read-only do Game Mode passou, mas não houve reboot nem entrada física
  na sessão nesta rodada.
- A UI Desktop não foi navegada interativamente; esta certificação comprova a
  cadeia de release/daemon e os smokes operacionais, não a jornada visual.
- O primeiro run de CI falhou apenas no Python 3.12 em
  `test_daemon_controls_profile_roundtrip_is_closed_and_reversible`; o mesmo SHA
  passou localmente, no PR, nas outras versões de Python e no rerun do job. A
  causa ainda não foi diagnosticada e está registrada como G23.
- M10–M15, a matriz física completa e G20 permanecem abertos. A aprovação desta
  release não autoriza declarar o produto completo, em produção ou
  `verified-hw`.
