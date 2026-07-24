# Auditoria do lote A1–A4

Data: 2026-07-23. Linha auditada: `codex/expansao-master-steamzero`, de
`891ed8d` a `62cb0a4`.

## Rastreabilidade

| WI | Commit | Contrato | Relatório | Estado |
|---|---|---|---|---|
| A1 | `891ed8d` | `feat-playtime-v1` | `WI-A1.md` | `verified-dev` |
| A2 | `e2eb488` | `feat-operation-history-v1` | `WI-A2.md` | `verified-dev` |
| A3 | `340ec5e` | `feat-collection-v1` | `WI-A3.md` | `verified-dev` |
| A4 | `62cb0a4` | `feat-bitrot-v1` | `WI-A4.md` | `verified-dev` |

Cada linha possui schema registrado, golden, testes de domínio, CLI/RPC,
bridge Desktop e projeção QML. A2 fornece rollback contextual às mutações de
A3; A4 é observacional e nunca altera ROMs.

## Gates do lote

- 1.425 testes aprovados na suíte integral;
- cobertura total 85,24%, sem queda abaixo do piso de 85%;
- Ruff, mypy strict em 149 módulos, independência e fronteiras aprovados;
- oito harnesses QML offscreen aprovados em 949×593 e 1280×800;
- nenhum teste ou artefato contém ROM, mídia pessoal ou credencial real;
- nenhuma evidência offscreen foi promovida a `verified-hw`.

## Dependências e destinos

- sessões observadas e interrompidas estão concluídas em A1; screenshot/vSaves
  continua em G5;
- histórico transacional está concluído em A2 e será reutilizado por todos os
  WIs mutáveis seguintes;
- tags, favoritos e regras locais estão concluídos em A3; comunidade permanece
  protegida em B0;
- saúde anti-bitrot está concluída em A4; cascata de exclusão e views de mídia
  permanecem em A7, patches/linhagem em A8 e enriquecimento de
  DLC/firmware/região em A12;
- A5 depende apenas do manifesto de plataformas já entregue por F5 e pode
  prosseguir sem bloquear os destinos acima.

Resultado: lote coerente com o ledger, sem WI verde sem commit, relatório,
contrato e teste correspondente.
