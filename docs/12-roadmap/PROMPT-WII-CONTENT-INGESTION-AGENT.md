# Prompt de execução — Wii sem impacto nas frentes paralelas

Você é o agente responsável por implementar `WII-UNIFIED-CONTENT-INGESTION` no SteamZero.

## Objetivo

Permita que o usuário escolha uma pasta, arquivo, unidade removível ou compartilhamento e obtenha uma biblioteca Wii organizada sem renomear, converter ou instalar conteúdo manualmente.

O runtime é Dolphin, mas todo registro Wii deve declarar `systemId=wii`; GameCube permanece separado por `systemId=gamecube`.

Nome de apresentação:

```text
Título do jogo - Edição [GAME_ID]
```

## Escopo obrigatório

1. Criar identidade Wii por disc ID/title ID, região, edição e source fingerprint.
2. Distinguir Wii de GameCube antes do catálogo e do launch.
3. Reconhecer ISO/GCM, RVZ, WBFS, CISO, GCZ, WIA, NFS, WAD e NAND title.
4. Classificar WAD como conteúdo instalável, nunca como ISO.
5. Separar jogos, canais, WiiWare, Virtual Console, saves, SD, NAND e cache.
6. Implementar RVZ como conversão explicitamente opt-in.
7. Executar RVZ em background com limite de CPU/I/O, pausa durante jogo, cancelamento, retomada e rollback.
8. Manter a fonte original ativa até verify e confirmação do usuário.
9. Reportar source bytes, RVZ estimado, staging, economia, NAND e cache.
10. Resolver mídia por `systemId=wii` + ID interno antes do título.
11. Declarar requisitos de controles e avisar periférico ausente.
12. Criar preflight Dolphin e testes de WAD/NAND, conversão e recuperação.

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
- `src/steamzero/platform_manifests/47-playstation-vita.platform.json`;
- `src/steamzero/platform_manifests/64-playstation-4.platform.json`;
- `src/steamzero/adapters/manifests/rpcs3.adapter.json`;
- `src/steamzero/adapters/manifests/vita3k.adapter.json`;
- `src/steamzero/adapters/manifests/shadps4.adapter.json`.

Não edite `library.py`, `media_registry.py` ou `emulation.py` sem coordenação. Use módulos próprios e handoff de integração.

## Regras RVZ

- RVZ é recomendado, mas nunca automático.
- A conversão exige ação explícita do usuário.
- O jogo continua lançável pela fonte original durante o job.
- Limite CPU/I/O e pause durante jogo ativo.
- Cancelamento remove somente staging incompleto.
- Verify deve validar leitura, metadados e integridade.
- RVZ só vira ativo após verify e confirmação.
- ISO original nunca é apagada automaticamente.
- Remoção posterior da origem é outra operação, com plano próprio.

## Regras gerais

- Scan read-only antes de qualquer instalação ou conversão.
- Não confiar em nomes externos.
- Não extrair ou copiar arquivos grandes durante o scan.
- WAD/NAND possuem fluxo separado de imagem de disco.
- Não substituir NAND inteira automaticamente.
- Não exigir BIOS genericamente para todo jogo Wii.
- Hardlink/reflink somente no mesmo filesystem.
- `ready` exige fonte íntegra e preflight Dolphin.

## Sequência

1. Leia `docs/ACTIVE-WORK.md` e `docs/12-roadmap/WII-CONTENT-INGESTION-AND-MEDIA-PLAN.md`.
2. Crie/assuma workstream próprio.
3. Crie fixtures Wii, GameCube, WAD, NAND, ISO, RVZ e fontes removíveis.
4. Implemente modelo → resolver → conversão RVZ → WAD/NAND → catálogo → mídia.
5. Execute todos os gates do `AGENTS.md`.
6. Não instale nem altere o host nesta etapa.
7. Faça commit isolado e registre o handoff.

## Testes mínimos

- ISO Wii e ISO GameCube corretamente separadas;
- RVZ existente identificado sem reconversão;
- conversão opt-in recusada quando não confirmada;
- plano com espaço temporário e economia;
- conversão pausada durante jogo;
- cancelamento e retomada;
- falha preservando ISO;
- verify inválido impedindo ativação do RVZ;
- WBFS/CISO tratados com semântica própria;
- WAD válido, inválido e de região conflitante;
- NAND ausente, instalada e conflitante;
- save/cache/SD não catalogados como jogo;
- mídia Wii não recebe arte de GameCube;
- volume removível ausente e reencontrado;
- preflight Dolphin recusado com causa acionável.

## Resultado esperado

Uma biblioteca Wii simples para o usuário, econômica quando ele optar por RVZ e sempre fluida: fonte original preservada, conversão de baixa prioridade, rollback seguro, WAD/NAND controlados e nenhuma dependência das frentes de tema, launcher, PS3, PS4 ou Vita.

