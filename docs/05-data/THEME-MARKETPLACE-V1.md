# THEME-MARKETPLACE-V1 — opt-in do catálogo remoto de temas

## Posição de confiança

O marketplace remoto de temas **nasce desligado** e não possui catálogo
embutido. Não existe host default no código: sem configuração explícita do
operador, `theme search`, `theme info` e `theme install <id>` recusam com
`E-THEME-MARKETPLACE-DISABLED`.

A razão é de cadeia de suprimentos. Um endereço default aponta para
infraestrutura que o projeto precisa operar e defender para sempre; se o
domínio expirar ou for tomado, toda instalação passa a buscar temas de um
terceiro. Preferimos não ter catálogo a ter um catálogo que ninguém garante.

Instalar tema por **URL direta** ou **caminho local** é um caminho independente
e continua funcionando com o marketplace desligado.

## Arquivo de configuração

Caminho: `$XDG_CONFIG_HOME/steamzero/theme-marketplace-v1.json`
(default `~/.config/steamzero/theme-marketplace-v1.json`).

```json
{
  "schemaVersion": 1,
  "enabled": true,
  "catalogUrl": "https://catalogo-em-que-eu-confio.example/catalog-v1.json"
}
```

| Campo | Obrigatório | Significado |
|---|---|---|
| `schemaVersion` | sim | Versão do contrato. Hoje `1`. |
| `enabled` | sim | `false`, ausente ou arquivo inexistente ⇒ marketplace desligado. |
| `catalogUrl` | sim quando `enabled` | Endereço HTTPS do catálogo. Vazio ⇒ continua desligado. |

Arquivo ilegível ou JSON inválido **degrada para desligado**, com aviso em log —
nunca derruba a aplicação.

## Validação do endereço

`catalogUrl` é recusado com `E-THEME-CATALOG-FAILED` quando:

- o esquema não é `https` (inclusive `http` puro);
- não há host;
- há credencial embutida (`https://user:senha@host/...`).

## Variável de ambiente

`STEAMZERO_THEMES_CATALOG_URL` **escolhe o endereço, mas não habilita nada**. O
opt-in continua sendo a configuração persistida; a variável só substitui o
`catalogUrl` quando o marketplace já está habilitado, e o override é registrado
em log. Isso impede que uma variável injetada no ambiente de sessão ligue
sozinha um catálogo remoto.

## Integridade obrigatória

Instalação a partir do catálogo exige `checksumSha256` na entrada. Entrada sem
checksum falha fechado com `E-SUPPLY-NO-CHECKSUM`: origem inverificável não é
instalada. O checksum é conferido sobre os bytes baixados antes de qualquer
extração.

Instalação por URL direta aceita checksum opcional, porque nesse caso o
endereço foi escolhido pelo próprio operador no momento do comando.

## Catálogo como dado hostil

O documento remoto é tratado como entrada não confiável:

- resposta limitada a 2 MiB;
- JSON inválido, ausência de `entries` ou `entries` não-lista ⇒
  `E-THEME-CATALOG-FAILED`;
- entrada sem `id` textual, ou com `size`/`rating`/`downloadCount` não
  numéricos ⇒ `E-THEME-CATALOG-FAILED`. Nenhuma conversão escapa como
  `KeyError`/`ValueError` cru;
- cache local com TTL de 1 h; quando a rede falha, o cache expirado ainda é
  usado como fallback, com aviso — leitura degradada é preferível a indisponibilidade.

## Erros

| Código | Quando |
|---|---|
| `E-THEME-MARKETPLACE-DISABLED` | Sem opt-in: busca, info e install por ID recusados. |
| `E-THEME-CATALOG-FAILED` | Endereço inválido, catálogo inacessível ou malformado. |
| `E-SUPPLY-NO-CHECKSUM` | Entrada de catálogo sem `checksumSha256`. |
| `E-CONTENT-INCOMPLETE` | Checksum declarado não confere com os bytes baixados. |

## Testes que sustentam este contrato

`tests/unit/test_theme_marketplace.py`:

- `TestMarketplaceDisabledByDefault` — desligado sem config, desligado com
  `enabled:false`, variável de ambiente sozinha não habilita, `enabled` sem URL
  continua desligado, e ausência de host embutido no código-fonte;
- `TestCatalogUrlValidation` — recusa `http`, URL sem host e credencial embutida;
- `TestCatalogHostileInput` — entrada sem `id`, `id` não textual, `size` e
  `rating` não numéricos;
- `TestThemeMarketplaceInstall::test_install_without_checksum_fails_closed`.
</content>
</invoke>
