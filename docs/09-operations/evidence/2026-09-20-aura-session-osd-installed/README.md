# AURA OSD e galeria de saves — release instalada

Esta evidência foi capturada em Wayland na release `2.0.0rc1-3acc2104dd5a`
com o Launcher instalado e o jogo real `Blaster Master (USA) (Translated
PtBr)` iniciado pela rota oficial do Launcher.

Sequência observada:

1. o Launcher abriu o detalhe do jogo e iniciou RetroArch/Mesen;
2. a janela real do jogo ficou visível;
3. a camada AURA exibiu o OSD com `Estado: running`, ações semânticas e foco;
4. `Galeria de saves` abriu e mostrou o fallback honesto `Nenhum save-state foi
   criado para esta sessão`;
5. fechar a galeria/OSD devolveu o detalhe do mesmo jogo;
6. o jogo continuou executando, sem tela preta ou perda do contexto.

O botão `Trocar disco` aparece desabilitado para este título single-disc, como
exige o contrato. Isto não substitui a prova de troca em um jogo multi-disc;
essa lacuna continua registrada separadamente.

Os hashes e o método completo estão em [PHYSICAL-VALIDATION.json](PHYSICAL-VALIDATION.json).
