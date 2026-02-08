# Walking-script

## Hinweise zur Wiedergabe
Einige Spiele (z. B. Minecraft im Vollbildmodus) reagieren nur auf DirectInput-taugliche Backends. Falls `pyautogui` keine Eingaben auslöst, kannst du in `Script/Script.py` auf das `pynput`-Playback umschalten (`USE_PYNPUT_PLAYBACK = True`) oder Windows-spezifische Libraries wie `pywin32`/`pydirectinput` verwenden.
