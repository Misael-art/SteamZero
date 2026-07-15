# QAM-INTEGRATION — integração com o Quick Access Menu (opcional)

## Postura

O QAM (via Decky Loader) é um **adapter opcional de conveniência**. Precedente direto: PhaseZero trata Decky como opt-in (`linux/steamdeck/install-plugins.sh`) e conversa via WebSocket (`decky-ws-client.py`). Regra do produto: **zero lógica crítica no plugin** (§12.2) e **zero dependência** (P9, ADR-0008).

## Superfície do plugin (fina)

O plugin é um cliente da API local com escopo restrito (AUTHORIZATION-MODEL §2):
- Save rápido (checkpoint do jogo em execução) / restore rápido (última entrada da timeline).
- Trocar perfil de desempenho (dos perfis já definidos).
- Status de sync (somente leitura) · estado de controle/áudio/tela do modo atual.
- Diagnóstico contextual: "algo errado com este jogo?" → deep-link para a Game Mode UI.

## Degradação

Decky ausente/quebrado (FM-11): healthcheck marca QAM `unavailable`; as mesmas ações continuam disponíveis por: Game Mode UI (aberta como jogo/atalho), hotkeys de controle (ações semânticas), CLI e notificações do sistema. A UI informa uma única vez ("O menu rápido está indisponível após a atualização do Steam; suas funções continuam em <lugar>").

## Compatibilidade

O plugin declara versão de contrato; a Compat Matrix registra {SteamOS, Steam Client, Decky, plugin} testados (FM-10/§11.5); plugin desatualizado = desativado com aviso, nunca meio-funcionando.
