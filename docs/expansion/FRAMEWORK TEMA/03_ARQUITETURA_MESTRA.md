# 3. Arquitetura incremental

## 3.1 Fluxo

```text
pacote builtin / pacote do usuário
              │
              ▼
ThemeCatalog → ThemeValidator → ThemeResolver
                                  │
                     tema resolvido e seguro
                                  │
                 DesktopDashboard / bridge
                                  │
                                  ▼
                         Main.qml / Theme.qml
```

QML nunca recebe o caminho bruto de um pacote e nunca interpreta um manifesto
parcialmente validado.

## 3.2 Mapeamento para o repositório

| Responsabilidade | Local sugerido |
|---|---|
| modelo puro, resolução e validação adicional | `src/steamzero/domain/themes.py` |
| descoberta, paths XDG e leitura segura | `src/steamzero/adapters/theme_catalog.py` |
| manifesto JSON Schema | `src/steamzero/schemas/theme-manifest-v1.schema.json` |
| preferência do usuário | `src/steamzero/core/paths.py` + arquivo `theme-preference-v1.json` |
| plano/apply transacional | `src/steamzero/domain/theme_preferences.py` |
| temas nativos | `src/steamzero/themes/<theme-id>/` |
| projeção para a UI | `src/steamzero/adapters/desktop_dashboard.py` |
| rotas allowlisted | `src/steamzero/adapters/desktop_contracts.py` e `desktop_ui.py` |
| tokens QML | `src/steamzero/ui/qml/Theme.qml` e `qmldir` |
| gerenciador visual | seção em `src/steamzero/ui/qml/Main.qml` |
| testes | `tests/unit/test_themes.py`, `tests/integration/test_theme_*`, `tests/qml/check_themes.qml` |

Nomes podem ser ajustados pelo implementador se o código atual oferecer padrão melhor,
mas as fronteiras acima devem permanecer.

## 3.3 Contratos de backend

Read model em `dashboard.theme`:

```json
{
  "schemaVersion": 1,
  "activeThemeId": "org.steamzero.default",
  "activeThemeVersion": "1.0.0",
  "previewThemeId": null,
  "fallbackApplied": false,
  "themes": [],
  "resolved": {
    "tokens": {},
    "assets": {}
  },
  "errors": []
}
```

Rotas mínimas:

| Método | Rota | Efeito |
|---|---|---|
| `GET` | `/themes` | catálogo e tema ativo |
| `POST` | `/theme/preview` | resolve para preview, sem persistir |
| `POST` | `/theme/preview/cancel` | descarta preview |
| `POST` | `/theme/plan` | cria plano de ativação, instalação ou remoção |
| `POST` | `/theme/apply` | aplica plano com `planId` e `confirmToken` |

Se os contratos atuais favorecerem IDs de ação em vez de rotas novas, preservar o
catálogo allowlisted. Não criar endpoint genérico de leitura de arquivo.

Payload de `/theme/plan` deve usar uma união discriminada fechada:

- `{"action":"activate","themeId":"..."}`;
- `{"action":"install","sourcePath":"..."}`;
- `{"action":"remove","themeId":"..."}`.

`sourcePath` é uma origem local selecionada explicitamente pelo usuário, somente leitura,
e só existe na ação `install`. O destino nunca vem do cliente: é derivado do ID validado e
da raiz XDG. Nenhuma dessas strings é encaminhada para shell.

## 3.4 Catálogo de erros

Adicionar os códigos ao catálogo existente antes de usá-los:

| Código | Situação |
|---|---|
| `E-THEME-MANIFEST` | manifesto ausente, malformado ou fora do schema |
| `E-THEME-INCOMPATIBLE` | versão/API incompatível |
| `E-THEME-UNSAFE` | path, tipo ou conteúdo proibido |
| `E-THEME-LIMIT` | tamanho, quantidade, dimensão ou profundidade excedida |
| `E-THEME-NOT-FOUND` | ID/origem deixou de existir |
| `E-THEME-ACTIVE` | remoção isolada do tema ativo |

Os nomes finais devem ser confrontados com `docs/06-api/ERROR-CATALOG.md` para evitar
colisão. Não reutilizar erro genérico se a UI precisar orientar uma correção diferente.

## 3.5 Persistência e diretórios

- Builtins: recursos do pacote Python via `importlib.resources`.
- Pacotes do usuário: `${XDG_DATA_HOME:-~/.local/share}/steamzero/themes/<theme-id>/`.
- Preferência: `${XDG_CONFIG_HOME:-~/.config}/steamzero/theme-preference-v1.json`.
- Staging, journal e rollback: infraestrutura transacional existente.

O caminho XDG deve ser derivado em `core.paths`, sobrescrevível em testes. Diretórios de
usuário usam `0700`; arquivos gerenciados usam `0600`.

## 3.6 Resolução

1. Descobrir builtins e pacotes do usuário sem seguir symlinks.
2. Validar JSON Schema e limites.
3. Confirmar que o diretório corresponde ao `id`.
4. Resolver `extends`, com profundidade máxima 2 e detecção de ciclo.
5. Mesclar apenas chaves allowlisted.
6. Resolver assets dentro da raiz validada.
7. Aplicar fallback para campos ausentes.
8. Sobrepor acessibilidade e perfil responsivo.
9. Publicar um objeto imutável/determinístico para QML.

Pacote inválido aparece no catálogo como `invalid` com erro estruturado, mas não impede
o carregamento dos demais temas.

## 3.7 Atomicidade

Instalação deve extrair ou copiar para staging, validar por completo e só então publicar
o diretório final por operação transacional. Ativação grava apenas a preferência. Remoção
nunca toca assets compartilhados fora do diretório do pacote e nunca remove builtins.
