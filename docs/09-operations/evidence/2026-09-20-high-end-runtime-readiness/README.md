# Prontidão resiliente de PS4, PS5, X68000 e Xbox — 2026-09-20

## Entrega segura desta etapa

Esta etapa registra e implementa preflights antes do spawn:

- PS4 e PS5 recusam archive bruto (`.rar`, `.7z`, `.zip` e tarballs) até que o
  conteúdo tenha sido materializado por uma operação governada. O emulador não
  recebe um container que ele não sabe consumir.
- PS5 preserva o preflight já existente de x86_64/Vulkan. SharpEmu ausente no
  host continua sendo ausência operacional, não compatibilidade inventada.
- X68000 permanece catalogado. O scanner expõe o conjunto archive como
  `needs-platform-contract` enquanto a frente dona do manifesto não comprova o
  contrato M3U do PX68K; nenhum M3U falso é publicado.
- Xbox consulta a configuração nativa/Flatpak do xemu somente para leitura e
  exige `eeprom`, `flash`, `mcpx` e `hdd` regulares antes do spawn. No host,
  `xemu.toml` contém apenas `eeprom_path`; portanto a tela de configuração não
  é tratada como gameplay.
- Xbox 360 continua protegido pelo lifecycle: Xenia Canary está `degraded` e
  não é considerado lançável enquanto o deployment fixado não convergir.

## Estado físico observado

- Release ativa observada: `2.0.0rc1`.
- Snapshot read-only de componentes após o commit: shadPS4 e SharpEmu aparecem
  instalados; Xenia Canary permanece `degraded` por divergência do deployment;
  xemu aparece `unavailable` porque a consulta Flatpak falhou, sem qualquer
  tentativa de reparar ou instalar automaticamente.
- `7z` está disponível para backend seguro de archives; a materialização ainda
  depende de ação explícita e job assíncrono, sem modificar a origem.
- O acervo contém Xbox ISO, Xbox 360 payload/configuração, 14 archives X68000,
  dois artefatos PS5 (`.rar` e `.exfat`) e metadados PS4 sem payload jogável.
- Não houve instalação, rollback, reboot, download de firmware, alteração do
  host ou alegação de gameplay PS4/PS5/Xbox/X68000 nesta etapa.

## Gates desta entrega

- Regressão ampliada: **253 passed** cobrindo controller, PS4, PS5, multidisco,
  materializador e classificação da biblioteca.
- Ruff check, `ruff format --check`, mypy, independência e boundaries: **pass**.
- A suíte isolada integral foi tentada, mas o runner produziu falhas/erros em
  lote e as repetições com `-x` avançaram até 16% antes de terminar sem processo
  visível ou rodapé. O resultado é **inconclusivo**, não verde; nenhum teste foi
  removido ou enfraquecido para contornar isso.

## Handoffs e próximos gates

O contrato M3U X68000 está em `SOFT-COORDINATION` porque o manifesto e os testes
pertencem a `WS-2026-09-MULTIDISC-DESCRIPTOR-RECONCILIATION`. A execução continua
nos itens independentes: materialização, preflight Xbox, validação de conteúdo e
testes estáticos. A prova física só pode ocorrer após autorização de instalação e
com firmware/dumps legais disponíveis.
