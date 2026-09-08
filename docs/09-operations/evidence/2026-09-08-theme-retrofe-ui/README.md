# Importação RetroFE — entrada visual e assets

Esta evidência acompanha a entrega da entrada RetroFE na área Temas.

Estado do ciclo: release instalada e validada no host sem reboot, logout ou
encerramento da sessão KDE.

Provas automatizadas deste ciclo:

- `tests/unit/test_theme_import_retrofe.py` — inspeção sem escrita, IR, licença,
  overwrite, symlink, limite e cópia para o store por conteúdo.
- `tests/qml/check_theme_editor_import.qml` — entrada, inspeção e publicação
  RetroFE pelo contrato QML, sem ativação automática.
- `tests/integration/test_retrofe_vertical_slice.py` — 53 testes verdes.

Evidência física:

- `02-entrega-funcional.png` — janela QML carregada do `/opt/steamzero/current`
  após a instalação, mostrando a entrada **Importar cena RetroFE**, inspeção do
  layout, relatório de degradação, assets prontos e a regra de não ativação
  automática.
- Release ativa: `2.0.0rc1-435f9108eeb7`, source commit
  `435f9108eeb7b4adf1d84b87d9d2e70c692eead1`.
- Rollback disponível: `2.0.0rc1-b09908a58261`.

A convergência inicial reiniciou somente o daemon do SteamZero, conforme o
fluxo governado; não houve reinício do host nem encerramento da sessão KDE.
`steamzero doctor --json` terminou com `ok: true`, sem operações pendentes; os
avisos preexistentes de staging órfão e inspeção de boot permanecem explícitos.

Nenhum token, segredo ou dado pessoal deve ser persistido nas capturas do host.
