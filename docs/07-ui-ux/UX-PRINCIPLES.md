# UX-PRINCIPLES

U1. **Traduzir, não expor.** A UI converte `erro técnico → significado → impacto → ação recomendada → correção → detalhes opcionais` (§12.1). O usuário P1 nunca precisa entender "checksum mismatch"; o P2 encontra tudo em "detalhes".

U2. **Confiança por transparência, não por esconder.** Antes de mudar algo: o que será feito, quanto espaço, o que é reversível (plano/preview sempre visível). Depois: o que foi feito, onde está o backup.

U3. **Estado do sistema sempre visível e verdadeiro.** Dashboard reflete o State Store verificado (P10): "pronto para jogar" significa BIOS ok + emulador ok + storage presente + save acessível.

U4. **Nada de becos.** Toda tela tem saída por B; toda operação longa tem cancelamento seguro; todo erro tem pelo menos uma ação (nem que seja "exportar diagnóstico").

U5. **O controle é o cidadão de primeira classe** (NAVIGATION-BY-CONTROLLER). Mouse/teclado são bem-vindos no Desktop Mode, nunca exigidos no Game Mode.

U6. **Progressive disclosure.** Instalação padrão = 3 decisões (onde, o quê, confirmar). Cada tela avançada é opt-in. Modo avançado global habilita densidade extra para P2.

U7. **Linguagem:** pt-BR/en desde o início (chaves i18n); frases curtas; sem jargão por padrão; terminologia consistente com o GLOSSARY (nunca "flush do save" na UI — "salvando com segurança").

U8. **Nunca punir o hábito de console.** Desligar "no meio" não pode custar dados (checkpoints); remover cartão não pode custar biblioteca (estados `unavailable`).

U9. **Feedback em ≤100ms** para navegação; operações >1s viram jobs com progresso honesto (P11); >10s são canceláveis e pausáveis.

U10. **Acessibilidade não é modo** — escala, contraste e redução de movimento são parte do design base (ACCESSIBILITY.md).
