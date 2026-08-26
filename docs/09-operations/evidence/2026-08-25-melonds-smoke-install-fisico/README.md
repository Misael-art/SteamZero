# Evidência física — install governado baixa e smoke flatpak-info do melonDS (2026-08-25)

Item: `SZ-EMULATION-LONG-OPERATIONS` (fecha também a pendência registrada em
`SZ-EMULATION-ENHANCEMENTS`)
Release validada: **`2.0.0rc1-92d91d631b80`** (`refs/heads/main`), já instalada e
ativa no host — nenhuma nova release foi necessária: as correções
(`b34213d` allowlist de rede na unit do daemon; `c2a1ff1` #100 smoke flatpak-info
do melonDS) já estavam nesta release.
Host: Valve Jupiter (Steam Deck LCD)

## O que esta evidência prova

**P0 do handoff**: o fluxo governado de install VOLTOU A BAIXAR. O job
`component.apply` executou dentro do daemon (unit
`RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK`, daemon ativo
desde 20:12:25, antes de todas as chamadas) e completou com estágio `verified`
em ~48 s (23:24:29 → 23:25:17 UTC). Com a allowlist antiga (`AF_UNIX` apenas) o
mesmo caminho falhava com "Could not resolve hostname".

**Smoke flatpak-info do melonDS**, pendente desde que o adapter revelou contrato
inválido (`--version`): o install físico foi repetido nesta release e
`component verify --id melonds` devolve `verified: true`, com versão implantada
igual à fonte fixada `66752a190012baa6d929936577818db9f70ab178a3651f4bc86a5b02d2d350d7`.
Corroboração externa: `flatpak info --show-commit net.kuribo64.melonDS` devolve
o mesmo commit.

## Natureza dos arquivos

Os três PNGs são **renderizações fiéis de stdout real capturado** da release
instalada, não capturas de tela e não transcrições reescritas. Cada quadro traz
o comando exato acima da saída. Exceção honesta: no quadro 1 do
`03-recuperacao.png`, o erro `E-TX-STALE-PLAN` não é reexecutável hoje (o plano
consumido foi gravado num state home contaminado e descartado); o texto exibido é
o capturado na primeira tentativa, sem edição.

Não há captura de GUI porque instalação/verificação de componente **não tem
superfície QML própria** — a superfície observável desta entrega é o CLI. Uma
janela do launcher apareceria como evidência sem mostrar a entrega.

| Arquivo | Conteúdo |
|---|---|
| `01-baseline.png` | Release ativa, melonds `missing` com alvo fixado, unit com allowlist de rede, daemon na geração nova |
| `02-entrega-funcional.png` | Job `completed` estágio `verified`, status `installed`, verify `verified: true`, commit corroborado pelo flatpak |
| `03-recuperacao.png` | Erro controlado (`E-TX-STALE-PLAN`), dedupe de replay (mesmo job), plano `noop` no alvo, token errado recusado (`E-TX-CONFIRM-REQUIRED`) |

## Resultado medido

```
job            01M0XKTKY900HTWDZX9T9NBSQA  component.apply
estado         completed, stage=verified   (~48 s)
melonds        installed @ 66752a190012b… == alvo fixado
verify         verified=true, repairable=false, exit 0
flatpak info   mesmo commit (sistema, fora do steamzero)
replay         mesma confirmação -> MESMO jobId (dedupe)
noop           plan quando instalado no alvo -> action=noop
token inválido E-TX-CONFIRM-REQUIRED, blocked, nada mutado
```

## Incidente de ambiente registrado (não é defeito do produto)

A primeira tentativa falhou com `E-TX-STALE-PLAN` porque o shell do agente
recebe `XDG_STATE_HOME=/home/misael/.config/ai.opencode.desktop` do harness: o
CLI gravou o plano nesse state home contaminado enquanto o daemon (ambiente
limpo do systemd) lê `/home/misael/.local/state/steamzero`. A transação recusou
sem efeito colateral — comportamento correto. Todas as chamadas de CLI feitas por
agente a partir de shell contaminado devem usar `env -u XDG_STATE_HOME`. O mesmo
contágio explica falsos "plano não encontrado" em sessões anteriores.

## Leitura honesta dos dois `warn` do doctor

`doctor` saiu `degraded` com exit 0 — contrato: só `failed` sai 1. Os `warn`
(`backup.orphan`, `boot.direct: unknown`) são anteriores a esta entrega.

## Reexecução

```bash
env -u XDG_STATE_HOME steamzero component status --id melonds
env -u XDG_STATE_HOME steamzero component verify --id melonds
flatpak info --show-commit net.kuribo64.melonDS
env -u XDG_STATE_HOME steamzero jobs list --limit 5
```

Rollback do componente disponível via `operations rollback-plan` /
`rollback-apply` da operação `01M0XKRWW8J4EFY16VBJ7337RK`; NÃO executado — o
melonDS permanece instalado como estado desejado.
