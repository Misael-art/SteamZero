# Catálogo de temas na release instalada — 2026-09-03

Validação física da release `2.0.0rc1-603c36fdfaec` no host (Steam Deck LCD),
instalada pelo fluxo governado a partir do commit `603c36fd` com CI verde no run
`33796970755`.

Toda medição abaixo saiu do **pacote instalado** em
`/opt/steamzero/current/venv`, não do checkout.

## O ciclo executado

| Passo | Resultado observado |
|---|---|
| Listar | 5 curados com licença e crédito, 4 excluídos com motivo, store em 0 B |
| Instalar `org.esde.iconic` | 1906 assets, 143,1 MB, 44,7s |
| Instalar `org.esde.playstation-x` | 1552 assets, 303,4 MB, 72,4s |
| `gc` com os dois donos | 0 órfãos |
| Desinstalar `playstation-x` | store **inalterado**: 3030 blobs / 446,5 MB |
| `gc` (prévia) | 1456 órfãos, 303,4 MB |
| `gc --apply` | recuperou 303,4 MB; sobraram os 1574 blobs do iconic |
| `gc` de novo | 0 órfãos |
| `store.verify` | `ok: True, missing: 0, corrupt: 0` (re-hasheia os blobs) |

Remover um tema **não** apagou arte, e o vizinho sobreviveu íntegro: 1574
digests referenciados pelo manifesto do iconic, **0 referências quebradas**.

## O número que corrige a premissa

O pedido original partia de que temas compartilham assets entre si. Medido no
host, isso quase não se sustenta:

| Origem da economia | iconic | playstation-x |
|---|---|---|
| Repetição **interna** ao pacote | 52,2 MB | 27,1 MB |
| Compartilhado com **outro tema** | 0 B (nada instalado) | **18,7 KB** em 303 MB |

18,7 KB é 0,006% do pacote. O ganho real do store está na dedup interna e na
atualização de um mesmo tema (94% reaproveitado, medido antes).

É exatamente a distinção que um contador único escondia: antes de separar
`bytesRepeatedInPackage` de `bytesSharedWithInstalled`, esta instalação teria
reportado "52 MB deduplicados entre temas" — falso, porque não havia outro tema.

## Captura

`01-catalogo-no-host.png` — o painel com o estado real do host: 136,5 MB em 1574
arquivos, Iconic com selo `Instalado` e `Reinstalar`/`Remover`, os outros em
`Instalar`.

O QML renderizado tem sha256 `6833fa93750cd2…` idêntico ao de
`/opt/steamzero/current`, então os pixels são do código instalado.

### Um defeito que a captura pegou

A primeira tentativa saiu com spinner e **"0 B em 0 arquivos"**, porque o
`XMLHttpRequest` para `file://` falhou silenciosamente e o painel nunca recebeu
os dados. O host tinha 143 MB instalados: publicar aquela imagem teria afirmado
o oposto do estado real. O estado passou a ser embutido no harness.

## O que esta evidência NÃO prova

- **Nenhuma cena ES-DE foi renderizada.** Instalar um tema continua sem mudar a
  aparência da central; `activated: false` é deliberado.
  `GAP-THEME-ESDE-SCENE-NOT-RENDERED` segue aberta.
- A captura vem do QML instalado alimentado pelo estado real, **não de um
  screenshot da sessão gráfica em execução**. Os cliques foram provados em
  `qmltestrunner`, e as rotas foram exercidas contra o pacote instalado; o que
  falta é a jornada ponta a ponta dentro da sessão.
- Nada foi medido em FPS, GPU ou memória.
- `doctor` segue `degraded` por dois avisos **pré-existentes** (uma árvore de
  staging órfã e `boot.direct: unknown` por falta de permissão de inspeção).
  Nenhum dos dois foi introduzido aqui.

## Rollback

`2.0.0rc1-e571577faeda` continua disponível.
