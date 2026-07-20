# Manutenção e mídia da Steam

## Limpeza que realmente libera espaço

A aba **Steam → Biblioteca** inventaria somente dois conjuntos allowlisted:

- shader cache regenerável em `steamapps/shadercache/<AppID>`;
- crash dumps regulares quando a limpeza é global.

Compatdata/Proton, saves, conteúdo instalado, Workshop e downloads ficam fora do scanner e
da operação. A Steam deve estar fechada no plan e no apply. O plano expira em 15 minutos,
vincula fingerprints e exige `confirmToken` mais a frase `LIBERAR ESPACO`.

A remoção primeiro renomeia cada candidato para um tombstone no mesmo filesystem e depois
o apaga. Se o processo cair entre as etapas, `recover` conclui a remoção; cache alterado é
preservado e produz `E-TX-STALE-PLAN`. A garantia é deliberadamente `G-NONE` depois da
confirmação destrutiva, pois manter uma cópia no mesmo disco não liberaria espaço.

## Pacote local de mídia

Uma pasta de pacote pode conter ao menos um destes arquivos, com até 16 MiB cada:

```text
grid.png|jpg|webp
portrait.png|jpg|webp
hero.png|jpg|webp
logo.png|jpg|webp
```

Magic bytes e symlinks são validados. Conta e AppID são explícitos; o destino permanece em
`userdata/<conta>/config/grid`. Variantes anteriores da mesma arte são removidas dentro da
mesma transação, mas ficam no backup verificado. Apply e rollback exigem a Steam fechada e
a garantia é `G-FULL`, byte-idêntica. O adapter é local-only: não baixa arte, não recebe
credenciais e não depende de scraper ou PhaseZero.
