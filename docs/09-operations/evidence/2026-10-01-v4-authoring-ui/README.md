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
Hashes: `SHA256SUMS`.

## Roteiro curto (release candidata, quando existir)
1. **Sucesso.** Temas → duplicar `org.steamzero.asset-recipes-demo` → no Studio: adicionar efeito `shadow` na pilha `focusedCover`, mudar `blur` para 20, mover para cima; keyframe `focused` `scale=1.2`; criar timeline `entrada` + clip; ligar `previewTitles.text` ao metadado `genre`. Desfazer/Refazer devem seguir cada passo; "Não salvo" acompanha o histórico.
2. **Salvar/reabrir.** Salvar, Fechar, reabrir o tema na lista: os valores permanecem (inclusive o binding).
3. **Exportar/importar.** Exportar o `.zip`; importar de novo exige "como cópia" (id novo, "(cópia)"); o original fica intacto.
4. **Erro e recuperação.** Digitar `9999` em `blur radius`: aparece mensagem acionável, o campo volta ao valor declarado e o histórico não ganha passo. Num tema sem layouts o inspetor de bindings explica como obter um tema com layouts.
5. **Viewport compacto** (janela estreita): os três inspetores continuam alcançáveis rolando a coluna esquerda.
6. **Teclado/gamepad/seletor nativo:** não exercitados por este pacote; registrar como "assistido" se o AT-SPI não responder (limitação do instrumento, não do produto).
Consumidor: tema da central (ThemeBridge) para tokens; cena da Engine (`SceneEsdeView`) para ES-DE/RetroFE. Launcher/AURA Cinema **não** consomem cenas importadas neste pacote.
Versão: preencher com a release instalada (`2.0.0rc1-5715d7962691` NÃO contém estas mudanças). Rollback preservado: `2.0.0rc1-e2af2562ebba`.
