# UI-TESTS — testes de UI

| Classe | O que verifica | Automação |
|---|---|---|
| Focus graph | todo elemento interativo alcançável só com D-pad/A/B; sem traps; foco inicial correto; modais devolvem foco | grafo declarado × runtime walker (input sintético) em toda tela — CI |
| Navegação | percursos das jornadas J1–J9 completos por controle | scripts de input sintético |
| Escalas | 100/125/150/TV × 1280×800 e 4K: sem clipping, sem elemento fora da viewport | screenshot diff |
| Glyphs | rodapé correto por tipo de controle (Xbox/PS/Deck/Nintendo-swap) | unit + screenshot |
| Erros | todo código E-* exibível tem template completo (título/impacto/ação) nas 2 línguas | teste de catálogo (render de todos os erros) |
| Progresso | card de job com dados mockados: total desconhecido ⇒ sem porcentagem; cancelamento em duas fases | component tests |
| Acessibilidade | contraste automatizado; labels presentes; redução de movimento respeitada | axe-like + lint de cena |
| Estados vazios/extremos | biblioteca 0 e 10k+; 50 jobs; 20 problemas críticos | fixtures |
| Reconexão | UI mata conexão com daemon e reconecta: re-hidratação sem duplicar eventos | integração |
| Teclado virtual | campo de texto dispara teclado no Game Mode | hardware/manual assistido |

Contrato de teste UI↔core: UI testada contra um **daemon fake** que emite os golden files dos contratos — mudanças de contrato quebram os dois lados visivelmente.
