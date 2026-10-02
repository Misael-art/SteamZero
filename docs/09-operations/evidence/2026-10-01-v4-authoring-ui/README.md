# V4 — autoria pela UI: capturas e roteiro para B_VISUAL

**Nível de prova:** teste QML automatizado com **eventos Qt (mouseClick/keyClick)** sobre os controles reais do
`ThemeEditorPanel` contra o `DesktopControlServer` real (dashboard real, dados em diretório temporário), em
plataforma `offscreen`/renderer software. **Não** é prova física: sem input real de teclado/gamepad/portal,
sem release instalada, sem AT-SPI.

Branch `codex/v1-v3-theme-journey-2026-10-01`; teste: `tests/integration/test_theme_authoring_e2e.py`
(harness `tests/qml/check_theme_authoring_e2e.qml`). Capturas geradas com `SZ_CAPTURE_DIR=<dir>`.

## Capturas (dados sintéticos)
| Arquivo | O que mostra |
|---|---|
| `01-studio-efeitos-movimento.png` | Inspetores de efeitos (cartões com parâmetros) e de movimento; 1100x900 |
| `02-studio-compacto.png` | Viewport 640x560 (layout compacto): inspetores seguem alcançáveis por rolagem |
| `03-studio-binding.png` | Binding `text ← item.genre` ligado e listado; timeline/clips acima |
| `04-studio-compact-movimento.png` | Viewport 640x560 após rolar até o inspetor de movimento; `Adicionar clip` cabe inteiro no viewport |
Hashes: `SHA256SUMS`.

## Correção verificada em 2026-10-02

O gate visual do CI no run `36952440268` encontrou controles do inspetor fora do
viewport horizontal no Qt 6.11.2: em 1100x900 `keyframe_scale` começava em x=394
num `Flickable` de 380 px; em 640x560 o centro de `motionClipAdd` ficava além do
limite de 280 px. Os `Flow` internos herdavam a largura implícita dos filhos.
Agora o cartão limita a largura ao `ScrollView.availableWidth`, e os `Flow`
quebram na largura do inspetor. O harness também verifica que o alvo inteiro está
na viewport antes de enviar mouse/teclado.

Reprodução e correção foram executadas no container pinado pelo CI
(`ghcr.io/misael-art/steamzero-qml-visual@sha256:8b832ec124ae72aa59a4de3b5c00ccf3f03b41a7e688f45c10daf767290041cd`,
Qt 6.11.2, Python 3.14.6, software/offscreen): antes, `1 failed`; depois, o teste
de autoria passou (`1 passed`). No host BigLinux, a mesma jornada passou e gerou
as capturas 01–04. O guard de estado do runner registrou igualdade antes/depois.
Isso prova eventos Qt no harness QML e persistência no diretório temporário, não
input físico nem execução pela release instalada.

Limite de captura: o container visual reproduz a geometria, mas a imagem dele
mostra glifos ausentes (quadrados) no stack de fontes disponível. Por isso a
captura 04 é do renderer software local do host, legível e ligada ao mesmo teste;
os screenshots do container não são usados como aprovação visual.

## Gates locais do checkpoint

Na árvore congelada após a correção do viewport, correspondente ao commit
funcional `57d18663f63f25fb655cce1b6dee40e56b592dc4`, os gates locais terminaram
em:

- `.venv/bin/python tools/run_tests_isolated.py tests -q`: **6557 passed, 47 skipped** em 2599,72 s; o guard registrou o mesmo estado real antes/depois (`files=12818`, `directories=2068`, `bytes=1372818509`). Os skips são contratos condicionados a Flatpak/core e fixtures `reference/` não versionadas.
- `.venv/bin/ruff check src tools tests`: aprovado.
- `.venv/bin/ruff format --check src tools tests`: 689 arquivos formatados.
- `.venv/bin/mypy src`: sem erros, 299 arquivos.
- `make independence boundaries`: independência e fronteiras aprovadas.
- `make status-check`: aprovado depois de renovar os digests dos itens que incluem a superfície QML compartilhada.
- `git diff --check`: aprovado.

O run remoto `36952440268` pertence ao SHA anterior `ee72df66` e falhou no gate
visual QML por geometria fora do viewport. A correção local passou no container
visual pinado; o CI do novo SHA só será criado depois do push. Nenhum pacote foi
instalado: a release ativa continua `2.0.0rc1-5715d7962691`.

## Roteiro curto (release candidata, quando existir)
1. **Sucesso.** Temas → duplicar `org.steamzero.asset-recipes-demo` → no Studio: adicionar efeito `shadow` na pilha `focusedCover`, mudar `blur` para 20, mover para cima; keyframe `focused` `scale=1.2`; criar timeline `entrada` + clip; ligar `previewTitles.text` ao metadado `genre`. Desfazer/Refazer devem seguir cada passo; "Não salvo" acompanha o histórico.
2. **Salvar/reabrir.** Salvar, Fechar, reabrir o tema na lista: os valores permanecem (inclusive o binding).
3. **Exportar/importar.** Exportar o `.zip`; importar de novo exige "como cópia" (id novo, "(cópia)"); o original fica intacto.
4. **Erro e recuperação.** Digitar `9999` em `blur radius`: aparece mensagem acionável, o campo volta ao valor declarado e o histórico não ganha passo. Num tema sem layouts o inspetor de bindings explica como obter um tema com layouts.
5. **Viewport compacto** (janela estreita): os três inspetores continuam alcançáveis rolando a coluna esquerda.
6. **Teclado/gamepad/seletor nativo:** não exercitados por este pacote; registrar como "assistido" se o AT-SPI não responder (limitação do instrumento, não do produto).
Consumidor: tema da central (ThemeBridge) para tokens; cena da Engine (`SceneEsdeView`) para ES-DE/RetroFE. Launcher/AURA Cinema **não** consomem cenas importadas neste pacote.
Versão: preencher com a release instalada (`2.0.0rc1-5715d7962691` NÃO contém estas mudanças). Rollback preservado: `2.0.0rc1-e2af2562ebba`.
