# LICENSE-MATRIX — matriz de licenças

(Cobre também o artefato citado em §7 como `docs/legal/LICENSE-MATRIX.md`.)

## Projetos-fonte

| Projeto | Licença | Evidência | Cópia literal permitida? | Condições |
|---|---|---|---|---|
| EmuDeck | GPL-3.0 | `reference/EmuDeck/LICENSE` (GPLv3 íntegra) | Sim, **se** o Unified for GPL-3.0-compatível | manter copyright, disponibilizar fonte, licenciar derivado sob GPLv3 |
| LinuxToys | GPL-3.0 | `reference/linuxtoys/LICENSE` | idem | idem |
| RetroDECK | GPL-3.0 + avisos de terceiros | `reference/RetroDECK/LICENSE` + `other_licenses.txt` | idem | idem + repassar avisos de terceiros aplicáveis |
| RetroDECK/components | GPL-3.0 (LICENSE na raiz do repo) | árvore via API | idem | atenção: recipes empacotam projetos upstream com licenças próprias |
| PhaseZero | **sem arquivo LICENSE** (all rights reserved por default; titular = autor do repo) | ausência verificada (`ls LICENSE*` vazio; README sem cláusula) | Depende de Q2/Q3 | recomendação: titular adiciona licença explícita antes do reuso formal |

## Componentes que a plataforma instalará (não são copiados, são obtidos)

Cada adapter registra `license` no manifesto (obrigatório — ADAPTER-MODEL). Exemplos: RetroArch GPLv3, Dolphin GPLv2+, DuckStation (CC-BY-NC-ND a partir de 2024 — **atenção**: proíbe redistribuição de derivados; instalar do upstream é ok, redistribuir binário no lockfile NÃO), PCSX2 GPLv3, RPCS3 GPLv2, MAME GPLv2+/BSD-3, ES-DE MIT, SRM GPLv3. Inventário fino por componente será validado na Fase 4 antes de cada adapter entrar no lockfile (o exemplo DuckStation mostra por que: mudanças de licença upstream acontecem).

## Compatibilidade entre licenças (cenário recomendado: Unified = GPL-3.0-or-later)

| Combinação | Veredito |
|---|---|
| GPL-3.0 (3 projetos) → Unified GPL-3.0-or-later | ✔ compatível |
| PhaseZero (proprietário do mesmo titular) → Unified | ✔ se o titular relicenciar/dual-licenciar seu próprio código |
| Código GPL copiado ↔ pedaços proprietários no mesmo binário | ✖ — se Q2 escolher licença fechada, **zero cópia** dos três projetos (só reimplementação por comportamento, ver REUSE-POLICY) |
| Assets (ícones/artes) dos projetos | ✖ por padrão — licenças de assets não inventariadas (G7); não redistribuir |
| Marcas/nomes ("EmuDeck", "RetroDECK", "LinuxToys") | ✖ — nomes e logos não são licenciados pela GPL; não usar no produto (Q1) |

## Bloqueio operativo

Até Q2 estar decidida e registrada em ADR-0013: **nenhuma linha de código dos quatro projetos entra no Unified** (a Fase 0 não copia nada — apenas documenta comportamento, o que é legalmente seguro).
