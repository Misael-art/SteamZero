# Baseline read-only do host para PS5

Data: 2026-09-19

Este registro é somente diagnóstico; não é prova de instalação, gameplay ou
compatibilidade física.

Comandos executados:

- `uname -m` → `x86_64`;
- `vulkaninfo --summary` → Vulkan 1.4.357, GPU AMD RADV (`AMD Custom GPU
  0405`), Mesa 26.1.7;
- `tools/release_host.py inspect` → release ativa
  `2.0.0rc1-f98a1a12a46b`, commit de origem `f98a1a12...`, SharpEmu ausente no
  inventário de componentes.

O diagnóstico confirmou arquitetura e Vulkan disponíveis, mas não autoriza
instalação, não fornece dump PS5 e não substitui as capturas PNG exigidas pela
prova física. A branch de integração permanece local e sem instalação no host.
