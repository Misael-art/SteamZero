# CONFIGURATION-SCHEMAS — configuração da plataforma e de emuladores

## Configuração da própria plataforma

- Formato: TOML (comentável, tipado) em `$XDG_CONFIG_HOME/steamzero/config.toml` + drop-ins `config.d/*.toml` (ordem lexicográfica, merge raso documentado).
- Schema JSON publicado (`steamzero config schema`); validação na carga; erro aponta linha/campo.
- Toda escrita via transação (backup+atomic+verify). `steamzero config set k v` gera diff no plano.

Exemplo (extrato):

```toml
[storage]
roms_root = "auto"          # ou path; "auto" = resolve por volume role
backup_retention_days = 30
backup_max_gb = 20

[jobs]
max_background = 2
pause_on_battery_percent = 25
forbid_heavy_during_gameplay = true

[network]
offline_mode = "auto"       # auto|forced-offline
scraper_rate_limit_rps = 2

[ui]
scale = "auto"              # 100|125|150|tv|auto
reduce_motion = false
high_contrast = false
```

## Configuração de emuladores (F-CF-01/02)

- Parsers estruturados por formato: INI (configparser round-trip preservando comentários quando possível), JSON, XML (defusedxml), YAML (ruamel para preservar comentários). **Proibido** sed textual denso e eval-indireção (anti-padrões: RetroDECK framework.sh eval; EmuDeck sed/rsync bruto).
- Cada adapter declara `configFormat` + schema dos campos que gerencia; campos não gerenciados são preservados intocados (regra de round-trip).
- Operações: `get`, `set (diff)`, `apply-preset`, `restore-defaults --section`, `migrate` (versionada), sempre com backup e verify de parse pós-escrita (FM-12).
- Presets: camadas `default < platform < device/mode < game` com resolução determinística e visualização de origem por campo ("este valor vem do preset X").

## Config por jogo

`profile(scope=game)` no State Store referencia overrides; materialização para o formato do emulador acontece no launch (launcher genérico), nunca editando o arquivo global do emulador para um jogo específico quando o emulador suporta per-game config nativo.
