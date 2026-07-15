# ROBUSTNESS-SCORE — avaliação objetiva de robustez

## Escala e pesos

Cada critério recebe 0–4 por projeto:
0 = ausente · 1 = ad-hoc/inconsistente · 2 = presente em parte dos módulos · 3 = sistemático com exceções · 4 = sistemático e testado.

Pesos (soma 100): tratamento de erro 10; idempotência 8; atomicidade 8; backup 8; rollback 10; validação de entrada 8; logs 6; segurança 12; testes 10; portabilidade 5; manutenção 5; UX de falha 5; offline 3; compat Steam Deck 5; proteção de dados do usuário 12 → normalizado para 0–100.

Justificativas citam evidências (arquivo:linha quando aplicável). Pontuação é da **base de código atual**, não do potencial.

## Notas por critério

| Critério (peso) | PhaseZero (linux/) | EmuDeck | LinuxToys | RetroDECK |
|---|---|---|---|---|
| Tratamento de erro (10) | 3 — strict mode universal em lib/pz; exceções tratadas (`|| true` deliberado) | 1 — sem strict mode (0/228); erros seguem fluxo | 2 — libs checam deps/distro; scripts confiam nas libs | 2 — logger + checks.sh, mas sem strict mode e com eval |
| Idempotência (8) | 3 — `--needed`, pré-checagem `pacman -Q`, guards visited em profiles (common.sh:594-611) | 1 — reinstalação sobrescreve; migrações one-shot destrutivas | 2 — pkg managers idempotentes por natureza; overrides flatpak acumulam | 2 — presets reaplicáveis; post_update por versão é one-way |
| Atomicidade (8) | 3 — `pz_boot_atomic_install` (mktemp+mv, common.sh:425-434); managed file via install | 1 — `.temp`+mv só no download (helperFunctions.sh:760-762); configs via rsync direto | 1 — escrita direta | 1 — escrita direta via eval/sed |
| Backup (8) | 3 — boot bundle completo (common.sh:260-282); .bak por escrita | 0 — migrações sem backup | 0 | 2 — backup userdata tar; sem backup por operação |
| Rollback (10) | 3 — manifesto por operação + library rollback com verify; falhas: cp não-atômico, manifesto apagado inteiro | 0 | 0 | 1 — reinstalar versão anterior manualmente |
| Validação de entrada (8) | 3 — schemas jq de profile (common.sh:566-588), path traversal guard (748-764), `pz_boot_valid_id` | 1 — parâmetros posicionais sem validação | 1 — compat header validado pela GUI | 1 — eval com strings de config |
| Logs (6) | 3 — pz.log 0600 rotacionado, níveis; falta estrutura JSON | 1 — echos | 1 | 3 — logger.sh com níveis configuráveis |
| Segurança (12) | 3 — umask 077, admin bridge, sem eval, guards EFI/live-root | 1 — curl|bash no instalador upstream, downloads sem checksum por padrão, sem strict mode | 2 — sudo_rq pontual, flatpak; mas `sudo` liberal nos scripts | 1 — 26 eval em framework.sh; sandbox Flatpak compensa parcialmente (+) |
| Testes (10) | 3 — 122 arquivos Pester + CI parse; cobertura Linux via testes que exercitam scripts | 0 — test.sh trivial | 0 | 1 — post_build_check, automation_tools |
| Portabilidade (5) | 2 — Arch-first (pacman/yay hard no profile runner) | 2 — Deck-first + nonDeck | 4 — 8+ famílias de distro | 4 — Flatpak distro-agnóstico |
| Manutenção (5) | 2 — monólito PS + linux/ em crescimento; docs internas fortes | 1 — 31 scripts quase-clones | 3 — padrão pequeno e uniforme | 2 — framework denso, mas modelo components moderniza |
| UX de falha (5) | 2 — mensagens CLI claras; envelope com blockers | 1 — zenity genérico | 2 — zenity com fallback TTY | 2 — dialogs + wiki |
| Offline (3) | 2 | 0 — setup exige rede | 1 | 3 — roda offline pós-install |
| Compat Deck (5) | 4 — modos/dock/microSD/plugins dedicados | 3 — nasceu para Deck | 1 | 4 — appliance para Deck |
| Proteção de dados (12) | 3 — backups, quarentena, confirmToken na biblioteca | 1 — migrações movem dados do usuário sem backup | 2 — não toca dados de jogos | 2 — move_folder com checagens; sem transação |

## Resultado ponderado (0–100)

| Projeto | Score | Leitura |
|---|---|---|
| **PhaseZero (linux/)** | **72** | Melhor base transacional/segurança; débitos: rollback não verificado, GC de backups, Arch-first |
| **RetroDECK** | **49** | Melhor plataforma/distribuição; débitos: eval, sem transação, sem testes de mutação |
| **LinuxToys** | **41** | Melhor simplicidade/portabilidade; sem estado, sem domínio de emulação |
| **EmuDeck** | **25** | Melhor cobertura funcional/templates; robustez estrutural mais baixa dos quatro |

Conclusão operacional: herdar **arquitetura de execução** do PhaseZero, **modelo de plataforma/distribuição** do RetroDECK, **formato de módulo** do LinuxToys e **conteúdo de domínio** (templates, paths, receitas por emulador) do EmuDeck — reimplementado sob o padrão transacional.
