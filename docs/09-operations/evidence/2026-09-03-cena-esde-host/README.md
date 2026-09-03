# Cena ES-DE na release instalada — 2026-09-03

Validação física da release `2.0.0rc1-51f6a5d7db49`, instalada pelo fluxo
governado a partir do commit `51f6a5d7` com CI verde no run `33810860050`.

Toda medição saiu do **pacote instalado** em `/opt/steamzero/current/venv`.

## O que foi exercido

`theme.scene.render` sobre o `org.esde.xmb-menu` que já estava instalado no
host, com `system=snes`, `colorScheme=blue`, `fontSize=medium` e
`aspectRatio=16:10`:

| | |
|---|---|
| Seleções oferecidas | 7 proporções · 39 esquemas de cor · 3 fontes · 20 idiomas · 7 variantes |
| Assets resolvidos | 31, **0 faltando** |
| system | 21 elementos, 2 desenháveis |
| gamelist | 28 elementos, 8 desenháveis |
| menu | 7 elementos, 0 desenháveis |

Os números batem com os medidos no checkout, o que confirma que as duas
correções de causa raiz viajaram para a release.

## Captura

`01-cena-na-release-instalada.png` — o QML renderizado tem sha256
`68fe8f23a934b695…`, idêntico ao de `/opt/steamzero/current`, então os pixels
são do código instalado.

## Proveniência

- `runtime.provenance`: `2.0.0rc1-51f6a5d7db49`
- `service.generation`: daemon na release ativada, não preso na anterior
- Rollback disponível: `2.0.0rc1-603c36fdfaec`

## Um defeito que esta validação revelou

`doctor` passou de 1 para **4 árvores de staging órfãs**. Não é do
renderizador — os diretórios têm ULID de operação e horário das três
instalações de tema deste ciclo.

Causa raiz — e a primeira que registrei aqui estava **errada**. Eu havia escrito
que o staging era preservado para o rollback e ficava vazio em instalação nova.
Lendo o código: é o staging do **download**, cujo `operation_id` é próprio e
diferente do que `install` devolve. `acquire_and_install` apagava o tarball com
`remove_file` e nunca o diretório, então vazava em **toda** instalação, não só
nas novas. As três deste ciclo eram todas novas, o que fez a explicação errada
parecer encaixar.

Corrigido depois, em `SZ-THEME-IMPORT-ESDE-LAYOUT`, com `remove_tree`.

## O que esta evidência NÃO prova

- **A central continua com a aparência dela.** A cena é uma prévia sob demanda;
  nada foi ativado. `GAP-THEME-ESDE-SCENE-NOT-RENDERED` segue aberta.
- `carousel`, `video`, `helpSystem`, `systemStatus`, `boundText` e `badges`
  compilam e não desenham — é o que o rodapé da captura declara.
- A captura vem do QML instalado alimentado pelo estado real, **não de um
  screenshot da sessão gráfica em execução**.
- Nada foi medido em FPS, GPU ou memória.
- `doctor` segue `degraded`, agora por staging órfã (acima) e por
  `boot.direct: unknown`, este último por falta de permissão de inspeção e
  pré-existente.
