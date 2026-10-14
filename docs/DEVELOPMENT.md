# Development notes

Things that are easy to break and expensive to rediscover.

## Where things live

| Piece | Location |
|---|---|
| **App** (core + modules, the one driving the board) | `app/` — see [`app/README.md`](../app/README.md) |
| User data: profile, tokens, cache, log | `%APPDATA%\TELINHA\` |
| Legacy agent, kept as a fallback | `agent/` |
| Firmware flashed on the board | `firmware/telinha_p4/` |
| Previous generations (JOQUEI, RÉDEA) | `arquivo/` — reference only |
| Packaging experiments (stage 0) | `app/provas/etapa0/RESULTADO.md` |

Pages and buttons live in `%APPDATA%\TELINHA\perfil.json` (schema 2:
`aparencia` / `toque` / `aceso`). `agent/config.json` is imported only on first
launch. App pages (Claude Code, Discord, OBS, soundboard) come from
`app/pacotes/<app>/pacote.json`; a profile page with the same id wins.

## Core idea

The board is dumb. Every pixel is composed on the PC with Pillow
(`app/telinha/arte.py`) and shipped as JPEG. Changing an icon, a color or what a
button does is a profile edit, never a firmware flash.

## Hard rules

1. **Nothing that changes on its own goes into the artwork.** Live text goes to the
   status bar (`{"ev":"barra"}`). Live cards have a fixed id plus a version;
   content-derived ids make the screen flicker. The compositor assigns art ids,
   never a module.
2. **Never type without checking the foreground window.** Every `digitar` action
   carries `exigir` (the expected app in front). Otherwise the text lands in
   whatever app has focus.
3. **Nothing slow in the serial loop.** `ligacao.py` never calls module code:
   actions go to the router's worker pool, art comes from the compositor with a
   deadline, state comes from the collector.
4. **The last chunk is acknowledged after `drawJpg`** (firmware). Before that the
   board is not reading the UART and the next line arrives 15–20 bytes short.
5. **The FQBN must include `ChipVariant=postv3`** (P4 rev v3.2). Without it the
   board boot-loops with `CHIP_LP_WDT_RESET`. `firmware/build.ps1` sets it.
6. **LovyanGFX is patched** in `Bus_DSI.cpp` (DSI PHY clock). Updating the library
   drops the patch and the board aborts in `Bus_DSI.init()`. Details in
   `arquivo/redea/README.md`, rev v3.2 section.
7. **Baud rate stays at 921600.** At 2 Mbps the CH343 bridge corrupts characters.
8. **No unsigned `.exe`.** Windows 11 Smart App Control blocks it. The app runs on
   the signed `python.exe` / `pythonw.exe`.
9. **`pythonw.exe` has no `sys.stdout`** (it is `None`). Guard any
   `sys.stdout.reconfigure`.

## Before calling it done

```powershell
cd app; python -m pytest testes -q     # the whole core against a fake board
cd app; python -m telinha lista        # pages, buttons and art sizes
.\firmware\build.ps1                   # must compile (if firmware changed)
```

## Running

`pythonw -m telinha bandeja` (from `app/`) starts the tray icon, which launches
the core (`python -m telinha rodar`) and restarts it if it crashes. Double-click
the tray icon (or `python -m telinha janela`) to open the editor window. After
changing `app/editor/`, run `npm run build` there. Log at
`%APPDATA%\TELINHA\telinha.log`. Changed code in `app/`? Kill the `telinha rodar`
process and the tray brings it back. Changed only the profile? The board just
needs to send `hello`.
