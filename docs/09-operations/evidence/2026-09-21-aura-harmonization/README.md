# AURA — prova física da release 2.0.0rc1-13c933c30ace

Esta sessão valida a promoção governada do commit
`13c933c30ace5fcafa160f6514392885bfbe57c4` para o host real.

| Evidência | Resultado |
| --- | --- |
| `02-installed-aura-13c933c3.png` | Central AURA instalada em Wayland real, catálogo com 1.153 títulos e card de continuidade visível. |
| `03-performance-installed-13c933c3.json` | Probe OpenGL real: startup 146 ms, 375 frames, p95 16,213 ms, RSS 395.132 KiB, VRAM 15.040 KiB; orçamento aprovado. |

O instalador confirmou daemon convergente e idempotente, serviço/socket ativos,
`schemaVersion=22`, zero operações pendentes e release ativa
`2.0.0rc1-13c933c30ace`. Nenhum reboot ou finalização da sessão KDE foi feito.

Esta evidência fecha a prova física da superfície AURA/bridge visual. Não é
prova de OSD, save-state, troca de disco, vídeo real ou retorno ao foco após um
jogo; esses fluxos permanecem próximos itens de validação.
