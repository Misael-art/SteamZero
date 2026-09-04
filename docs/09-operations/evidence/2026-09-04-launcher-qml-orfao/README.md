# Launcher: cena `qml6` órfã — validação física — 2026-09-04

Host Valve Jupiter (`misael-jupiter`), KDE/Wayland, sessão real. Release
instalada durante toda a medição: **2.0.0rc1-a44f52964b3e**.

Medição A/B no mesmo compositor, contra o mesmo daemon (`steamzero-core`,
PID 2821424). Só o código do wrapper difere.

## A — release instalada (sem a correção)

```
wrapper steamzero-launcher  pid 3770127  pgid 3770127
filho   qml6                pid 3770181  pgid 3770127   <- mesmo grupo
```

Depois de `kill -TERM 3770127` (o mesmo sinal que o systemd envia):

| Observação | Resultado |
|---|---|
| wrapper | morto |
| filho `qml6` 3770181 | **vivo**, reparentado para o PID 1764 |
| janela `{7c3a5e60…}` | **presente**, título `SteamZero`, `getwindowpid` = 3770181 |

`01-orfa-sobrevive-sem-a-ponte.png` é essa janela. Ela renderiza a biblioteca
inteira — `8016 arquivo(s) · 1119 jogo(s)` no rodapé, anel de foco ciano no
primeiro cartão — e é **indistinguível da UI viva**. Mas a ponte HTTP morreu
junto com o wrapper: nada nela responde. É precisamente esse o defeito.

Foi essa aparência de UI viva que produziu dois diagnósticos errados no item
SZ-AURA-LAUNCHER: as duas janelas coexistindo em 2026-08-27 e, em 2026-09-04,
injeções de teclado entregues à janela órfã.

## B — árvore corrigida

Executada com `PYTHONPATH` apontando para o worktree e a origem impressa em
tempo de execução, para não medir por engano o `src` do checkout principal:

```
src=/mnt/sdcard/Projects/Port_Steam/.claude/worktrees/keen-napier-429bd2/src/steamzero/__init__.py

wrapper python3  pid 3776260  pgid 3776260
filho   qml6     pid 3776276  pgid 3776276   <- grupo PRÓPRIO
```

O grupo próprio já é a correção observável antes mesmo do encerramento.

Depois do mesmo `kill -TERM` no wrapper:

| Observação | Resultado |
|---|---|
| filho `qml6` 3776276 | **morto** (visto como `<defunct>` e depois colhido) |
| janelas com título `SteamZero` | **nenhuma** |
| wrapper | morto após o encerramento do filho |

`02-corrigido-cena-viva.png` é a cena viva antes do sinal;
`03-apos-sigterm-sem-janela.png` é a área de trabalho depois dele.

## Capturas

| Arquivo | Conteúdo |
|---|---|
| `01-orfa-sobrevive-sem-a-ponte.png` | release instalada: janela órfã, wrapper já morto |
| `02-corrigido-cena-viva.png` | árvore corrigida, cena viva sob supervisão |
| `03-apos-sigterm-sem-janela.png` | após o SIGTERM: nenhuma janela do Launcher |

## Fronteira do que está provado

- **Provado no compositor real:** o `qml6` sobrevive ao SIGTERM do wrapper sem a
  correção, segurando uma janela que se passa pela UI; e não sobrevive com ela.
- **Provado por teste:** `tests/integration/test_launcher_child_lifetime.py`
  cobre SIGTERM e SIGINT pelo caminho real de `launch_launcher_ui`.
- **Não provado:** SIGKILL no próprio wrapper. Está fora de alcance de qualquer
  processo — nenhum código pode rodar depois dele. Fica como limite conhecido.
- **Não provado na release:** a correção foi medida na árvore, contra o daemon
  da release instalada. Confirmá-la na release exige publicação e instalação
  autorizadas, que esta sessão não tem.
