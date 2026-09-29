# 20 — bateria de mutações do formatador e da medida tipada

`20-bateria-de-mutacoes.log` guarda a saída corrida por corrida. Script:
`/tmp/ux04_mutation_battery.py` (`sha256` prefixo `c5928d5079d4e8d9`, gravado no
cabeçalho do log). Ele copia o arquivo, aplica **uma** substituição, roda a
verificação, restaura e confere o `sha256` original — a árvore é verificada ao
final do log (`árvore restaurada: True (4 arquivos conferidos por sha256)`).

Veredito: **8/8 mutações mortas**, cada uma citando o requisito que violou.

| mutação | o que quebra | morto por |
|---|---|---|
| M1 | rótulo decimal (`MB`/`GB`) com divisor 1024 | gate — "o rótulo tem de dizer IEC" |
| M2 | limiar de andar decimal sobre divisor binário | gate — "mantissa abaixo de 1" |
| M3 | separador estrangeiro (`toFixed(2)`) | gate — "separador de milhar/decimal estrangeiro" |
| M4 | ausência vira `0 B` | gate — "dado não medido tem representação própria (traço)" |
| M5 | uma página volta a formatar sozinha | gate — "uma única grandeza não pode ter várias leituras" |
| M6 | cartão para de publicar `metricBytes` | `test_grandeza_do_bucket_viaja_como_inteiro_e_nao_como_texto` |
| M7 | grandeza volta para a prosa do volume | `test_nenhum_cartao_escreve_grandeza_na_prosa` |
| M8 | schema aceita string em `metricBytes` | `test_schema_valida_o_tipo_da_grandeza` |

## Dois falsos resultados encontrados durante a própria bateria

Registrados porque sem eles a bateria diria mais do que prova.

1. **M2 morreu pelo motivo errado na primeira rodada.** O script rodava o harness
   com um ambiente reduzido (`env` trocado, não mesclado). Sem `HOME`/locale, o
   `Qt.locale()` do harness caía em `C`, e `testLocalizado` falhava **para qualquer
   mutação — inclusive para o código certo**. Corrigido para `{**os.environ, **GATE_ENV}`,
   como faz o gate real (`tests/integration/test_qml_handheld_offscreen.py:34`).
2. **M3 sobreviveu porque era inerte.** `.toLocaleString(Qt.locale())` aparece
   também num comentário de documentação do `sizes.js`, e a substituição atingia a
   primeira ocorrência — o código não mudava. O script agora rejeita alvo com
   contagem ≠ 1 (`mutação ambígua ou inexistente`) em vez de reportar sobrevivência.

Além disso, o grupo **normalização** foi acrescentado ao harness *para* M2 ter
motivo legítimo de morrer: 1.000.000 B lido como `0,95 MiB` é o sintoma de escolher
andar por limiar decimal e dividir por potência de 1024. Sem esse grupo, M2 era um
mutante equivalente ao conjunto de valores que o harness usava.
