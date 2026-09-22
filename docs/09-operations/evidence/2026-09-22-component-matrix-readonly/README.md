# Matriz de componentes — leitura somente leitura — 2026-09-22

## Escopo

Captura do estado publicado pelo host ativo, sem `plan`, `apply`, `repair`,
`rollback` ou restart. A release observada foi `2.0.0rc1-13c933c30ace`.

## Comando

```text
/usr/local/bin/steamzero component list --json
```

## Resultado

O contrato retornou `status=degraded` e `count=36`:

- 33 componentes em `installed`;
- 2 em `missing`: `sunshine` e `vita3k`;
- 1 em `degraded`: `xenia-canary`, com `detail` explícito: o manifesto do
  deployment divergiu sem mudança na fonte fixada.

As origens observadas concordam com os executores: Flatpak/Flatpak, AppImage/
engine, archive/libretro e native/engine. Não houve fallback silencioso nem
mutação no host.

## Contraste com o canonical

A suíte vertical do canonical passou com 169 testes cobrindo jobs, roteamento,
composição, workspace e lifecycle. O runner isolado registrou o state home real
idêntico antes e depois. A prova de lançamento de jogo, acompanhamento da
sessão e retorno ao Launcher permanece física e não foi declarada.
