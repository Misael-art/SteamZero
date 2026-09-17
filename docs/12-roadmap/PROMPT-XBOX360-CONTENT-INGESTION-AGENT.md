# Prompt de execução — Xbox 360 sem impacto nas frentes paralelas

Você é o agente responsável por implementar a capacidade `XBOX360-UNIFIED-CONTENT-INGESTION` no SteamZero.

## Objetivo

Implemente ingestão automática e resiliente para Xbox 360. O usuário deve selecionar uma pasta, arquivo, unidade removível ou compartilhamento e obter um catálogo organizado sem renomear ISO, separar GOD, localizar `default.xex` ou editar manualmente metadados.

O nome apresentado deve seguir:

```text
Título do jogo - Edição [TITLEID]
```

Use identidade técnica interna, não o nome externo, para agrupar fontes e resolver mídia.

## Escopo obrigatório

1. Criar o modelo de identidade Xbox 360 e referências de armazenamento sem caminho absoluto como identidade.
2. Criar resolver seguro para ISO, XEX extraído, GOD, conteúdo digital/XBLA, DLC, title update, cache e saves.
3. Associar arquivo GOD e pasta `.data` como uma única fonte.
4. Reconhecer `default.xex` e tratar múltiplos `.xex` de forma determinística, sem escolher um executável arbitrário.
5. Agrupar por `TITLEID`, content ID, media ID, edição e região.
6. Preservar duplicatas e variantes sem apagar ou mesclar silenciosamente.
7. Excluir cache, saves e perfis do catálogo de jogos.
8. Integrar o read model ao catálogo por uma fronteira nova e pequena.
9. Declarar a política Xbox 360 no manifesto e no adapter somente onde houver prova.
10. Implementar busca de mídia por `platformId + TITLEID`, com fallback seguro.
11. Informar footprint original, overhead, staging, mídia e dados do Xenia.
12. Adicionar testes de classificação, agrupamento, caminho removível/rede, mídia, conflitos, rollback e preflight.

## Limites de ownership — não tocar

Não edite nem reformate arquivos pertencentes às frentes de tema, launcher ou PS4. Em particular, não altere:

- `src/steamzero/ui/qml/**`;
- `src/steamzero/ui/assets/**`;
- `src/steamzero/domain/scene_esde.py`;
- `src/steamzero/domain/theme_*.py`;
- `src/steamzero/adapters/desktop_dashboard.py`;
- `src/steamzero/launcher/**`;
- `src/steamzero/adapters/launcher_*.py`;
- `src/steamzero/platform_manifests/64-playstation-4.platform.json`;
- `src/steamzero/adapters/manifests/shadps4.adapter.json`;
- `src/steamzero/domain/library.py` sem coordenação explícita.

Prefira módulos novos e adaptadores pequenos. Se a integração exigir um arquivo compartilhado, pare antes de editá-lo e registre o contrato/handoff em vez de invadir o owner atual.

## Regras de implementação

- Primeiro reproduza o comportamento atual com fixtures.
- Não confie no nome do arquivo para identidade primária.
- Não extraia ou copie arquivos grandes durante scan.
- Inspecione containers com limites de tamanho e proteção contra traversal.
- Não use hardlink/reflink entre filesystems diferentes.
- Preserve a referência original para SD, USB e rede.
- Não remova arquivos antigos automaticamente.
- Não transforme `ContentCache.pkg`, saves ou perfis em jogos.
- Jogos do Xbox original devem ser recusados como Xbox 360/Xenia.
- `ready` exige preflight do adapter; ausência de prova vira `needs-review`.
- Não fabrique suporte do Xenia para formatos não verificados.

## Sequência de entrega

1. Leia `docs/ACTIVE-WORK.md`, este prompt e o plano `docs/12-roadmap/XBOX360-CONTENT-INGESTION-AND-MEDIA-PLAN.md`.
2. Crie/assuma um workstream próprio antes de editar código.
3. Faça a menor implementação vertical: modelo → resolver → catálogo → mídia.
4. Escreva testes focados para cada fonte e cada estado de erro.
5. Execute os gates obrigatórios do `AGENTS.md` no fechamento.
6. Não instale nem altere o host nesta etapa; a prova física será posterior e só com autorização específica.
7. Faça commit isolado, atualize item de status e registre o handoff.

## Casos mínimos de teste

- ISO válida com `TITLEID` conhecido;
- pasta extraída com `default.xex`;
- pasta com vários `.xex`, sem escolha arbitrária;
- GOD com `.data` ausente, correspondente e incompatível;
- conteúdo digital em `Content/...`;
- DLC e title update ligados ao jogo correto;
- `ContentCache.pkg`, save e perfil ignorados;
- mesma fonte em dois caminhos, com deduplicação por fingerprint;
- edições/regiões diferentes mantidas separadas;
- volume removível indisponível e depois reencontrado;
- share de rede com mount point alterado;
- mídia encontrada por `TITLEID` e fallback sem correspondência;
- pacote inválido, traversal e limite de tamanho;
- falha no apply preservando origem e catálogo anterior;
- preflight recusado com estado e causa legíveis.

## Resultado esperado

Entregue um catálogo Xbox 360 simples para o usuário e conservador internamente: uma entrada lógica por jogo, fontes físicas preservadas, mídia correta, espaço mensurado, conflitos explícitos e nenhuma dependência nas frentes de tema ou launcher.

