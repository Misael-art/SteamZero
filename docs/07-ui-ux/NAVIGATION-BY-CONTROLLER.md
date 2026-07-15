# NAVIGATION-BY-CONTROLLER — navegação por controle

## Mapeamento global (imutável entre telas)

| Entrada | Ação |
|---|---|
| A | confirmar/ativar item focado |
| B | voltar (fecha modal → tela anterior → dashboard; nunca sai do app sem confirmação) |
| X | ação contextual secundária (declarada no rodapé) |
| Y | busca (em listas) |
| Menu (☰) | opções da tela |
| View | detalhes/modo avançado do item |
| LB/RB | trocar abas |
| LT/RT | paginação rápida em listas longas |
| L-stick/D-pad | mover foco |
| R-stick | scroll de painel secundário |

## Regras de foco (§12.3)

1. **Foco inicial previsível:** primeira ação primária da tela (nunca "nada focado").
2. **Focus graph explícito:** cada tela declara o grafo (não confiar só em heurística espacial do toolkit); CI testa: todo elemento interativo alcançável, nenhum trap, ciclo consistente.
3. **Sem armadilhas:** modais capturam foco e devolvem ao elemento de origem ao fechar.
4. **Scroll previsível:** item focado sempre visível (scroll-into-view com margem); sem scroll inercial no foco.
5. **Glyphs dinâmicos:** rodapé mostra os botões reais do controle ativo (Xbox/PS/Deck) — layout Nintendo respeita swap A/B do sistema.
6. **Teclado virtual:** campos de texto invocam o teclado (Steam keyboard no Game Mode; Maliit/desktop IME fora — precedente: PhaseZero `pz steamdeck keyboard repair`).
7. **Hold-to-confirm** para ações destrutivas (segurar A 1,5s com anel de progresso) além da frase tipada onde exigido.
8. **Hot-swap:** troca/queda de controle não perde o foco nem cancela modais; reconexão retoma onde estava (F-CT-03).

## Testes

Suíte de navegação automatizada (input sintético): percorrer todas as telas só com D-pad+A+B; asserção de alcançabilidade e de rodapé correto (08-testing/UI-TESTS.md).
