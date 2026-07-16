# ERROR-UX — experiência de erro (§12.8)

## Anatomia de todo erro exibido

```
[ícone estado]  Título humano                                (código E-…)
O que aconteceu   — 1 frase concreta
Impacto           — o que deixa/deixou de funcionar
[Ação automática já tomada — quando houver: "A versão anterior foi restaurada."]
[Botão: Ação recomendada]   [Botão: outra ação]   [Ver detalhes]  [Exportar diagnóstico]
```

`Ver detalhes` (opt-in) revela: causa provável, operationId, log recortado, link de docs. `Exportar diagnóstico` → SUPPORT-BUNDLE (com preview).

## Textos canônicos (exemplos normativos do §12.8 ↔ códigos)

| Código | Título/frase |
|---|---|
| `E-STORAGE-MISSING` | "O cartão microSD usado por este jogo não foi encontrado." + impacto ("o jogo fica indisponível, nada foi apagado") + ação ("reinsira o cartão" / "migrar para o SSD") |
| `E-COMPONENT-UPDATE-ROLLEDBACK` | "A atualização falhou. A versão anterior foi restaurada." |
| `E-SAVES-CONFLICT` | "Existem dois progressos diferentes deste jogo." + escolha lado a lado com metadados |
| `E-CONTENT-FW-INCOMPAT` | "O firmware selecionado não é compatível com este emulador." |
| `E-STORAGE-SPACE` | "São necessários mais 8,4 GB para concluir a conversão." + botão "liberar espaço" |
| `E-DESKTOP-OWNER-CONFLICT` | "Outro serviço está controlando display ou entrada." + unidade detectada + botão "revisar desativação" quando allowlisted |
| `E-DESKTOP-CONFLICT-RELEASE` | "Não foi possível desativar o serviço por completo." + confirmação de que o SteamZero permaneceu observador e restauração tentada |

## Regras

1. Código sempre visível (discreto) — é o elo usuário↔suporte↔logs.
2. Nunca dois erros empilhados para a mesma causa raiz: o agregador de problemas correlaciona por operationId e mostra 1 card.
3. Erros em lote (200 conversões, 3 falhas): resumo + lista filtrável das falhas, nunca 3 modais.
4. Tom: sem culpa ("não foi possível" em vez de "você fez errado"), sem alarmismo, sem humor em perda de dados.
5. Toda mensagem vem do catálogo i18n (chave = código); UI nunca concatena strings técnicas cruas.
6. Problemas críticos persistentes (rollback-failed) viram card fixo no Dashboard até resolução — não toast efêmero.
