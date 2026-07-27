# Runbook: Experiência do Modo Desktop — toque, OSK e atalhos

Este documento é para o operador instalar e validar no hardware as mudanças
de desktop experience. O agente entrega código, testes e runbook; a execução
física e build/release são responsabilidade do operador (Regras 1 e 4 do
AGENTS.md).

## Pré-requisitos no host

- Steam Deck (LCD/OLED) com BigLinux/Plasma Wayland.
- Pacotes do host: `kwriteconfig6`, `qdbus6`, `wvkbd-mobintl`, `steam`.
- KDE Shortcuts habilitado (`kglobalaccel` ativo na sessão Plasma).

## Build e release

O operador executa o fluxo de release vigente (pip wheel + manifesto +
wheelhouse). O agente não constrói release.

```bash
# Exemplo do fluxo; ajuste para o toolchain atual do projeto.
make check
python -m build --wheel
# sincronizar wheelhouse e manifesto conforme processo vigente
```

## Instalação

```bash
sudo ./tools/install_host.py install
```

Se o caminho do instalador for outro, use o vigente no ambiente.

## Verificação por item

### 1. OSK standalone (wvkbd)

1. Garanta que `maliit-keyboard` e a Steam não estão rodando ou que seus
   providers falham.
2. Execute:
   ```bash
   steamzero desktop keyboard
   ```
3. **Esperado:** `wvkbd-mobintl --daemon` abre o teclado virtual.
4. Se `wvkbd` não estiver instalado, instale pelo repositório do host e repita.

### 2. Atalhos KDE globais

Após aplicar um perfil Desktop (`steamzero desktop plan --profile handheld`
seguido de `apply` na UI/CLI), teste:

| Atalho | Ação esperada |
|---|---|
| `Meta+Ctrl+K` | Abrir teclado virtual (`steamzero desktop keyboard`) |
| `Meta+Ctrl+D` | Overview / Exposição de todas as áreas de trabalho |
| `Meta+Ctrl+L` | Bloquear sessão |
| `Meta+D` | Mostrar área de trabalho |

Se algum atalho não funcionar, verifique `~/.config/kglobalshortcutsrc` e se
`kglobalaccel` foi reconfigurado (`qdbus6 org.kde.kglobalaccel /kglobalaccel reconfigure`).

### 3. UX de toque / OSK auto-show

1. Aplique um perfil com `touchMode=true` (handheld).
2. Na UI do SteamZero, focalize um `TextField` editável (ex.: frase de
   confirmação de manutenção).
3. **Esperado:** se um IM module (Maliit) estiver ativo, o OSK aparece
   automaticamente. Se não houver IM module, o atalho `Meta+Ctrl+K` ou o
   botão "Abrir teclado" ainda funcionam.

### 4. Botões físicos do Deck

1. Execute:
   ```bash
   steamzero desktop status
   # ou
   steamzero doctor
   ```
2. Verifique o campo `deckInputKeys`.
3. **Se `true`:** os botões do Deck chegam como teclas e os atalhos KDE
   devem funcionar.
4. **Se `false`:** registre no WORKLOG. Os atalhos KDE não funcionarão com
   os botões físicos; o caminho futuro é InputPlumber (decisão adiada).

## Rollback

Para restaurar o snapshot de `kglobalshortcutsrc` e `kwinrc`:

```bash
steamzero desktop recover
```

Verifique que os atalhos voltaram aos valores anteriores e que
`~/.local/share/applications/steamzero-desktop-keyboard.desktop` foi removido
se o efeito o criou.

## Critério de aceitação no hardware

Aceite quando os 3 itens funcionais (OSK, atalhos, toque) estiverem
validados no Deck físico **OU** quando qualquer falha estiver registrada
como `degraded` e causa clara no WORKLOG.

## Captura de evidência

Anexe ao WORKLOG a saída de:

```bash
steamzero doctor
```

Inclua também a saída de:

```bash
steamzero desktop status
```

para registrar `deckInputKeys` e o estado truth no hardware real.
