# NON-GOALS — o que este produto deliberadamente NÃO faz

| # | Não-objetivo | Racional | Onde vive, se o usuário precisar |
|---|---|---|---|
| N1 | Obter ROMs/BIOS/keys/firmware de qualquer fonte | Política local-owned-dump-only (inegociável) | Usuário produz seus próprios dumps |
| N2 | Contornar DRM ou verificação de assinatura de consoles | Legal/ético | — |
| N3 | Gerenciamento genérico de boot/GRUB, Windows VM, Waydroid, homelab, LLM server | A herança ampla do PhaseZero continua fora do domínio. A exceção estreita já implementada é a sessão/entrada recuperável do **SteamZero Game Mode**, sempre gated, reversível e sujeita à certificação física; ela não transforma o produto em gerenciador geral de boot | PhaseZero clássico (`linux/pz boot|windows-vm|waydroid|server`) para administração ampla; `steam_boot.py` somente para a jornada Game Mode |
| N4 | Ser frontend de biblioteca próprio concorrendo com ES-DE/Steam | Estratégia é integrar frontends via adapters, não substituí-los | Adapters (03-architecture/ADAPTER-MODEL.md) |
| N5 | Suporte a Windows/macOS/Android | Linux-first (SteamOS, Arch, Fedora, Bazzite, Ubuntu) | EmuDeck upstream cobre esses alvos |
| N6 | Loja/repositório próprio de plugins arbitrários de terceiros | Superfície de supply chain injustificável no v1 | Modelo de plugins restrito (ADR-0007) |
| N7 | Telemetria automática | Privacidade; pacote de suporte é manual e revisável | 09-operations/SUPPORT-BUNDLE.md |
| N8 | Overclock/undervolt e mutações de firmware do Deck | Risco de hardware fora do apetite do produto | Ferramentas dedicadas de terceiros |
| N9 | Multi-usuário completo no v1 | Complexidade; schema já prevê para v2 (Q9) | RetroDECK multi_user como referência futura |
| N10 | Compatibilidade com SteamOS 2.x ou hardware pré-Deck | Base instalada irrelevante para o alvo | — |
