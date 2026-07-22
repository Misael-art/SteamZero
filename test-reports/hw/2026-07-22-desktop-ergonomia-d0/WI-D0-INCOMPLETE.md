# WI-D0 — evidência física parcial (não concluído)

Data: 2026-07-22. Sessão observada: Wayland, Plasma/KWin, usuário `misael`.
Nenhum perfil, escala, regra de janela ou configuração persistente foi alterado.

## Base verificada

- Base da branch: `main@74f29845986df906ee7824b4a467ddf2b1de9828`.
- `STEAM-SESSION-ROADMAP.md`: SHA-256
  `a228e5aee0f134a3c80af9c7f66166a0fee52dcea6a3bde1bfddf3d7a30dc1f9`.
- `EMULATOR-PORTING-DIRECTIVE.md` foi somente lido no caminho absoluto autorizado;
  SHA-256 `3283d1b21dd7bc5bd8e5a7ae84fd202908ce8afb25ce42263553b886192130b9`.

## Medição da tela

| Físico | Lógico observado | Escala | Orientação | Área de janela observada |
|---|---:|---:|---|---:|
| eDP-1, 800×1280 @ 60 Hz | 949×593 | 1,35 | retrato (KScreen rotation 8) | 948×553 |

O orçamento normativo de 592 px lógicos é compatível com a geometria observada;
a janela maximizada perde cerca de 40 px lógicos para o shell.

## Capturas aceitas

| Caso | Aplicativo/versão | Evidência | Observação | Prioridade |
|---|---|---|---|---|
| Editor | Kate 26.04.3 | `04-editor-kate.png` | Janela maximizada, documento vazio e sem conteúdo pessoal. A área útil é 948×553 lógicos; menus e barra de ferramentas usam densidade pequena para toque. | P2 |

Esta imagem é uma captura atual da tela física, 1280×800, realizada por Spectacle
sem alterar a sessão. Toolkit: Qt/KDE. A superfície cabe na altura útil, não mostra
overflow; a operação por toque não foi exercitada, portanto a prioridade P2 trata
somente a densidade visual observável.

## Capturas rejeitadas e recaptura necessária

| Caso | Estado | Motivo | Próxima evidência exigida |
|---|---|---|---|
| Gerenciador de arquivos — Dolphin 26.04.3 | Inconclusivo; arquivo removido do commit | A janela não estava isolada/maximizada e a captura expunha outra janela ao fundo; não prova falha do Dolphin. | Diretório temporário neutro, janela maximizada, sem outra janela visível, conteúdo suficiente para avaliar overflow e scroll. |
| Leitor de PDF — Okular 26.04.3 | Rejeitado por privacidade; arquivo removido do commit | Nome de documento e conteúdo potencialmente pessoal visíveis. | PDF sintético ou público, com texto e imagem neutros. |

## Estado do WI

**Não concluído.** Faltam nove evidências físicas obrigatórias: gerenciador de
arquivos recapturado, navegador, terminal, suíte de escritório, leitor de PDF e
abrir/salvar GTK e Qt. As tentativas de abertura read-only de Firefox, Konsole e
LibreOffice não produziram uma janela capturável nesta sessão. Uma janela de
navegador e um terminal existentes foram rejeitados porque expunham conteúdo pessoal;
as imagens foram removidas. Não foi instalado nenhum aplicativo nem foram usados mocks.

Enquanto as nove capturas não existirem, não há tabela decisória final, ranking
completo, schema `desktop-ergonomics-v1` normativo, alteração de produto, entrada
no `docs/WORKLOG.md` ou conclusão de D0.
