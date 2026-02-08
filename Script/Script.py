import json
import threading
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import pyautogui
import tkinter as tk
from pynput import keyboard, mouse

# ===== Einstellungen =====
RECORD_HOTKEY = keyboard.Key.f8
PLAY_HOTKEY = keyboard.Key.f9
SAVE_HOTKEY = keyboard.Key.f10
LOAD_HOTKEY = keyboard.Key.f11
EXIT_HOTKEY = keyboard.Key.esc
DEFAULT_FILE = "macro_minecraft.json"
HOTKEYS = {RECORD_HOTKEY, PLAY_HOTKEY, SAVE_HOTKEY, LOAD_HOTKEY, EXIT_HOTKEY}
# Hinweis: Manche Spiele (z. B. Minecraft im Vollbild) reagieren nur auf DirectInput-taugliche Backends.
# Wenn pyautogui nicht zuverlässig ist, teste USE_PYNPUT_PLAYBACK oder Windows-spezifische Libraries.
USE_PYNPUT_PLAYBACK = False

# Optional: tiny pause reduction to smooth playback
MIN_SLEEP = 0.0005

# pyautogui failsafe ggf. aus, damit Maus an Ecke nicht stoppt
pyautogui.FAILSAFE = False


@dataclass
class Event:
    t: float                    # Zeit seit Aufnahmebeginn in Sekunden
    etype: str                  # "key_down", "key_up", "mouse_move", "mouse_down", "mouse_up", "scroll"
    key: Optional[str] = None   # z.B. "w", "Key.space"
    button: Optional[str] = None  # "left", "right", "middle"
    x: Optional[int] = None
    y: Optional[int] = None
    dx: Optional[int] = None
    dy: Optional[int] = None


class MacroRecorderPlayer:
    def __init__(self):
        self.recording = False
        self.playing = False
        self.start_time = 0.0
        self.events: List[Event] = []
        self.lock = threading.Lock()

        self.k_listener: Optional[keyboard.Listener] = None
        self.m_listener: Optional[mouse.Listener] = None
        self.keyboard_controller = keyboard.Controller()
        self.mouse_controller = mouse.Controller()

        # Beim Abspielen ignorieren wir eingehende Input-Events
        self.ignore_input = False

    def event_count(self) -> int:
        with self.lock:
            return len(self.events)

    def get_status(self) -> str:
        if self.recording:
            return "Recording..."
        if self.playing:
            return "Playing..."
        return "Idle"

    # ---------- Hilfsfunktionen ----------
    def _now(self) -> float:
        return time.perf_counter()

    def _rel_time(self) -> float:
        return self._now() - self.start_time

    @staticmethod
    def _key_to_str(k: Any) -> str:
        # keyboard.KeyCode(char='w') => 'w'
        # keyboard.Key.space => 'Key.space'
        if isinstance(k, keyboard.KeyCode):
            return k.char if k.char is not None else str(k)
        return f"Key.{k.name}" if isinstance(k, keyboard.Key) else str(k)

    @staticmethod
    def _str_to_key(s: str) -> Any:
        # 'w' -> 'w' (pyautogui key string)
        # 'Key.space' -> 'space'
        if s.startswith("Key."):
            return s.replace("Key.", "")
        return s

    @staticmethod
    def _button_to_str(btn: mouse.Button) -> str:
        return btn.name

    @staticmethod
    def _str_to_button(name: str) -> str:
        # pyautogui nutzt "left"/"right"/"middle"
        return name

    @staticmethod
    def _str_to_pynput_key(s: str) -> Any:
        if s.startswith("Key."):
            key_name = s.replace("Key.", "")
            return getattr(keyboard.Key, key_name, None) or keyboard.KeyCode.from_char(key_name)
        return keyboard.KeyCode.from_char(s)

    @staticmethod
    def _str_to_pynput_button(name: str) -> mouse.Button:
        return getattr(mouse.Button, name)

    def _append_event(self, ev: Event):
        with self.lock:
            self.events.append(ev)

    # ---------- Aufnahme ----------
    def start_recording(self):
        if self.playing:
            print("[!] Kann nicht aufnehmen während Wiedergabe läuft.")
            return
        self.recording = True
        self.start_time = self._now()
        with self.lock:
            self.events.clear()
        print("[REC] Aufnahme gestartet.")

    def stop_recording(self):
        self.recording = False
        print(f"[REC] Aufnahme gestoppt. Events: {len(self.events)}")

    # ---------- Datei ----------
    def save_events(self, filename: str = DEFAULT_FILE):
        with self.lock:
            data = [asdict(e) for e in self.events]
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[SAVE] Gespeichert: {filename} ({len(data)} Events)")

    def load_events(self, filename: str = DEFAULT_FILE):
        with open(filename, "r", encoding="utf-8") as f:
            raw = json.load(f)
        with self.lock:
            self.events = [Event(**item) for item in raw]
        print(f"[LOAD] Geladen: {filename} ({len(self.events)} Events)")

    # ---------- Wiedergabe ----------
    def play(self):
        if self.recording:
            print("[!] Stoppe erst die Aufnahme (F8), dann abspielen.")
            return
        with self.lock:
            if not self.events:
                print("[!] Keine Events vorhanden.")
                return
            events_copy = list(self.events)

        if self.playing:
            print("[!] Wiedergabe läuft bereits.")
            return

        def _run():
            self.playing = True
            self.ignore_input = True
            print("[PLAY] Wiedergabe gestartet.")
            t0 = self._now()
            last_t = 0.0

            try:
                for ev in events_copy:
                    if not self.playing:
                        break

                    wait = ev.t - last_t
                    if wait > 0:
                        time.sleep(max(wait, MIN_SLEEP))
                    last_t = ev.t

                    if ev.etype == "key_down":
                        key = self._str_to_key(ev.key or "")
                        if USE_PYNPUT_PLAYBACK:
                            pynput_key = self._str_to_pynput_key(ev.key or "")
                            self.keyboard_controller.press(pynput_key)
                        else:
                            pyautogui.keyDown(key)
                    elif ev.etype == "key_up":
                        key = self._str_to_key(ev.key or "")
                        if USE_PYNPUT_PLAYBACK:
                            pynput_key = self._str_to_pynput_key(ev.key or "")
                            self.keyboard_controller.release(pynput_key)
                        else:
                            pyautogui.keyUp(key)
                    elif ev.etype == "mouse_move":
                        if ev.x is not None and ev.y is not None:
                            if USE_PYNPUT_PLAYBACK:
                                self.mouse_controller.position = (ev.x, ev.y)
                            else:
                                pyautogui.moveTo(ev.x, ev.y)
                    elif ev.etype == "mouse_down":
                        if ev.button and ev.x is not None and ev.y is not None:
                            if USE_PYNPUT_PLAYBACK:
                                self.mouse_controller.position = (ev.x, ev.y)
                                self.mouse_controller.press(self._str_to_pynput_button(ev.button))
                            else:
                                pyautogui.mouseDown(x=ev.x, y=ev.y, button=self._str_to_button(ev.button))
                    elif ev.etype == "mouse_up":
                        if ev.button and ev.x is not None and ev.y is not None:
                            if USE_PYNPUT_PLAYBACK:
                                self.mouse_controller.position = (ev.x, ev.y)
                                self.mouse_controller.release(self._str_to_pynput_button(ev.button))
                            else:
                                pyautogui.mouseUp(x=ev.x, y=ev.y, button=self._str_to_button(ev.button))
                    elif ev.etype == "scroll":
                        # pyautogui.scroll: positive up, negative down
                        if USE_PYNPUT_PLAYBACK:
                            self.mouse_controller.scroll(ev.dx or 0, ev.dy or 0)
                        else:
                            pyautogui.scroll(ev.dy or 0, x=ev.x, y=ev.y)
            finally:
                self.playing = False
                self.ignore_input = False
                print("[PLAY] Wiedergabe beendet.")

        threading.Thread(target=_run, daemon=True).start()

    def stop_play(self):
        if self.playing:
            self.playing = False
            print("[PLAY] Stop-Signal gesendet.")

    # ---------- Listener Callbacks ----------
    def on_key_press(self, key):
        if key == EXIT_HOTKEY:
            # ESC: falls playing -> stop; sonst exit
            if self.playing:
                self.stop_play()
            else:
                print("[EXIT] Beende...")
                self.stop_all()
            return

        if self.ignore_input:
            return

        # Hotkeys global
        if key == RECORD_HOTKEY:
            if not self.recording:
                self.start_recording()
            else:
                self.stop_recording()
            return
        if key == PLAY_HOTKEY:
            self.play()
            return
        if key == SAVE_HOTKEY:
            self.save_events(DEFAULT_FILE)
            return
        if key == LOAD_HOTKEY:
            try:
                self.load_events(DEFAULT_FILE)
            except Exception as e:
                print(f"[LOAD] Fehler: {e}")
            return

        if key in HOTKEYS:
            return

        if self.recording:
            self._append_event(Event(t=self._rel_time(), etype="key_down", key=self._key_to_str(key)))

    def on_key_release(self, key):
        if self.ignore_input:
            return
        if key in HOTKEYS:
            return
        if self.recording:
            self._append_event(Event(t=self._rel_time(), etype="key_up", key=self._key_to_str(key)))

    def on_mouse_move(self, x, y):
        if self.ignore_input:
            return
        if self.recording:
            self._append_event(Event(t=self._rel_time(), etype="mouse_move", x=int(x), y=int(y)))

    def on_mouse_click(self, x, y, button, pressed):
        if self.ignore_input:
            return
        if self.recording:
            etype = "mouse_down" if pressed else "mouse_up"
            self._append_event(
                Event(
                    t=self._rel_time(),
                    etype=etype,
                    button=self._button_to_str(button),
                    x=int(x),
                    y=int(y),
                )
            )

    def on_mouse_scroll(self, x, y, dx, dy):
        if self.ignore_input:
            return
        if self.recording:
            self._append_event(
                Event(
                    t=self._rel_time(),
                    etype="scroll",
                    x=int(x),
                    y=int(y),
                    dx=int(dx),
                    dy=int(dy),
                )
            )

    def run(self):
        print("=== Macro Recorder/Player ===")
        print("F8  = Aufnahme Start/Stop")
        print("F9  = Wiedergabe")
        print("F10 = Speichern (macro_minecraft.json)")
        print("F11 = Laden (macro_minecraft.json)")
        print("ESC = Wiedergabe stoppen / Beenden")
        print("-----------------------------")

        self.start_listeners()

        # Hauptthread am Leben halten
        try:
            while True:
                time.sleep(0.2)
                if self.k_listener is None or self.m_listener is None:
                    break
                if not self.k_listener.running or not self.m_listener.running:
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all()

    def start_listeners(self):
        self.k_listener = keyboard.Listener(
            on_press=self.on_key_press,
            on_release=self.on_key_release
        )
        self.m_listener = mouse.Listener(
            on_move=self.on_mouse_move,
            on_click=self.on_mouse_click,
            on_scroll=self.on_mouse_scroll
        )

        self.k_listener.start()
        self.m_listener.start()

    def stop_all(self):
        self.recording = False
        self.playing = False
        self.ignore_input = False
        if self.k_listener:
            self.k_listener.stop()
        if self.m_listener:
            self.m_listener.stop()


class MacroRecorderUI:
    def __init__(self, recorder: MacroRecorderPlayer):
        self.recorder = recorder
        self.root = tk.Tk()
        self.root.title("Macro Recorder")
        self.status_var = tk.StringVar(value="Idle")
        self.details_var = tk.StringVar(value="Events: 0")

        status_label = tk.Label(self.root, textvariable=self.status_var, font=("Arial", 14))
        status_label.pack(pady=(10, 2))
        details_label = tk.Label(self.root, textvariable=self.details_var)
        details_label.pack(pady=(0, 10))

        button_frame = tk.Frame(self.root)
        button_frame.pack(padx=10, pady=10)

        tk.Button(button_frame, text="Start Recording", width=18, command=self.start_recording).grid(row=0, column=0, padx=5, pady=5)
        tk.Button(button_frame, text="Stop Recording", width=18, command=self.stop_recording).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(button_frame, text="Play", width=18, command=self.play).grid(row=1, column=0, padx=5, pady=5)
        tk.Button(button_frame, text="Stop Play", width=18, command=self.stop_play).grid(row=1, column=1, padx=5, pady=5)
        tk.Button(button_frame, text="Save", width=18, command=self.save).grid(row=2, column=0, padx=5, pady=5)
        tk.Button(button_frame, text="Load", width=18, command=self.load).grid(row=2, column=1, padx=5, pady=5)
        tk.Button(button_frame, text="Exit", width=38, command=self.close).grid(row=3, column=0, columnspan=2, padx=5, pady=(10, 5))

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.recorder.start_listeners()
        self.refresh_status()

    def refresh_status(self):
        self.status_var.set(self.recorder.get_status())
        self.details_var.set(f"Events: {self.recorder.event_count()}")
        self.root.after(200, self.refresh_status)

    def start_recording(self):
        self.recorder.start_recording()

    def stop_recording(self):
        self.recorder.stop_recording()

    def play(self):
        self.recorder.play()

    def stop_play(self):
        self.recorder.stop_play()

    def save(self):
        self.recorder.save_events(DEFAULT_FILE)

    def load(self):
        try:
            self.recorder.load_events(DEFAULT_FILE)
        except Exception as e:
            print(f"[LOAD] Fehler: {e}")

    def close(self):
        self.recorder.stop_all()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MacroRecorderUI(MacroRecorderPlayer()).run()
