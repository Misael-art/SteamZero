# A41 — resultado da certificação física

**Data:** 2026-07-29 · **Host:** misael-jupiter · BigLinux/Manjaro · kernel
6.18.38-1-MANJARO · **Sessão:** Wayland/KDE · **Usuário:** misael (uid 1000)

**Veredito: certificação APROVADA.** O ciclo físico
`a41 → a40 → a41` convergiu nas duas direções. A tag `v0.1.0a41` aponta para o
commit exato certificado.

## Identidade certificada

| Dimensão | Valor |
|---|---|
| Release | `0.1.0a41-31b30211ba85` |
| Commit | `31b30211ba85ec9ef60096809616771ff1aef6b5` |
| Wheel | `steamzero-0.1.0a41-py3-none-any.whl` |
| SHA-256 do wheel | `e31e84a92a51f2de64e4ad3c83b021dc53f0050eee595ea9ecb33fd24dfb6d20` |
| SHA-256 do lock | `33c7f069591207278a82da262ecbe7a54f161b9d047774c8776f1cb9ab251da0` |
| SHA-256 do instalador estável | `a393d742eb94076fb93b3a81a045dc60ada307d08cdf148bd5b23e5975586857` |
| Run do wheelhouse | `30502750471` |
| Tag | `v0.1.0a41` no mesmo commit |

O artefato veio do CI do merge em `main`. Checksums publicados, manifesto
externo e interno, lock, seis wheels de dependência, proveniência, SBOM e
auditoria foram conferidos. O manifesto declara `sourceTreeState=clean`, o
commit completo acima e zero vulnerabilidades conhecidas na auditoria
publicada.

## Resultado do ciclo físico

| Verificação | Resultado observado | Estado |
|---|---|---|
| Gates locais | 3.254 testes; Ruff check/format; mypy 189; independence; boundaries | ✅ |
| CI do commit | package/supply-chain, QML, Python 3.11/3.12/3.14 e smokes Ubuntu/Arch/Manjaro verdes | ✅ |
| Instalação inicial a41 | `ok=true`, refresh do daemon declarado `pending` | ✅ |
| Convergência inicial a41 | uma tentativa, `restarted=true`, identidade completa | ✅ |
| Idempotência inicial a41 | zero tentativas, `restarted=false`, mesmo PID | ✅ |
| Rollback a41→a40 | `current` mudou para `0.1.0a40-fa29b46ba796` | ✅ |
| Convergência a40 | uma tentativa, versão, commit e executável a40 confirmados | ✅ |
| Idempotência a40 | zero tentativas, `restarted=false`, PID `621618` preservado | ✅ |
| Doctor na a40 | `ok`, schema 13, zero operações pendentes | ✅ |
| Roll-forward a40→a41 | release existente revalidada e refresh declarado `pending` | ✅ |
| Convergência final a41 | uma tentativa, release e commit completos confirmados | ✅ |
| Idempotência final a41 | zero tentativas, `restarted=false`, PID `624105` preservado | ✅ |
| CLI / doctor | `0.1.0a41`; doctor `ok`, schema 13, zero operações pendentes | ✅ |
| Socket / serviço | ambos `active`; serviço convergido no commit certificado | ✅ |
| Game Mode check | `state=ready`, Steam, Gamescope, runtime e fallback disponíveis | ✅ |
| Laboratório do host | KVM/libvirt e componentes declarados `ready` | ✅ |
| Host status administrativo | manifesto a41 exato, hashes rechecados e `ok=true` | ✅ |
| Tag | `v0.1.0a41` publicada no SHA certificado | ✅ |

## Prova da correção da composição de emulação

No host instalado, o workspace de Nintendo Switch deixou de cair na composição
mínima que aparecia na captura da a40. A leitura real publicou:

- 15 jogos;
- keys próprias `rev21` e firmware `22.5.0`, ambos com estado `ok`;
- Eden, Citron e Ryubing com versão-alvo, especialidade e ação `Instalar`;
- uma ação por card, em vez de `Ações (0)`;
- como único bloqueador de prontidão, a ausência honesta de um emulador
  instalado.

O estado geral continua `unverified` por esse último motivo. Isso é verdade do
host, não regressão da bridge HTTP nem falsa pendência de keys. A UI da a41
abriu fisicamente na rota Emulação, publicou Nintendo Switch com 35% de
prontidão e permaneceu estável durante a inspeção.

## Estado final do host

```text
current: /opt/steamzero/releases/0.1.0a41-31b30211ba85
daemon:  0.1.0a41-31b30211ba85
commit:  31b30211ba85ec9ef60096809616771ff1aef6b5
CLI:     0.1.0a41
doctor:  ok
socket:  active
service: active
Game Mode check: ready
```

A a40 permanece preservada como rollback. Nenhuma configuração de boot foi
alterada, nenhum emulador foi instalado e nenhum reboot foi executado.

## Limites honestos desta certificação

- O check read-only do Game Mode passou, mas não houve reboot nem entrada
  física na sessão nesta rodada.
- O estado de boot privilegiado não foi reautorizado; o check sem privilégio
  reportou `unknown` por permissão, enquanto a cadeia Game Mode reportou
  `ready`.
- A UI abriu e a rota de Emulação foi inspecionada, mas a navegação completa
  por teclado/gamepad não foi certificada porque o backend de automação do host
  recusou entrada com a versão instalada do `ydotool`.
- Nenhum emulador Switch está instalado. Portanto, jogos permanecem não
  lançáveis e a prontidão da plataforma continua em 35%.
- Esta aprovação certifica release, rollback, convergência e a composição
  corrigida. Não declara o produto completo, em produção ou `verified-hw`.
