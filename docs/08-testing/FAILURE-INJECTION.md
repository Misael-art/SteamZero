# FAILURE-INJECTION — injeção de falhas (§13.3)

Harness: FS de teste dedicado (tmpfs/loopback), rede mockável, processo do núcleo matável em pontos instrumentados ("crash gates" ativados só em build de teste), relógio virtualizável.

| ID | Falha simulada | Técnica | Resultado exigido |
|---|---|---|---|
| FI-01 | Rede interrompida no meio do download | proxy que corta após N bytes | job blocked(network); resume com range + re-hash; nada fora do staging |
| FI-02 | Download parcial/truncado | servidor mock encerra cedo | checksum falha; retry; depois E-SUPPLY-CHECKSUM |
| FI-03 | Arquivo corrompido/payload hostil do provedor | fixture adulterada | rejeição por hash/magic bytes; quarentena quando aplicável |
| FI-04 | Crash do daemon (SIGKILL) em CADA etapa do pipeline | crash gates em scan/plan/backup/stage/apply(entre ações)/verify/activate/test/commit | recovery determinístico: rollback ou roll-forward; journal consistente; AC-TX-02 |
| FI-05 | DNS indisponível | resolver mock NXDOMAIN | igual FI-01; erro claro, não timeout infinito |
| FI-06 | Disco cheio (ENOSPC) durante apply/conversão | quota/loopback pequeno | preflight pega o caso previsível; ENOSPC no meio → stop→rollback→verify |
| FI-07 | microSD removido durante job que escreve nele | unmount forçado do loopback | FM-06: job pausa, volume missing, zero escrita no mountpoint vazio |
| FI-08 | Processo do emulador travado no fechamento | mock que ignora SIGTERM | escalada FM-08; timeline intacta |
| FI-09 | Suspensão no meio de job/da sessão | trigger de pre-suspend sintético | pausa em ponto de segurança; resume correto |
| FI-10 | Queda de energia (poweroff -f da VM) durante escrita | VM kill | configs íntegras (atômico); journal recupera |
| FI-11 | Controle desconectado durante jogo/na UI | uinput remove device | foco preservado; reconexão retoma (F-CT-03) |
| FI-12 | Display sem sinal pós-mudança de modo | mock do adapter display | cadeia de fallback completa até tela interna |
| FI-13 | Symlink malicioso em árvore de ROMs | fixture | E-CONTENT-UNSAFE-PATH; sem travessia |
| FI-14 | JSON/XML/INI inválido (config corrompida) | fixtures fuzzadas | FM-12: backup do corrompido + oferta de restauração; parser nunca crasheia o daemon |
| FI-15 | Lock abandonado (dono morto) | matar dono e reexecutar | lease expira; lock quebrado com registro; sem deadlock |
| FI-16 | Zip bomb (razão de expansão absurda) | fixture 42.zip-like sintética | limite dispara; quarentena; staging limpo |
| FI-17 | Archive com path traversal | fixture `../../…` | rejeição por entrada; nada materializado fora do staging |
| FI-18 | Archive com 1M entradas/profundidade extrema | fixture gerada | limites de contagem/profundidade; erro claro |
| FI-19 | Timeout de conversão (ferramenta pendurada) | mock chdman pendurado | timeout do plano; rollback; original intacto |
| FI-20 | Permissão negada no destino | chmod fixture | preflight detecta; erro com ação; sem estado parcial |

Regra de suíte: cada FI roda nas variantes {SSD, microSD-lento (throttle I/O)} quando fizer sentido, e sempre termina com verificação de: estado consistente + zero temporários órfãos + journal fechado + erro do catálogo.
