# AURA — troca de disco no Launcher instalado

Esta evidência repete o ciclo multidisco na release instalada
`2.0.0rc1-7af569b5fbba`, construída do commit
`7af569b5fbba906404d822192077a31890e29b07`, usando o descritor M3U gerenciado
de Street Fighter II e quatro ADFs derivados de fonte local do host.

O bridge do Launcher criou uma sessão real do PUAE e publicou quatro IDs
persistentes:

`amiga:street-fighter-ii-world-warrior:1992:disc-1..4`

O read model confirmou `activeDisc: 0`; as operações de sessão confirmaram a
troca para o disco 2 (`activeDisc: 1`) e o retorno ao disco 1 (`activeDisc: 0`).
O processo observado foi RetroArch Flatpak 1.22.2 com PUAE 5.3.0 e Kickstart
A1200. O conteúdo original não foi alterado.

As capturas são deliberadamente honestas:

- `01-baseline.png`: central AURA em fullscreen antes do lançamento.
- `02-entrega-funcional.png`: janela real do RetroArch/PUAE com o bezel AURA;
  o frame do jogo permaneceu cinza nesta fixture e não é apresentado como
  renderização de jogo confirmada.
- `03-recuperacao.png`: retorno ao contexto de detalhes do Launcher.

O caminho de UI também foi exercitado: exibiu “Preparando” e, em uma segunda
tentativa, apresentou o erro controlado `LAUNCHER-LAUNCH-FAILED-001` quando o
PUAE encerrou. Não houve tela preta nem reinício do KDE. A troca de disco foi
validada pelo contrato HTTP do Launcher instalado, enquanto a abertura visual
do OSD pela UI permanece dependente de uma sessão que mantenha o processo do
PUAE vivo.
