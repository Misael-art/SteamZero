# 24 — matriz de locales: o gate pino um fuso e ficou vermelho no CI

## O que foi medido

O harness `tests/qml/check_storage_units.qml`, executado diretamente (mesmo
ambiente do gate: `QT_QPA_PLATFORM=offscreen`, `QT_LOGGING_RULES=""`,
`QT_FORCE_STDERR_LOGGING=1`, `QML_DISABLE_DISK_CACHE=1`) sob cinco contextos de
locale. Script: `24-matriz-de-locales.py` (`sha256` `de8c7623ff1a5392`, `ROOT` =
diretório de trabalho); logs `24-matriz-de-locales-antes.log`
(`sha256` `8f1cfc3eceedc7df`) e `24-matriz-de-locales-depois.log`
(`sha256` `4ab6c4d095a68172`).

| `LC_ALL` | antes (harness `bf437d2b…`) | depois (harness `919ab433…`) |
|---|---|---|
| `C` | **6 falhas de 109**, rc=1 | 145 ok, rc=0 |
| `C.UTF-8` | **6 falhas de 109**, rc=1 | 145 ok, rc=0 |
| sem `LANG`/`LC_ALL` (host) | 109 ok, rc=0 | 145 ok, rc=0 |
| `en_US.UTF-8` | **6 falhas de 109**, rc=1 | 145 ok, rc=0 |
| `pt_BR.UTF-8` | 109 ok, rc=0 | 145 ok, rc=0 |

## Causa

Não era a produção. `src/steamzero/ui/qml/sizes.js:50` formata com
`toLocaleString(Qt.locale())`, i.e. delega ao locale em vigor — que é o contrato.
O defeito estava no **gate**: linha 27 do harness declarava
`property var locale: Qt.locale("pt_BR")` e comparava as saídas contra esse pino
(quatro checagens de separador e três literais de frase inteira, dois dos quais
com `,` cravado). Na máquina do autor (pt_BR) o gate passava; na imagem do gate
visual, que fixa `LC_ALL=C.UTF-8` (`ci/qml-visual/Containerfile:58-59`) com o
mesmo locale trancado em `environment.lock.json:26`, ele reprovaria. Um gate que
só vale no fuso de quem o escreve não é gate — e foi assim que a UX-04 chegou ao
checkpoint com "verde" local.
## Medição complementar (sonda isolada)

`(1.5).toLocaleString(...)` no Qt 6.11.2 deste host, medido com
`probe` de `Window` (`qml6` offscreen):

| contexto | `Qt.locale().name` | sem argumento | `Qt.locale()` | `Qt.locale("pt_BR")` | `"pt-BR"` | `toFixed(2)` |
|---|---|---|---|---|---|---|
| `LC_ALL=C.UTF-8` | `C` | `1.5` | `1.50` | `1,50` | `1.5` | `1.50` |
| `LC_ALL=pt_BR.UTF-8` | `pt_BR` | `1,5` | `1,50` | `1,50` | `1.5` | `1.50` |

Três consequências para o desenho do gate:

1. o argumento `QLocale` **é honrado** (linhas 3 e 4), então "fixar um locale na
   produção" é defeito possível e mutável — o pino novo precisa pegá-lo;
2. string BCP-47 **não** é honrada (coluna 5), então a forma delegada é
   `toLocaleString(Qt.locale())` e não `toLocaleString("pt-BR")`;
3. `toFixed` **não** localiza (coluna 6), que é o outro mutante da mesma classe.

Sobre propagação: Qt resolve o nome por conta própria — `fr_FR.UTF-8` e
`de_DE.ISO-8859-1` são honrados sem dados do glibc (medido), e um nome inválido
(`xx_YY.UTF-8`) cai em `C`. Por isso a matriz não depende da imagem do CI ter o
locale `pt_BR` instalado; e por isso o teste também exige que o harness
**informe** o locale que usou, para o caso de um dia depender.

## O que mudou

* `property var locale: Qt.locale()` (o em vigor) e
  `property var separador` derivado de `(1.5).toLocaleString(locale)`, uma
  referência que não passa pelo formatador de armazenamento.
* O harness passou a publicar `check_storage_units locale=<nome> decimal="<sep>"`
  antes do veredito — é a âncora de não vacuidade da matriz.
* Os dois literais de frase inteira viraram expectativa **composta** a partir da
  leitura do formatador (`"12 arquivo(s), " + formatar(main, 1073741824) + …`),
  que é o requisito real: prosa e cartão dizem a mesma leitura.
* `testNadaSome` deixou de procurar o literal `"0.0"` (surdos num locale com
  vírgula) e passou a procurar `"0" + separador`.
* Novo `tests/integration/test_storage_units_locale_matrix.py` (`sha256`
  `6520c53faba868c7`): verde sob `C.UTF-8` **e** `pt_BR.UTF-8`, locale reportado
  conferido, e os dois separadores têm de diferir.

Contagem: 109 → **145** checagens (oráculo de grandeza da evidência 25 acrescenta
36). Verde nos cinco contextos.
