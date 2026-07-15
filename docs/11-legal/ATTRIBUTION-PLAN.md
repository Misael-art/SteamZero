# ATTRIBUTION-PLAN — plano de atribuição

## Quando o Unified reusar/derivar (condicionado a Q2 = GPL-3.0-or-later)

1. `NOTICE`/`CREDITS.md` na raiz com seção por projeto-fonte: nome, URL, licença, o que foi derivado (por diretório/arquivo), copyright holders originais.
2. Cabeçalho SPDX em todo arquivo: `SPDX-License-Identifier: GPL-3.0-or-later`; arquivos derivados adicionam `Derived from <projeto> (<arquivo>@<commit>), Copyright (c) <holders>`.
3. Reimplementações independentes (sem cópia) registram: "capability inspired by <projeto>; implemented independently" — em `docs/adr` ou no CREDITS (transparência sem implicar derivação).
4. Templates de configuração adaptados do EmuDeck (`configs/`): tratados como código GPL — mesma atribuição.
5. UI "Sobre": créditos aos quatro projetos e aos emuladores/ferramentas instalados (com licenças), no padrão RetroDECK (`retrodeck_credits`).
6. Nomes/logos de terceiros nunca aparecem como identidade do produto; apenas em créditos e em contexto factual ("importar de uma instalação EmuDeck").
7. Manter `THIRD-PARTY-NOTICES.md` gerado a partir do SBOM em cada release (automatizado no CI).
