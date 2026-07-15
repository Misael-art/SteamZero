# ADR-0003 — Distribuição híbrida: Flatpak primário + helper host + alternativas nativas

**Status:** aceito (spike de validação na Fase 2 — R-10)

## Contexto
RetroDECK prova o modelo Flatpak-appliance para o domínio (isolamento, updates OSTree com rollback por commit, distro-agnóstico). LinuxToys prova empacotamento multi-formato (deb/rpm/pkgbuild/flatpak/nix). PhaseZero instala no host (Arch-first). Operações privilegiadas (TDP, udev, mounts) não vivem dentro de sandbox.

## Alternativas
1. **Flatpak primário + `steamzero-admin` no host + pacotes nativos/AppImage como alternativas** (escolhida).
2. Só Flatpak — contras: TDP/mounts impossíveis ⇒ produto capado no Deck.
3. Só nativo — contras: N distros × M versões; SteamOS imutável dificulta; perde rollback OSTree.
4. AppImage primário — contras: sem updates transacionais, sandbox fraco.

## Prós
Isolamento por padrão; updates/rollback da plataforma "de graça"; superfície privilegiada mínima e separada; SteamOS-friendly (Flatpak é o mecanismo suportado).

## Contras / Riscos
Complexidade de portais; IPC sandbox↔helper via D-Bus system com policy; instalação em duas partes (Flatpak + helper opcional) — UX de setup deve explicar que o helper é opcional (sem ele: sem TDP/mounts automáticos, resto funciona).

## Decisão
Como acima. Emuladores instalados preferencialmente como Flatpaks --user (fora do nosso sandbox, geridos via portal/flatpak-spawn) e AppImages em `~/Applications`; nunca "emuladores dentro do nosso Flatpak" (diferença deliberada do RetroDECK: componentes independentes, atualizáveis individualmente).

## Consequências
CI produz: Flatpak, pacote do helper (rpm/deb/pkgbuild), AppImage da CLI; matriz de teste inclui as 3 vias.

## Revisão futura
Spike Fase 2: se portais/flatpak-spawn inviabilizarem gestão de Flatpaks user a partir do sandbox ⇒ promover instalação nativa a primária (ADR revisado).
