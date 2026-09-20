# AURA — ingestão local de mídia rica

## Objetivo

Fechar a ponte entre o acervo de arte local do RetroFE e o read model do AURA
Launcher sem transformar nome de arquivo em identidade implícita. A ingestão
preserva o `gameId` da biblioteca canônica, deriva o `platformId` da coleção
conhecida e publica masters endereçados por hash.

## Fluxo

```text
RetroFE collections/
  -> coleção conhecida + medium_artwork/
  -> papel allowlisted (cover/screentitle, fanart, screenshot, video)
  -> normalização de título sem acentos/caixa
  -> match único dentro da plataforma
  -> plano auditável
  -> apply opcional, sem sobrescrever por padrão
  -> masters/<platform>/<kind>/<sha>.<ext> + assignments-v1.json
```

O plano é somente leitura. Symlinks, diretórios de usuário (`Main`), extensões
não suportadas, títulos sem match e empates ficam fora do apply. Um registro que
já tem o papel solicitado é preservado, a menos que o operador passe `--replace`.
Nenhuma origem é removida e nenhum download é executado.

## Uso

```text
PYTHONPATH=src python tools/import_retrofe_media.py \
  --library ~/.local/share/steamzero/emulation-library-cache-v1.json \
  --source-root /home/misael/emulation/frontend/RetroFE/collections \
  --media-root ~/.local/share/steamzero/media
```

O comando acima só imprime o plano. Para publicar em uma raiz de mídia já
revisada, repetir com `--apply`; `--replace` é uma decisão explícita e não faz
parte do caminho normal.

## Varredura do acervo real — 2026-09-20

Com a biblioteca canônica e o acervo RetroFE do host:

| Decisão | Quantidade |
| --- | ---: |
| accepted | 79 |
| ambiguous / revisão humana | 3 |
| unmatched / sem palpite seguro | 165 |

O apply foi exercitado em uma raiz temporária: 79 masters publicados, 0 falhas,
0 sobrescritas. Os aceitos incluíram 77 capas NES e 2 fanarts PlayStation. A
janela fullscreen instalada ainda não foi alterada: esta prova de ingestão não
é uma prova física da release nem substitui a captura PNG pós-instalação.

O próximo passo físico é promover esta mudança por release governada, aplicar o
plano na raiz de mídia do usuário e capturar a home/detalhe com fanart e capa
real. A autenticação interativa do `pkexec` continua sendo necessária para a
instalação da release; nenhuma mutação privilegiada foi feita por esta frente.
