# Framework de temas do SteamZero — plano validado

**Status:** especificação pronta para implementação incremental

**Validado contra:** `main` em `2aaa01d` (2026-07-26)

**Escopo:** UI Desktop Qt Quick/QML; o Game Mode continua condicionado ao ADR-0002

Esta pasta define como acrescentar temas nativos aprimorados e temas de terceiros
ao SteamZero sem reescrever o produto, duplicar o backend ou permitir execução de
código não confiável dentro da UI.

## Resultado da validação

O plano original era uma visão de produto genérica e não estava implementável neste
repositório. Ele:

- usava um nome de produto incorreto, contrariando a identidade consolidada SteamZero;
- propunha sete camadas novas sem mapear os módulos existentes;
- citava projeto de referência proibido no runtime pelo ADR-0019;
- misturava tema, plugin, editor visual, marketplace, asset registry e novo runtime;
- não definia formato de pacote, fronteira de confiança, fallback ou ordem de commits;
- não dizia como provar segurança, acessibilidade, foco e empacotamento.

Esta revisão converte a ideia em uma expansão do sistema atual. O marco inicial é
deliberadamente orientado a dados: terceiros alteram tokens e assets declarativos,
mas não fornecem QML, JavaScript, Python ou shaders executáveis.

## Ordem de leitura e execução

1. [01_VISAO_E_PRINCIPIOS.md](01_VISAO_E_PRINCIPIOS.md)
2. [02_CONSTITUICAO_DO_PROJETO.md](02_CONSTITUICAO_DO_PROJETO.md)
3. [03_ARQUITETURA_MESTRA.md](03_ARQUITETURA_MESTRA.md)
4. [04_MOTOR_DE_EXPERIENCIA_E_TEMAS.md](04_MOTOR_DE_EXPERIENCIA_E_TEMAS.md)
5. [05_GESTAO_DE_ASSETS_E_OTIMIZACAO.md](05_GESTAO_DE_ASSETS_E_OTIMIZACAO.md)
6. [06_EQUIPES_RESPONSABILIDADES_E_RACI.md](06_EQUIPES_RESPONSABILIDADES_E_RACI.md)
7. [07_ROADMAP_DEPENDENCIAS_E_PARALELIZACAO.md](07_ROADMAP_DEPENDENCIAS_E_PARALELIZACAO.md)
8. [08_OPERACAO_COM_CODEX.md](08_OPERACAO_COM_CODEX.md)
9. [09_CRITERIOS_DE_QUALIDADE_E_ACEITE.md](09_CRITERIOS_DE_QUALIDADE_E_ACEITE.md)
10. [10_PROMPT_EXECUCAO.md](10_PROMPT_EXECUCAO.md)

## Decisões resumidas

| Tema | Decisão do primeiro marco |
|---|---|
| Runtime | reaproveitar Qt Quick/QML e a bridge loopback existentes |
| Tema nativo | manifesto empacotado com o SteamZero |
| Tema de terceiros | pacote local declarativo, tratado como não confiável |
| Customização | tokens semânticos e assets allowlisted |
| Código externo | proibido: QML, JS, Python, bibliotecas e shaders |
| Persistência | preferência XDG escrita por plano transacional |
| Ativação | preview → plano → confirmação → apply → verificação |
| Falha | fallback automático para `org.steamzero.default` |
| Acessibilidade | alto contraste e redução de movimento prevalecem sobre o tema |
| Distribuição | instalação local; catálogo online e assinatura ficam fora do marco |

## Fonte de verdade

Este conjunto é uma especificação de expansão. Em caso de conflito, prevalecem
`AGENTS.md`, os ADRs aceitos, os contratos em `docs/05-data` e `docs/06-api`, e as
regras de segurança e transação já existentes.
