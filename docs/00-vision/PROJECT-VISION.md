# PROJECT-VISION — SteamZero

## Visão

Uma plataforma de jogos e emulação para Steam Deck e desktops Linux em que **nenhuma operação destrói dados do usuário**, toda mudança é planejada, visível e reversível, e a experiência inteira — da instalação de um emulador à restauração de um save — é operável pelo controle.

O produto une quatro heranças, sem copiá-las:

1. **EmuDeck** → cobertura funcional (31+ emuladores, templates de configuração, SRM/ES-DE, cloud sync) e experiência acumulada de casos reais.
2. **LinuxToys** → instaladores modulares mínimos: um script = uma capacidade, com metadados declarativos no cabeçalho e biblioteca comum de detecção de distro.
3. **RetroDECK** → isolamento (Flatpak), plataforma coesa (paths móveis, backup de userdata, BIOS checker, componentes com manifest/recipe), distribuição como appliance.
4. **PhaseZero** → padrão transacional: scan→plan→preview→apply→verify→rollback com `confirmToken`, manifesto de mudanças, envelope JSON, escrita atômica, guards de preflight, bridge de privilégio mínimo.

## O que o produto É

- Uma **plataforma** (núcleo transacional + gerenciador de jobs + state store + adapters + serviço local de UI/API), não uma interface que dispara scripts.
- **Segura por padrão**: menor privilégio, allowlist de ações, validação de caminhos, staging, checksums, quarentena.
- **Orientada a estados**: cada componente, jogo, BIOS, save e job tem estado conhecido, auditável e exportável.
- **Resiliente ao mundo real do Deck**: suspensão, dock/undock, microSD removido, bateria, offline, atualizações da Valve.
- **Legalmente responsável**: política `local-owned-dump-only` — o produto organiza e valida o que o usuário já possui; nunca obtém conteúdo protegido.

## O que o produto NÃO é

Ver NON-GOALS.md. Em uma linha: não é loja de ROMs, não é lançador universal de scripts arbitrários, não é ferramenta de administração geral de Linux (boot/VM/homelab ficam no PhaseZero clássico).

## Métrica de sucesso da visão

> Um usuário iniciante instala a plataforma, importa seus próprios dumps, joga, suspende, troca de dock, atualiza o SteamOS — e nunca vê um estado corrompido nem perde um save. Um usuário avançado audita cada operação por CLI/JSON e reverte qualquer uma delas.
