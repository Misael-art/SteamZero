# Prompt de execução — GameCube sem impacto nas frentes paralelas

Você é o agente responsável por implementar `GAMECUBE-UNIFIED-CONTENT-INGESTION` no SteamZero.

## Objetivo

Permita que o usuário escolha uma pasta, arquivo, unidade removível ou compartilhamento e obtenha uma biblioteca GameCube organizada sem renomear, converter ou instalar conteúdo manualmente.

O runtime é Dolphin, mas todo registro GameCube deve declarar `systemId=gamecube`; Wii permanece separado por `systemId=wii`.

Nome de apresentação:

```text
Título do jogo - Edição [GAME_ID]
```

## Escopo obrigatório

1. Criar identidade GameCube por Game ID, região, edição e source fingerprint.
2. Distinguir GameCube de Wii antes do catálogo e do launch.
3. Reconhecer ISO/GCM, RVZ, GCZ, CISO, WIA, DOL e ELF.
4. Classificar DOL/ELF sem identidade comercial como homebrew/executável.
5. Rejeitar WAD, NFS, WiiWare, Virtual Console e NAND como GameCube sem prova interna.
6. Agrupar jogos multi-disc em um conjunto lógico único.
7. Implementar RVZ como conversão explicitamente opt-in.
8. Executar RVZ em background com limite de CPU/I/O, pausa durante jogo, cancelamento, retomada e rollback.
9. Manter a fonte original ativa até verify e confirmação do usuário.
10. Reportar fonte, staging, economia, cache e tempo estimado.
11. Resolver mídia por `systemId=gamecube` + Game ID.
12. Criar preflight Dolphin e testes de multi-disc, conversão e recuperação.

## Ownership proibido

Não altere:

- `src/steamzero/ui/qml/**`;
- `src/steamzero/ui/assets/**`;
- `src/steamzero/domain/scene_esde.py`;
- `src/steamzero/domain/theme_*.py`;
- `src/steamzero/adapters/desktop_dashboard.py`;
- `src/steamzero/launcher/**`;
- `src/steamzero/adapters/launcher_*.py`;
- `src/steamzero/platform_manifests/35-wii-u.platform.json`;
- `src/steamzero/platform_manifests/36-playstation-3.platform.json`;
- `src/steamzero/platform_manifests/47-playstation-vita.platform.json`;
- `src/steamzero/platform_manifests/64-playstation-4.platform.json`;
- `src/steamzero/adapters/manifests/rpcs3.adapter.json`;
- `src/steamzero/adapters/manifests/vita3k.adapter.json`;
- `src/steamzero/adapters/manifests/shadps4.adapter.json`.

O manifesto Nintendo Console é compartilhado com Wii. Não o altere diretamente sem coordenação do integrador. Não edite `library.py`, `media_registry.py` ou `emulation.py` sem ownership explícito.

## Regras RVZ

- RVZ é recomendado, mas nunca automático.
- Conversão exige ação explícita do usuário.
- O jogo continua lançável pela fonte original durante o job.
- Limite CPU/I/O e pause durante jogo ativo.
- Cancelamento remove somente staging incompleto.
- Verify valida leitura, metadados e integridade.
- RVZ só vira ativo após verify e confirmação.
- ISO original nunca é apagada automaticamente.
- Remoção posterior da origem é operação separada.

## Regras gerais

- Scan read-only antes de conversão.
- Não confiar em nomes externos.
- Não extrair ou copiar arquivos grandes durante scan.
- Multi-disc não pode criar jogos duplicados.
- Não exigir BIOS genericamente para jogos GameCube.
- Hardlink/reflink somente no mesmo filesystem.
- `ready` exige fonte íntegra e preflight Dolphin.

## Sequência

1. Leia `docs/ACTIVE-WORK.md` e `docs/12-roadmap/GAMECUBE-CONTENT-INGESTION-AND-MEDIA-PLAN.md`.
2. Crie/assuma workstream próprio.
3. Crie fixtures GameCube, Wii, multi-disc, ISO, RVZ, homebrew e fontes removíveis.
4. Implemente modelo → resolver → multi-disc → conversão RVZ → catálogo → mídia.
5. Execute todos os gates do `AGENTS.md`.
6. Não instale nem altere o host nesta etapa.
7. Faça commit isolado e registre o handoff.

## Testes mínimos

- ISO GameCube e ISO Wii separadas corretamente;
- RVZ existente identificado sem reconversão;
- conversão opt-in recusada sem confirmação;
- plano com espaço temporário, economia e tempo;
- conversão pausada durante jogo;
- cancelamento e retomada;
- falha preservando ISO;
- verify inválido impedindo ativação do RVZ;
- WBFS/NFS/WAD recusados como GameCube sem prova interna;
- DOL/ELF classificados como homebrew;
- multi-disc agrupado em um jogo;
- mídia GameCube não recebe arte Wii;
- volume removível ausente e reencontrado;
- preflight Dolphin recusado com causa acionável.

## Resultado esperado

Uma biblioteca GameCube simples, econômica quando o usuário optar por RVZ e sempre fluida: fonte original preservada, conversão de baixa prioridade, multi-disc coerente, mídia correta e nenhuma dependência das frentes de tema, launcher, Wii, PS3, PS4 ou Vita.

