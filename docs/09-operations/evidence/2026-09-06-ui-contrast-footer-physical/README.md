# UI contrast footer — physical baseline

Esta evidência registra o estado físico antes da ativação da correção do
rodapé handheld.

- Host release observada: `2.0.0rc1-d556f7f5c89b`
- Source commit da release observada: `d556f7f5c89ba78cd274d1147ddac2bbee04fc4a`
- Comando: `steamzero desktop ui`
- PID da janela fotografada: `211013`
- Captura: `01-before-footer-fix.png`
- SHA-256: `26c050fa0d05c53a207b4239a946491cf60d4c8a75443c467f40bd16d55c3172`

O banner de perfil desatualizado está legível. No baseline, os rótulos
`STEAM MENU`, `D-PAD NAVEGAR`, `A SELECIONAR`, `X AÇÃO DE CONTEXTO` e `B VOLTAR`
ficavam com contraste insuficiente contra o fundo escuro do rodapé.

## After instalado

- Release observada: `2.0.0rc1-3cb57f4c1d59`
- Source commit da release: `3cb57f4c1d593915036e8b9eebea5b1f3f79db07`
- PID da janela fotografada: `333301`
- Captura: `02-footer-fixed.png`
- SHA-256: `fbfa837e60e43bffb9a83faa43e1650689a81467c3189c9e868feec4809d9a70`

Na captura after, os rótulos visíveis do rodapé aparecem claros e legíveis
sobre `#080d13`; a correção usa o resolvedor de contraste da UI. O journal da
release terminou em `committed`, com `deploymentHealthy=true`, convergência
idempotente e rollback disponível para `2.0.0rc1-d556f7f5c89b`. Nenhum reboot
ou logout foi executado.
