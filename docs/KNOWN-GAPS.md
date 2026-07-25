# KNOWN-GAPS — lacunas conhecidas e classificadas

| # | Lacuna | Classificação | Mitigação planejada |
|---|---|---|---|
| G1 | `RetroDECK/components` não clonado integralmente (timeout por blobs pesados; 5.516 paths só em `archive_later/`) | **Análise parcial** — modelo compreendido por amostragem (framework + duckstation + es-de) | Clonar com `--filter=blob:none --sparse` em máquina com rede melhor antes da Fase 4 (adapters) |
| G2 | EmuDeck: apenas ramo principal analisado; `android/`, `chimeraOS/`, `darwin/` não auditados em profundidade | **Fora de escopo v1** (alvos não-Linux-desktop) | Registrar; revisitar se houver demanda |
| G3 | PhaseZero lado Windows (`bootstrap-tools.ps1`, ~16k linhas) auditado por documentação (`CLAUDE.md`) e amostragem, não linha a linha | **Análise dirigida** — padrões de resiliência (checkpoint, change manifest, rollback, disk guard) confirmados pela doc interna e testes | O Unified é Linux-first; o lado Windows serve como referência conceitual, não como fonte de código |
| G4 | Nenhum teste dinâmico executado (nenhum script dos quatro projetos foi rodado) | **Restrição da Fase 0** (proibido mutar estado) | Fase 1+: bancada de testes com injeção de falhas |
| G5 | Nenhuma validação em hardware Steam Deck (LCD/OLED/dock) | **Bloqueador para "READY FOR IMPLEMENTATION" pleno** da parte Deck-específica | Matriz §13.4; depende de Q6 (OPEN-QUESTIONS) |
| G6 | Comportamento real do cloud sync EmuDeck (rclone) não exercitado; análise só estática de `cloudServicesManager.sh`/`cloudSyncHealth.sh` | Análise parcial | Prototipagem descartável na Fase 3 |
| G7 | Licenças de assets (ícones, artes, templates de controle) dos projetos de referência não inventariadas item a item | Pendência legal | 11-legal/THIRD-PARTY-NOTICES lista os blocos conhecidos; inventário fino antes de redistribuir qualquer asset |
| G8 | Versões exatas de SteamOS/Steam Client para a matriz de compatibilidade (§11.5) não levantadas | Pendência de pesquisa operacional | Levantar na Fase 2 com hardware real |
| G9 | PhaseZero não tem arquivo LICENSE | Pendência legal (Q2/Q3) | Decisão do titular antes de qualquer reuso formal |
| G10 | Requisitos de acessibilidade (narração/screen reader em Game Mode) sem solução técnica validada em Godot | Pesquisa pendente | ADR-0002 exige protótipo com critérios mensuráveis na Fase 5 |
| G11 | Boot direto/autologin da sessão Game Mode não validado com snapshot+console de recuperação | Bloqueio operacional G7 | Sessão manual SDDM e fallback Plasma existem; não tocar em GRUB/SDDM default antes do protocolo físico |
| G12 | Escala de texto do host (`forceFontDPI` do Plasma) não é honrada pela UI | **Lacuna de acessibilidade** — `reducedMotion` e `highContrast` já vêm do host via `dashboard.accessibility`; a escala não | O QML fixa `font.pixelSize` em ~72 pontos só no `Main.qml`, mais `Emulation.qml` e `SteamGameplay.qml`; aplicar escala exige um helper de tipografia e reexecução dos harnesses de layout/foco. Não foi feito junto do alto contraste para não misturar mudança de layout com mudança de cor às vésperas de uma release |
