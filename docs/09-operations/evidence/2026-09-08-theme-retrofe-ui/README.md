# Importação RetroFE — entrada visual e assets

Esta evidência acompanha a entrega da entrada RetroFE na área Temas.

Estado do ciclo: implementação local concluída; release, instalação e captura
funcional no host ainda serão registradas após o merge pelos canais governados.

Provas automatizadas deste ciclo:

- `tests/unit/test_theme_import_retrofe.py` — inspeção sem escrita, IR, licença,
  overwrite, symlink, limite e cópia para o store por conteúdo.
- `tests/qml/check_theme_editor_import.qml` — entrada, inspeção e publicação
  RetroFE pelo contrato QML, sem ativação automática.
- `tests/integration/test_retrofe_vertical_slice.py` — 53 testes verdes.

Nenhum token, segredo ou dado pessoal deve ser persistido nas capturas do host.
