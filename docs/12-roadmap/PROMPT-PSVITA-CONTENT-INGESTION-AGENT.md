# Prompt de execução — PS Vita sem impacto nas frentes paralelas

Você é o agente responsável por implementar `PSVITA-UNIFIED-CONTENT-INGESTION` no SteamZero.

## Objetivo

Permita que o usuário escolha uma pasta, arquivo, unidade removível ou compartilhamento e obtenha uma biblioteca PS Vita organizada sem renomear, extrair VPK manualmente, localizar `param.sfo` ou editar firmware, keys e licenças.

Nome de apresentação:

```text
Título do jogo - Edição [TITLE_ID]
```

Separe `gameGroupId`, `mediaId` e `sourceId`. A identidade primária vem dos metadados internos.

## Escopo obrigatório

1. Modelar obra, variante, fonte, firmware, pacote de fontes, key e licença.
2. Reconhecer pasta extraída, VPK, ZIP, VCI, PKG, NoNpDrm e FAGDec.
3. Ler `sce_sys/param.sfo` com parser seguro.
4. Classificar PKG em base, update, DLC, demo, aplicação ou desconhecido.
5. Associar updates/DLC sem criar jogos duplicados.
6. Classificar Vitamin como `unsupported` e Maidump como `needs-review`.
7. Implementar store de firmware, fontes, keys e licença/zrif sem fabricar ou baixar conteúdo protegido.
8. Resolver mídia por plataforma + title ID/content ID.
9. Usar volume/share + caminho relativo para SD, USB e rede.
10. Informar footprint de origem, instalação, staging, requisitos e mídia.
11. Implementar preflight Vita3K e rollback transacional.
12. Adicionar testes focados e fixtures para todos os estados.

## Ownership proibido

Não altere:

- `src/steamzero/ui/qml/**`;
- `src/steamzero/ui/assets/**`;
- `src/steamzero/domain/scene_esde.py`;
- `src/steamzero/domain/theme_*.py`;
- `src/steamzero/adapters/desktop_dashboard.py`;
- `src/steamzero/launcher/**`;
- `src/steamzero/adapters/launcher_*.py`;
- `src/steamzero/platform_manifests/36-playstation-3.platform.json`;
- `src/steamzero/adapters/manifests/rpcs3.adapter.json`;
- `src/steamzero/platform_manifests/64-playstation-4.platform.json`;
- `src/steamzero/adapters/manifests/shadps4.adapter.json`.

Não edite `library.py`, `media_registry.py` ou `emulation.py` sem coordenação. Prefira módulos próprios e handoff de integração.

## Regras

- Scan read-only antes de qualquer instalação.
- Não confie em nomes externos.
- Não extraia conteúdo grande durante o scan.
- Proteja parsers contra traversal, truncamento e limites abusivos.
- Não baixe, fabrique ou altere firmware, keys ou licenças.
- Preserve fontes originais.
- Hardlink/reflink somente no mesmo filesystem.
- `ready` exige requisitos, fonte íntegra e preflight Vita3K.
- Não declare suporte para 7z ou formatos não comprovados pelo adapter.

## Sequência

1. Leia `docs/ACTIVE-WORK.md` e o plano `docs/12-roadmap/PSVITA-CONTENT-INGESTION-AND-MEDIA-PLAN.md`.
2. Crie/assuma workstream próprio.
3. Crie fixtures de pasta, VPK, ZIP, VCI, PKG, Vitamin, Maidump, firmware, key e licença.
4. Implemente modelo → resolver → requirements store → catálogo → mídia → preflight.
5. Execute os gates do `AGENTS.md`.
6. Não instale nem altere o host nesta etapa.
7. Faça commit isolado e registre o handoff.

## Testes mínimos

- pasta válida com `sce_sys/param.sfo`;
- pasta com nome arbitrário;
- VPK válido, inválido e com traversal;
- ZIP contendo VPK, dump e conteúdo desconhecido;
- VCI válido e inválido;
- PKG base, update, DLC e demo;
- Vitamin recusado;
- Maidump em revisão;
- firmware e pacote de fontes presentes/ausentes/incompatíveis;
- key/license presente, ausente e inválida;
- mesmo title ID em duas origens com deduplicação;
- variantes regionais separadas;
- volume removível ausente e reencontrado;
- share de rede com mount point alterado;
- mídia encontrada por title ID/content ID;
- falha de apply preservando origem;
- preflight recusado com causa e recuperação.

## Resultado esperado

Uma biblioteca PS Vita simples para o usuário e rigorosa internamente: fontes reconhecidas pelo conteúdo, requisitos diagnosticados, mídia correta, espaço mensurado, rollback seguro e nenhuma dependência das frentes de tema, launcher, PS3 ou PS4.

