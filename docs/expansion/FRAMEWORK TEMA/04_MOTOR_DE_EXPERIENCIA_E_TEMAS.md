# 4. Contrato de tema e aprimoramentos nativos

## 4.1 Manifesto mínimo

Arquivo obrigatório: `theme.json`.

```json
{
  "schemaVersion": 1,
  "kind": "steamzero-theme-v1",
  "id": "org.example.ocean",
  "name": "Ocean",
  "version": "1.0.0",
  "author": "Example",
  "license": "CC-BY-4.0",
  "compatibility": {
    "themeApi": 1,
    "minimumSteamZeroVersion": "0.1.0"
  },
  "extends": "org.steamzero.default",
  "tokens": {
    "color": {
      "background": "#071019",
      "surface": "#0d1924",
      "surfaceRaised": "#122131",
      "border": "#2a3a49",
      "text": "#f2f6fb",
      "textMuted": "#9eabba",
      "accent": "#13bdf2",
      "accentStrong": "#0a5f85",
      "success": "#59d35d",
      "warning": "#ff9f1a",
      "danger": "#ff6b73",
      "focus": "#13bdf2"
    },
    "geometry": {
      "radiusSmall": 6,
      "radiusMedium": 10,
      "radiusLarge": 16,
      "borderWidth": 1,
      "focusWidth": 2,
      "minimumTarget": 48
    },
    "typography": {
      "scale": 1.0,
      "weightBody": 400,
      "weightStrong": 600
    },
    "motion": {
      "durationFast": 120,
      "durationNormal": 180
    }
  },
  "assets": {
    "background": "assets/background.png",
    "logo": "assets/logo.svg"
  }
}
```

O JSON Schema deve usar `additionalProperties: false` em todos os objetos fechados.
IDs seguem `^[a-z0-9]+(?:[.-][a-z0-9]+)+$`; versão usa SemVer estrito. O catálogo
normaliza apenas para comparação e nunca reescreve silenciosamente o manifesto.

## 4.2 Tokens obrigatórios

### Cor

`background`, `sidebar`, `surface`, `surfaceRaised`, `surfaceSelected`, `border`,
`text`, `textMuted`, `textDisabled`, `accent`, `accentStrong`, `success`, `warning`,
`danger`, `focus` e superfícies semânticas de sucesso/aviso/erro.

### Geometria

Raios pequeno/médio/grande, largura de borda, largura do foco, espaçamentos
pequeno/médio/grande e alvo mínimo. O resolver limita os valores a faixas seguras.

### Tipografia

Escala, pesos de corpo/destaque/título e família opcional restrita a fontes já
instaladas ou assets validados. O primeiro corte pode adiar fontes externas sem
adiar todo o framework.

### Movimento

Durações curta/normal/longa e intensidades de hover/foco. Não há animação arbitrária.
Com `reducedMotion`, todas as durações resolvidas são zero.

## 4.3 Assets permitidos no primeiro marco

- PNG, JPEG e WebP rasterizados;
- SVG estático sanitizado, sem script, referência externa, `foreignObject` ou URL;
- fonte local apenas se a API Qt usada permitir carregamento seguro e com limite.

Cada slot tem tipo, tamanho, dimensão e finalidade definidos pelo contrato. Um tema não
pode fornecer ícone para estado operacional, substituir texto, trocar glyph de controle
ou apontar para `http:`, `https:`, `file:` ou `data:`.

## 4.4 Tema QML

`Theme.qml` deve expor somente os valores resolvidos. Componentes deixam de possuir
hexadecimais próprios gradualmente e passam a consumir tokens. O primeiro commit de
integração cobre:

- propriedades de palette da `ApplicationWindow`;
- sidebar, superfícies, bordas, texto, foco e estados;
- `DarkButton`, `SteamComboBox`, `ErrorCard`, `CredentialProviderCard`,
  `ModernIcon` e `SwitchPlatformMark`;
- cores locais remanescentes em `Main.qml`, `Emulation.qml`, `SteamDesktop.qml`
  e `SteamGameplay.qml`.

Migração deve preservar o visual padrão pixel a pixel, exceto diferenças explicitamente
aprovadas.

## 4.5 Aprimoramentos nativos

O segundo tema builtin deve demonstrar o contrato, não recursos secretos. Melhorias
válidas para todos os temas:

- foco mais legível e coerente;
- superfícies semânticas para sucesso, aviso e erro;
- densidade portátil/monitor;
- escala tipográfica consistente;
- transições centralizadas;
- background/brand asset opcional com fallback;
- preview instantâneo e cancelável;
- indicação de compatibilidade, origem e licença no gerenciador.

O builtin aprimorado não pode usar chaves que um tema externo válido não consiga usar.
