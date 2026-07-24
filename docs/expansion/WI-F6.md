# WI-F6 — Perfis versionados e reversíveis de input

## Entrega

- `retro-input-profile-v1` define perfil, revisão, plataformas compatíveis,
  licença, layout, limite de jogadores, bindings semânticos e orientação;
- o registry empacotado publica oito perfis originais: gamepad padrão, par de
  Joy-Con, Mega Drive de três e seis botões, arcade, PlayStation digital,
  DualShock e gamepad cloud;
- todo perfil referenciado pelos dez manifestos de plataforma existe, declara a
  plataforma correspondente e respeita seu limite de jogadores;
- a resolução de bindings é pura e determinística; orientações portrait
  remapeiam apenas as direções quando o perfil declara `rotate-with-display`;
- ativações globais, por plataforma, jogo, dispositivo ou modo são persistidas
  em arquivo canônico sob a configuração do usuário;
- preview, confirmação, aplicação e rollback usam a transação G-FULL, com
  precondição congelada inclusive para operações sem alteração;
- a central de emulação publica estado, revisão, orientação e ações de perfil
  sem introduzir roteamento específico na QML;
- CLI e daemon expõem a mesma superfície fechada:
  `controls profiles|plan|apply|rollback`.

## Segurança e limites

- JSON Schema draft 2020-12 fechado, limites de tamanho e enums para todos os
  campos executáveis;
- entradas físicas aceitam somente formas declarativas `button.*`, `axis.*` e
  `hat.*`; perfis não escolhem comandos, módulos ou símbolos executáveis;
- ativações rejeitam symlinks, arquivos não regulares, tamanho acima de
  256 KiB, chaves inesperadas, alvo divergente, plataforma incompatível e
  bindings resolvidos adulterados;
- `scopeId`, plataforma, perfil e orientação são validados antes de construir o
  caminho; não há interpolação livre de diretórios;
- rollback aceita apenas operações do próprio domínio de perfis;
- TATE físico, rotação de janela, recovery de display e controles
  especializados continuam explicitamente destinados a R4 e R6.

## Evidência

- testes focados de domínio, controller, CLI, daemon, contratos, QML offscreen e
  bridge: aprovados;
- Hypothesis executa 50 exemplos contra o parser defensivo e aceita somente
  perfil válido ou erro tipado do SteamZero;
- suíte integral com cobertura: 1375 aprovados;
- cobertura limpa: 85,14% (mínimo exigido: 85%); domínio de perfis: 86,40%;
- Ruff, mypy strict em 144 módulos, independência, fronteiras,
  `git diff --check` e validação JSON: aprovados;
- wheel `steamzero-0.1.0a34-py3-none-any.whl` inspecionado: oito perfis e o
  schema público estão presentes.

Estado final: `verified-dev`. QML foi validado offscreen; nenhuma validação de
hardware, rotação física, controle especializado ou experiência sensorial é
alegada.
