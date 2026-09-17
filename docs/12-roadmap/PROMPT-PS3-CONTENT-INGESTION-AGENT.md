# Prompt de execução — PS3 sem impacto nas frentes paralelas

Você é o agente responsável por implementar a capacidade `PS3-UNIFIED-CONTENT-INGESTION` no SteamZero.

## Objetivo

Implemente ingestão automática e resiliente para PlayStation 3. O usuário deve escolher uma pasta, arquivo, unidade removível ou compartilhamento e obter um catálogo organizado sem renomear pastas, separar PKGs, procurar `PARAM.SFO`, RAP, EDAT ou firmware manualmente.

O nome apresentado deve seguir:

```text
Título do jogo - Edição [TITLEID]
```

Separe internamente `gameGroupId`, `mediaId` e `sourceId`. Use title ID/content ID e metadados internos como identidade; o nome externo é apenas fallback.

## Escopo obrigatório

1. Criar modelos de obra, variante de mídia, fonte, firmware e licença.
2. Reconhecer pasta PS3 extraída, ISO, PKG, patch, DLC, RAP e EDAT.
3. Ler e validar `PARAM.SFO` sem transformar EBOOT, SELF, SPRX ou PRX em jogos.
4. Classificar PKG por conteúdo real: base, update, DLC, demo, aplicação ou desconhecido.
5. Associar RAP/EDAT ao content ID/media ID correto.
6. Registrar `PS3UPDAT.PUP` no store global de firmware, separado da biblioteca.
7. Preservar variantes físicas e digitais sem duplicar a obra na interface.
8. Manter regiões, edições e hashes conflitantes separados ou em revisão.
9. Usar referências de volume/share + caminho relativo para SD, USB e rede.
10. Integrar read model e busca de mídia por title ID/content ID.
11. Implementar footprint de origem, instalação, staging, firmware, mídia e dados RPCS3.
12. Adicionar preflight específico para o alvo RPCS3 e testes de rollback.

## Limites de ownership — não tocar

Não edite nem reformate arquivos de tema, launcher ou PS4:

- `src/steamzero/ui/qml/**`;
- `src/steamzero/ui/assets/**`;
- `src/steamzero/domain/scene_esde.py`;
- `src/steamzero/domain/theme_*.py`;
- `src/steamzero/adapters/desktop_dashboard.py`;
- `src/steamzero/launcher/**`;
- `src/steamzero/adapters/launcher_*.py`;
- `src/steamzero/platform_manifests/64-playstation-4.platform.json`;
- `src/steamzero/adapters/manifests/shadps4.adapter.json`.

Não altere `src/steamzero/domain/library.py`, `media_registry.py` ou `emulation.py` sem coordenação explícita do owner. Prefira módulos novos e um handoff de integração.

## Regras de implementação

- Faça scan read-only antes de qualquer instalação.
- Não confie no nome de PKG, ISO ou pasta como identidade primária.
- Não extraia ISO/PKG grandes durante o scan.
- Proteja parsers contra traversal, truncamento, tamanhos abusivos e dados malformados.
- Não baixe, gere ou altere RAP, EDAT ou firmware.
- Preserve fontes originais e licenças fornecidas pelo usuário.
- Hardlink/reflink somente no mesmo filesystem.
- Use referências relativas para volumes removíveis e rede.
- Não remova duplicatas automaticamente.
- `ready` exige firmware, licença necessária, fonte íntegra e preflight RPCS3.
- Não promova suporte para formatos que o adapter não comprovou.

## Sequência de entrega

1. Leia `docs/ACTIVE-WORK.md` e `docs/12-roadmap/PS3-CONTENT-INGESTION-AND-MEDIA-PLAN.md`.
2. Crie/assuma workstream próprio e confirme ownership antes de editar código.
3. Faça fixtures primeiro: pasta PS3, ISO, PKG base/update/DLC, RAP, EDAT, PUP e fonte ausente.
4. Implemente modelo → resolver → store de requisitos → catálogo → mídia → preflight.
5. Execute testes focados e todos os gates do `AGENTS.md` no fechamento.
6. Não instale nem modifique o host nesta etapa; a prova RPCS3 será posterior e autorizada separadamente.
7. Faça commit isolado e registre evidência/handoff.

## Casos mínimos de teste

- pasta com `PS3_GAME/PARAM.SFO` e `PS3_DISC.SFB`;
- pasta com nome arbitrário e metadados válidos;
- ISO válida e ISO corrompida;
- PKG base, patch, DLC, demo e desconhecido;
- PKG com title ID/content ID conflitantes;
- RAP correspondente, ausente e inválido;
- EDAT associado e não associado;
- `PS3UPDAT.PUP` válido, duplicado e inválido;
- EBOOT/SELF/SPRX/PRX ignorados como jogos;
- jogo físico e digital agrupados na mesma obra sem perder media IDs;
- regiões/edições diferentes mantidas separadas;
- duplicata por hash e variante por hash diferente;
- volume removível ausente e reencontrado;
- share de rede com mount point alterado;
- busca de mídia por title ID antes do nome;
- falha de apply preservando fontes e catálogo anterior;
- preflight recusado com causa e próxima ação.

## Resultado esperado

Entregue uma biblioteca PS3 simples para o usuário e rigorosa internamente: uma obra apresentada de forma limpa, variantes físicas e digitais preservadas, firmware e licenças explicitamente diagnosticados, mídia correta, espaço medido e nenhuma dependência das frentes de tema, launcher ou PS4.

