# Pipeline de mídia — leitura somente leitura — 2026-09-22

## Comando

```text
/usr/local/bin/steamzero emulation workspace --json
```

Foi selecionado o objeto `data.platforms[id=switch].areaData.media.mediaPipeline`
da resposta, sem executar qualquer ação `media.*`.

## Estado observado no host

- 15 jogos no contexto Switch;
- 1 mídia customizada, 5 remotas e 9 fallback;
- 1.497 candidatos pendentes;
- `cacheBytes=3168306`;
- último audit global: `2026-07-26T03:24:13.872762+00:00`;
- `screenscraper`: `E-SCRAPE-CREDENTIAL-REJECTED`, categoria `auth`, estado
  persistido `inactive`, 184 falhas consecutivas e 184 requisições;
- há 1 `media.global` em `running`, identificado como stale pelo diagnóstico
  de jobs do host.

O erro do provider chega ao read model como diagnóstico persistido e a UI
possui o cartão de providers degradados; não foi tratado como quota nem como
sucesso vazio. Nenhum job foi iniciado, cancelado, reparado ou repetido.

## Canonical

Os testes de providers, scraping, rede, pipeline, escopo por plataforma,
auditoria e mídia passaram com **223 passed**. Os testes selecionados do
controller/read model passaram com **3 passed**. Em ambos os runs, o state home
real permaneceu idêntico antes e depois.
