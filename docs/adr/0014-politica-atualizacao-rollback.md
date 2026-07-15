# ADR-0014 — Política de atualização e rollback (plataforma e componentes)

**Status:** aceito

## Contexto
§10.1/§15/§11.5. RetroDECK atualiza como appliance (tudo junto); EmuDeck atualiza componentes resolvendo latest (sem pin, sem volta). Nenhum tem rollback de componente.

## Alternativas
1. **Componentes independentes com lockfile por canal + updates transacionais com rollback; plataforma com update transacional próprio (OSTree quando Flatpak)** (escolhida).
2. Appliance total (RetroDECK-style) — prós: matriz de teste pequena; contras: atualizar um emulador = atualizar tudo; contradiz adapters independentes.
3. Latest contínuo (EmuDeck-style) — contras: irreproduzível, quebra sem volta (anti-requisito).

## Decisão
Canais conforme RELEASE-CHANNELS; componente: update = transação com backup da versão anterior + verify + smoke test, rollback automático em falha e manual sob demanda (janela de retenção); plataforma: UPDATE-AND-ROLLBACK.md; nunca auto-update durante gameplay/bateria baixa; consentimento no stable.

## Consequências
Lockfile testado em conjunto é artefato de release; espaço de retenção gerenciado por GC com política.
Flatpak usa `G-DEPLOYMENT`: o snapshot anterior congela remote+commit, sua disponibilidade
é verificada no planejamento e rollback reaplica esse commit. Instalação nova é revertida
sem `--delete-data`; runtimes baixados podem ficar para GC. Intent durável permite recovery
após crash antes do commit lógico. Isso não é `G-FULL` do repositório OSTree nem dos dados
do aplicativo, distinção mostrada no preview.

## Revisão
Cadência (Q10) na aprovação; telemetria zero significa que regressões chegam por relatos — reforçar canal beta.
