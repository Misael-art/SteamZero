# PERSONAS

## P1 — "Console" (iniciante, maioria)

- Comprou o Deck como console. Nunca abriu o Desktop Mode.
- Quer: instalar, importar seus dumps de um pendrive, jogar. Não sabe o que é BIOS.
- Medos: quebrar o Deck, perder saves.
- Necessidades derivadas: setup guiado por controle; Centro de BIOS com cartões "presente/ausente" e importação local; erros com ação recomendada em linguagem humana; zero jargão técnico por padrão.
- Anti-requisito: nunca exigir terminal.

## P2 — "Auditor" (entusiasta avançado)

- Usa CLI, quer JSON, quer saber o hash de cada BIOS e cada mudança feita no sistema.
- Quer: `steamzero ... --json`, plano antes de aplicar, diff de configs, journal de operações, rollback seletivo, exportar/importar estado.
- Medos: ferramentas opacas que "fazem mágica" (motivo de ter abandonado EmuDeck).
- Necessidades derivadas: CLI-CONTRACT estável, ERROR-CATALOG com códigos, logs estruturados, modo dry-run em tudo.

## P3 — "Desktop Linux" (multi-distro)

- Roda Bazzite/Fedora/Arch no desktop com controle Bluetooth e TV.
- Quer: mesma plataforma do Deck no PC, perfis por dispositivo, sem dependência de SteamOS.
- Necessidades derivadas: adapters de distro (dnf/pacman/apt/rpm-ostree), detecção de hardware não-Deck, perfis docked-monitor/desktop.

## Antipersona

- Usuário que busca "baixar jogos": o produto não atende e comunica isso explicitamente (CONTENT-POLICY).
