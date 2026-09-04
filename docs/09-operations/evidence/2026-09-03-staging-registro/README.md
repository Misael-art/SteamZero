# Registro da operação de tema no banco — 2026-09-03

Validação física na release `2.0.0rc1-ba79eaae8d82`, instalada pelo fluxo
governado a partir do commit `ba79eaae` com CI verde no run `33823773463`.
Toda medição saiu do pacote em `/opt/steamzero/current/venv`.

## O defeito

O staging que guarda o `previous-theme.json` não tinha linha na tabela
`operation`. Consequência: `state_audit` o classificava como órfão, o doctor
avisava, e o **`state cleanup-plan` o listava para quarentena**. Quem
reinstalasse um tema e rodasse a limpeza governada perderia o desfazer, sem
nenhum aviso de que aquele diretório tinha dono.

Baseline medido no host **antes** da correção, sob a release
`2.0.0rc1-03fed007d1f0`:

```
itens: 1 | bytes: 122349
   staging 01M1MVR99JYX492AC41HAES91A  122349
```

122 KB de dado de rollback vivo, prestes a ser removido.

## A prova, com os dois lados declarados antes do resultado

O critério foi fixado antes de medir, para não ser ajustado depois:

| Item | Esperado | Observado |
|---|---|---|
| Staging **novo**, criado sob o código corrigido (`01M1MZDC85…`) | ausente do plano | **ausente** |
| Staging **antigo**, criado sob o código velho (`01M1MVR99J…`) | presente | **presente** |

O segundo lado importa tanto quanto o primeiro. Um plano vazio de imediato
seria motivo de desconfiança, não de comemoração: significaria que algo removeu
dado de rollback existente. A correção não adota resíduo retroativamente.

## Ciclo completo na release instalada

| Passo | Resultado |
|---|---|
| Reinstalar `org.esde.nso-menu` | `replaced: true`, staging com `previous-theme.json` |
| `cleanup-plan` | 1 item, e **não é** o novo |
| `theme.catalog.rollback` | `restoredPrevious: true`, `assetsPreserved: true` |
| Staging depois do rollback | removido; sobra só o resíduo antigo |
| Manifesto | restaurado, tema segue instalado |

Verificado por três vias deliberadamente redundantes — inspeção direta do
disco, `doctor` e `cleanup-plan`. O `cleanup` é justamente o mecanismo que
destruiria o dado, então prová-lo apenas pelo veredito de um componente vizinho
seria fraco.

## O resíduo antigo ficou, de propósito

`01M1MVR99JYX492AC41HAES91A` continua no disco e no plano de limpeza. Ele é um
`previous-theme.json` **válido**: um operador ainda pode desfazer aquela
reinstalação por ele. Colocá-lo em quarentena por conveniência estatística
seria cometer, à mão, exatamente o defeito que este commit corrige.

Fica como decisão do operador, não do agente.

## Ressalva sobre uma limpeza anterior

Mais cedo neste mesmo dia eu apliquei `state cleanup-apply` sobre quatro
diretórios órfãos. Todos tinham 0 bytes e nada se perdeu — mas eu havia
conferido o **tamanho**, não a **função**. Sob o defeito descrito aqui, um
diretório com rollback vivo teria ido junto. Foi sorte, não cuidado.

## O que esta evidência NÃO prova

- Nada sobre a aparência da central: `GAP-THEME-ESDE-SCENE-NOT-RENDERED` segue
  aberta.
- `doctor` continua `degraded`, por este resíduo e por `boot.direct: unknown`,
  este último por falta de permissão de inspeção e pré-existente.
- Nada foi medido em FPS, GPU ou memória.
