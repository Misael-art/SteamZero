# UI contrast footer — physical baseline

Esta evidência registra o estado físico antes da ativação da correção do
rodapé handheld.

- Host release observada: `2.0.0rc1-d556f7f5c89b`
- Source commit da release observada: `d556f7f5c89ba78cd274d1147ddac2bbee04fc4a`
- Comando: `steamzero desktop ui`
- PID da janela fotografada: `211013`
- Captura: `01-before-footer-fix.png`
- SHA-256: `26c050fa0d05c53a207b4239a946491cf60d4c8a75443c467f40bd16d55c3172`

O banner de perfil desatualizado está legível. Os rótulos `STEAM MENU`,
`D-PAD NAVEGAR`, `A SELECIONAR`, `X AÇÃO DE CONTEXTO` e `B VOLTAR` ficam com
contraste insuficiente contra o fundo escuro do rodapé. A correção já está
mergeada em `main` no commit `3cb57f4c1d593915036e8b9eebea5b1f3f79db07`, mas
o after ainda não pode ser carimbado: a ativação governada ficou aguardando
autenticação do agente Polkit do KDE. Nenhum reboot ou logout foi executado.
