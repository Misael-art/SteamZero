# Certificação da 0.1.0a38 no host — operação pendente

**Estado:** artefatos baixados e verificados. **Instalação NÃO executada.**
O host segue na a37; nenhuma tag foi criada.

A execução privilegiada foi bloqueada de forma transitória pelo classificador de
permissões do agente, não por falha de preflight. Todo o resto está pronto, e
este documento existe para que retomar não exija refazer nem adivinhar nenhuma
etapa.

## Identificadores

| campo | valor |
|---|---|
| Release canônica | `0.1.0a38-48f4034dfe36` |
| Commit | `48f4034dfe360083c427ee1991468254eee8ceea` |
| Versão do pacote | `0.1.0a38` |
| Run do Actions | `30413223899` (branch `main`, 8 de 8 jobs verdes) |
| Digest do ZIP | `sha256:4cede5901f09958159d29e59d4980a96c5ba604c4b88b81a5b72fdaa9708613a` |
| **Release de rollback** | `0.1.0a37-2aaa01d9d8b6` |

O ID canônico é `versão-primeiros12doCommit`, produzido por
`_canonical_release()` em `tools/install_host.py`. Um `--release` não canônico é
recusado pelo instalador. **`--release 0.1.0a38` está errado** — foi o erro da
primeira tentativa.

## Artefatos

Em `release-artifacts/a38-48f4034dfe36/` (fora do scratchpad, que é efêmero).
Não versionados: são reproduzíveis do commit mais o run, e os wheels de
terceiros não entram no git.

> **Não apague este diretório antes da prova no host.**
>
> Ele está no `.gitignore`, o que o faz parecer descartável numa limpeza de
> rotina — `git clean -xdf` o remove. Mas até a certificação terminar, ele é
> **material de prova**: é o conjunto exato cujos hashes foram conferidos e que
> será instalado. Regerá-lo do CI produziria bytes iguais, porém a cadeia
> "verifiquei ISTO e instalei ISTO" seria refeita do zero, e uma certificação
> vale pela cadeia, não pelo conteúdo.
>
> Depois da tag e da pre-release, pode ser removido.

```
dist/steamzero-0.1.0a38-py3-none-any.whl
dist/runtime-wheelhouse/            (6 wheels + WHEELHOUSE-MANIFEST.json)
dist/runtime-wheelhouse.tar.zst
requirements-runtime.lock
build/{SHA256SUMS,provenance.json,sbom.cdx.json,pip-audit.json}
VERIFIED-SHA256SUMS
```

### Hashes conferidos

```
edb2b658426ff398d553b799748d255365b983d97048c8c7553016470a96bca2  steamzero-0.1.0a38-py3-none-any.whl
33c7f069591207278a82da262ecbe7a54f161b9d047774c8776f1cb9ab251da0  requirements-runtime.lock
c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309  attrs-26.1.0
d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce  jsonschema-4.26.0
98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe  jsonschema_specifications-2025.9.1
251bf95b67017e27b13d82f5b326234ca62d70f9cf4c2b9032de2358a3b12c7b  pillow-12.3.0
381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231  referencing-0.37.0
dc319e5a1de4b6913aac94bf6a2f9e847371e0a140a43dd4991db1a09bc2d504  rpds_py-2026.6.3
```

Verificado: `sourceCommit` bate, `packageVersion` é `0.1.0a38`, árvore `clean`,
hash do lock confere, wheel confere, as 6 dependências conferem, **nenhum wheel
não declarado**.

Reconferir antes de instalar. Copie o bloco inteiro — as quatro linhas de `test`
não são zelo, são o que faz o comando falhar **antes** de conferir qualquer
arquivo quando o diretório está errado:

```bash
cd /mnt/sdcard/Projects/Port_Steam/release-artifacts/a38-48f4034dfe36

test "$(basename "$PWD")" = "a38-48f4034dfe36"
test -f VERIFIED-SHA256SUMS
test -f dist/steamzero-0.1.0a38-py3-none-any.whl
test -f dist/runtime-wheelhouse/WHEELHOUSE-MANIFEST.json
sha256sum -c VERIFIED-SHA256SUMS
```

Esperado: **10 de 10 `SUCESSO`**. Qualquer `FALHOU` ou "inexistente" interrompe.

### Por que o `cd` é obrigatório

O defeito não é do SHA-256 — é do **contexto de resolução**. Os caminhos dentro
do arquivo são relativos, então a partir da raiz do repositório eles apontam
para `Port_Steam/dist/`, não para os artefatos.

Isso já aconteceu, e o resultado foi pior que uma falha: **7 dos 10 passaram**.
Um `dist/runtime-wheelhouse` de teste local tinha os mesmos wheels — mesmo lock,
mesmo `pip download`, logo os mesmos bytes. Só o manifesto (commit diferente) e o
`.tar.zst` (ausente) denunciaram.

Falso positivo operacional clássico: arquivos **diferentes** com bytes
**iguais**. A verificação parecia ter acontecido e não tinha verificado o
conjunto que será instalado.

Esta é a forma NÃO confiável:

```bash
sha256sum -c release-artifacts/a38-48f4034dfe36/VERIFIED-SHA256SUMS   # ERRADO
```

O `dist/runtime-wheelhouse` local foi removido para não repetir a armadilha,
mas removê-lo é mitigação, não garantia — outro diretório com os mesmos wheels
reproduziria o efeito. A garantia são as linhas de `test`.

## Estado do host antes da operação

```
current           /opt/steamzero/releases/0.1.0a37-2aaa01d9d8b6
steamzero         0.1.0a37
doctor            ok — 4 checks pass, 0 blockers
socket            active
service           inactive  (ativação por socket; é o normal)
releases retidas  66
```

## Instalar

```bash
cd /mnt/sdcard/Projects/Port_Steam
A=/mnt/sdcard/Projects/Port_Steam/release-artifacts/a38-48f4034dfe36

bigsudo /usr/bin/python3 tools/install_host.py install \
  --release 0.1.0a38-48f4034dfe36 \
  --wheel "$A/dist/steamzero-0.1.0a38-py3-none-any.whl" \
  --wheel-sha256 edb2b658426ff398d553b799748d255365b983d97048c8c7553016470a96bca2 \
  --requirements "$A/requirements-runtime.lock" \
  --wheelhouse "$A/dist/runtime-wheelhouse" \
  --source-commit 48f4034dfe360083c427ee1991468254eee8ceea
```

**Não execute** se qualquer um divergir: SHA-256 do wheel, `sourceCommit`,
`packageVersion`, `sourceTreeState`, hash do lock, manifesto do wheelhouse, ID
canônico.

## Convergir o daemon

A instalação **não** está concluída quando `current` muda. Foi aceitar esse
estado como conclusão que produziu a regressão da a37.

```bash
readlink -f /opt/steamzero/current
ls -ld /opt/steamzero/releases/0.1.0a38-48f4034dfe36

steamzero service refresh --expect-release 0.1.0a38-48f4034dfe36 --json
```

Único resultado aceitável: `converged`. Qualquer outro estado — `pending`,
`mismatch`, `timeout`, `restartFailed` — interrompe a certificação.

## Smokes

```bash
steamzero --version
steamzero doctor --json
systemctl --user daemon-reload
systemctl --user enable --now steamzero-core.socket
systemctl --user status steamzero-core.socket --no-pager
steamzero-gamemode-session --check
bigsudo /usr/local/sbin/steamzero-host status
```

## Rollback real e roll-forward

```bash
bigsudo /usr/local/sbin/steamzero-host rollback --release 0.1.0a37-2aaa01d9d8b6
steamzero service refresh --expect-release 0.1.0a37-2aaa01d9d8b6 --json
# repetir os smokes

bigsudo /usr/local/sbin/steamzero-host rollback --release 0.1.0a38-48f4034dfe36
steamzero service refresh --expect-release 0.1.0a38-48f4034dfe36 --json
# repetir os smokes
```

**Não terminar com o host na a37.** O estado final é a38 instalada, a38 ativa,
daemon a38, doctor saudável, rollback e roll-forward comprovados.

## Tag — proibida até a evidência existir

```
a38 instalada → daemon convergido → smokes verdes
→ rollback real a37 → smokes verdes
→ roll-forward a38 → smokes finais verdes
```

Só então, e no SHA testado — nunca no `HEAD` que existir na hora:

```bash
git tag -a v0.1.0a38 48f4034dfe360083c427ee1991468254eee8ceea -m "SteamZero 0.1.0a38"
git push origin v0.1.0a38
```

Se o workflow da tag reconstruir os pacotes, **não** trate como equivalentes:
compare wheel, wheelhouse, manifesto e hashes com o conjunto certificado aqui.

A pre-release é `pre-release`, não release estável.

## Lacuna registrada

`steamzero service status --json` **não existe** — devolve
`E-CLI-USAGE: ação desconhecida`. Não bloqueia esta certificação: a convergência
é observável pelo alvo de `current`, pela resposta estruturada de
`service refresh --expect-release`, pelo estado do socket, pelo `doctor` e pelo
status do gerenciador. Trabalho separado; não acrescentar durante a operação de
release.
