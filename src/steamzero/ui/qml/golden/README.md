# Golden screenshots da UI Desktop

Capturas inspecionadas manualmente em Qt 6.11.1 com renderização software/offscreen.
Os dados são fixtures sintéticas no formato do read model existente; nenhum fallback
mockado foi adicionado ao runtime.

| Arquivo | Composição exercitada |
|---|---|
| `deck-overview-1280x800.png` | rail portátil, prontidão contextual e footer compacto |
| `deck-navigation-icons-1280x800.png` | rail portátil com glifos modernos, distintos e sem iniciais textuais |
| `deck-accessibility-menu-1280x800.png` | preferências visuais acessíveis no rail portátil |
| `deck-alert-expanded-1280x800.png` | alerta global novo ou bloqueante, com explicação e ação |
| `deck-alert-compact-1280x800.png` | alerta reconhecido sem duplicar o diagnóstico completo |
| `deck-accessibility-menu-1280x800.png` | preferências visuais ajustáveis dentro do app |
| `deck-accessibility-150-1280x800.png` | reflow com tipografia a 150% e rail preservado |
| `deck-emulators-data-1280x800.png` | lista com estados reais variáveis e ações preservadas |
| `deck-emulators-empty-1280x800.png` | filtro `Instalados 0`, seleção nula e empty state |
| `deck-emulator-drawer-1280x800.png` | inspector em drawer sem perder lista/contexto |
| `deck-error-feedback-1280x800.png` | erro traduzido em impacto e ação de diagnóstico |
| `deck-loading-1280x800.png` | carregamento indeterminado, bloqueio seguro e contexto preservado |
| `deck-navigation-icons-1280x800.png` | rail compacto com ícones vetoriais próprios e foco ciano |
| `deck-high-contrast-1280x800.png` | tokens de alto contraste sem filtro visual destrutivo |
| `deck-section-menu-1280x800.png` | lista semântica, foco visível, dots e footer contextual |
| `fullhd-steam-1920x1080.png` | lista e inspector Steam na composição padrão |
| `fullhd-profiles-1920x1080.png` | grid de perfis e estados recomendado/desejado/aplicado |
| `fullhd-sync-data-1920x1080.png` | fila com pendentes, conflitos preservados e concluídos |
| `fullhd-system-conflict-1920x1080.png` | diagnóstico e conflito sem banner explicativo duplicado |
| `ultrawide-sync-empty-2560x1080.png` | largura limitada e empty state de sincronização |
| `desktop-4k-overview-3840x2160.png` | composição lógica de desktop em escala 200% |
| `tv-4k-overview-3840x2160.png` | preset TV em escala 200%, alvos e tipografia ampliados |

As capturas 4K renderizam a composição lógica em 1920×1080 e preservam o resultado em
3840×2160, reproduzindo escala de sistema de 200% sem tratar pixels físicos como espaço
lógico adicional.

Rótulo: `verified-dev`. As imagens não comprovam Wayland/X11, controle, touch ou
hardware físico; esses itens permanecem explicitamente não verificados.
