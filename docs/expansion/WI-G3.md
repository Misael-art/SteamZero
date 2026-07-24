# WI-G3 — vkBasalt por jogo, custo e desligamento completo

## Entrega

- catálogo `gtool-vkbasalt-v1` publica disponibilidade, escopo exclusivamente
  por jogo e custos qualitativos para `off`, CAS, FXAA e SMAA;
- o perfil Steam aceita somente esses quatro modos e mostra diff antes do
  apply;
- presets ativos geram configuração fixa por App ID sob a raiz XDG do
  SteamZero, por transação G-FULL;
- o launcher revalida capacidade, arquivo regular, tamanho e conteúdo exato
  antes de compor `ENABLE_VKBASALT=1` e `VKBASALT_CONFIG_FILE`;
- `off` remove o arquivo gerenciado e não publica nenhuma variável nem camada
  vkBasalt no processo;
- rollback restaura atomicamente o perfil e a configuração anterior;
- QML expõe preset, custo e motivo quando escopo ou componente impedem a ação.

## Segurança e compatibilidade

- não há campo para shader, caminho, variável ou conteúdo arbitrário;
- configs com symlink, conteúdo divergente ou tamanho excessivo falham fechado;
- o launcher preserva perfis antigos, interpretando ausência do novo campo como
  `off`;
- capacidade aceita a observação do pacote ou de um manifesto Vulkan regular,
  sem afirmar que o efeito foi visualmente validado;
- a sintaxe implementada segue o
  [README oficial do vkBasalt](https://github.com/DadSchoorse/vkBasalt#usage)
  para ativação e arquivo de configuração por variável.

## Evidência

- suíte integral: 1.456 testes aprovados;
- cobertura total: 85,34%;
- cobertura do domínio de presets vkBasalt: 100%;
- Ruff, mypy em 153 módulos, independência e fronteiras: aprovados;
- oito harnesses QML offscreen aprovados;
- testes cobrem catálogo/custo, CAS ativo, `off` sem ambiente, remoção,
  rollback, escopo global, capacidade ausente, config adulterada e valores
  fora da allowlist.

Estado final: `verified-dev`. Custo real e resultado perceptual dependem do jogo,
resolução, driver e GPU; permanecem `PENDING-HUMAN`/hardware e não foram
promovidos por testes offscreen.
