# WI-F5 — Registry declarativo de plataformas e capacidades

## Entrega

- `platform-manifest-v1` define identidade, tipo, sistemas, artwork, capabilities,
  ações, áreas da UI, emuladores candidatos, mídia, controles, timing, presets e
  limites de acesso cloud;
- o registry empacotado publica, em ordem estável, Switch; GB/GBC/GBA;
  NES/Famicom; SNES; Mega Drive; Arcade/CPS/Neo Geo/MAME; PlayStation; GeForce
  NOW; Xbox Cloud Gaming e Amazon Luna;
- cada plataforma possui fallback SVG original próprio, sem repetir a ilustração
  do Switch;
- manifests referenciam adapters apenas por `adapterId`; o teste cruza essas
  referências com a allowlist fechada de `AdapterRegistry`;
- a composição do workspace lê áreas, capacidades, mídia, controles, timing,
  presets e artwork do manifesto, em vez de duplicá-los no controller;
- a UI de emulação não contém roteamento, cópia nem fallback condicionado a
  Switch: plataformas, áreas, extensões de conteúdo e estados vêm do payload;
- plataformas ainda não compostas aparecem como planejadas ou não verificadas,
  com ações desabilitadas e razão explícita;
- plataformas cloud não publicam emuladores locais e permanecem desabilitadas
  até composição operacional posterior.

## Segurança e limites

- JSON Schema draft 2020-12 fechado, com `additionalProperties: false`, limites
  de tamanho, IDs e enums;
- validação semântica rejeita IDs, ações e precedências duplicados, referências
  de capability ausentes e mistura entre plataformas cloud e emuladas;
- URLs cloud exigem HTTPS, sem credenciais, porta padrão/443 e hostname presente
  na allowlist declarada;
- o registry carrega somente recursos empacotados; manifestos nunca escolhem
  símbolos executáveis, comandos de shell ou módulos importáveis;
- timing desconhecido permanece explicitamente `unknown-explicit`; nenhum dado
  de hardware ou compatibilidade foi inventado.

## Evidência

- testes focados de registry, workspace, controller, contratos, QML offscreen e
  bridge: 105 aprovados; o gate final da UI genérica aprovou 44 casos;
- Hypothesis executa 50 exemplos contra o parser defensivo e aceita somente
  manifesto válido ou erro tipado do SteamZero;
- suíte integral com cobertura: 1351 aprovados;
- cobertura limpa: 85,10% (mínimo exigido: 85%);
- Ruff, mypy strict em 142 módulos, independência, fronteiras e
  `git diff --check`: aprovados;
- wheel `steamzero-0.1.0a34-py3-none-any.whl` inspecionado: 10 manifestos, schema
  público e 10 SVGs de fallback estão presentes.

Estado final: `verified-dev`. QML foi validado offscreen; nenhuma validação
física, sensorial ou de serviço cloud é alegada.
