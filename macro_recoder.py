"""
PC 매크로 녹화/재생 스크립트 (스냅샷 기능 포함)
------------------------------------------------
마우스 클릭, 마우스 이동, 키보드 입력을 순서와 시간 간격까지 그대로 기록했다가
나중에 똑같이 재생해주는 도구입니다.
매크로는 이름을 붙여 여러 개 저장/불러오기 할 수 있고,
녹화 도중 화면 스크린샷도 찍어서 함께 기록할 수 있습니다.

[사전 준비]
    pip install pynput pillow

[사용법]
    python macro_recorder.py

    F9  : 녹화 시작 / 정지 (토글). 정지하면 저장할 이름을 콘솔에 입력받습니다.
    F7  : 녹화 중에만 동작 — 지금 이 순간 화면을 스크린샷으로 저장 (스냅샷)
    F10 : 저장된 매크로 목록을 보여주고, 이름을 입력하면 재생
    F6  : 재생 중 즉시 멈추기 (비상 정지)
    ESC : 프로그램 종료

    매크로 데이터: macros/<이름>.json
    스냅샷 이미지: macros/<이름>_snapshots/snap_0001.png 형태로 저장됩니다.
"""

import json
import os
import time
import threading
from datetime import datetime

from pynput import mouse, keyboard
from pynput.mouse import Controller as MouseController, Button
from pynput.keyboard import Controller as KeyboardController, Key

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None  # pillow가 없으면 스냅샷 기능만 비활성화

MACRO_DIR = "macros"
os.makedirs(MACRO_DIR, exist_ok=True)

mouse_ctrl = MouseController()
keyboard_ctrl = KeyboardController()

events = []          # 녹화된 이벤트들이 쌓이는 리스트
recording = False
playing = False
start_time = None
snapshot_count = 0
current_snap_dir = None


# ---------- 녹화 ----------

def record_event(event_type, **kwargs):
    if not recording:
        return
    events.append({
        "type": event_type,
        "time": time.time() - start_time,
        **kwargs
    })


def on_move(x, y):
    record_event("move", x=x, y=y)


def on_click(x, y, button, pressed):
    record_event("click", x=x, y=y, button=str(button), pressed=pressed)


def on_scroll(x, y, dx, dy):
    record_event("scroll", x=x, y=y, dx=dx, dy=dy)


def take_snapshot():
    """녹화 중 F7을 누르면 현재 화면을 이미지로 저장하고, 이벤트 목록에도 남긴다."""
    global snapshot_count

    if not recording:
        print("[스냅샷 무시] 녹화 중일 때만 스냅샷을 찍을 수 있습니다.")
        return

    if ImageGrab is None:
        print("[오류] pillow가 설치되어 있지 않습니다. pip install pillow 후 다시 시도하세요.")
        return

    snapshot_count += 1
    filename = f"snap_{snapshot_count:04d}.png"
    filepath = os.path.join(current_snap_dir, filename)

    img = ImageGrab.grab()
    img.save(filepath)

    record_event("snapshot", file=filepath)
    print(f"[스냅샷] {filepath} 저장됨")


def on_press(key):
    global recording, playing

    if key == Key.f9:
        toggle_recording()
        return

    if key == Key.f7:
        take_snapshot()
        return

    if key == Key.f10:
        threading.Thread(target=choose_and_play, daemon=True).start()
        return

    if key == Key.f6:
        playing = False
        print("[정지] 재생을 멈췄습니다.")
        return

    if key == Key.esc:
        print("[종료] 프로그램을 끝냅니다.")
        return False

    try:
        record_event("key_press", key=str(key.char))
    except AttributeError:
        record_event("key_press", key=str(key))


def on_release(key):
    try:
        record_event("key_release", key=str(key.char))
    except AttributeError:
        record_event("key_release", key=str(key))


def toggle_recording():
    global recording, start_time, events, snapshot_count, current_snap_dir

    if not recording:
        events = []
        snapshot_count = 0
        start_time = time.time()
        recording = True
        print("[녹화 시작] F7=스냅샷, F9=녹화 정지")
    else:
        recording = False
        name = input("[녹화 종료] 저장할 매크로 이름을 입력하세요 (엔터=last): ").strip()
        if not name:
            name = "last"

        current_snap_dir = os.path.join(MACRO_DIR, f"{name}_snapshots")
        os.makedirs(current_snap_dir, exist_ok=True)

        filepath = os.path.join(MACRO_DIR, f"{name}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

        print(f"[저장 완료] '{name}' ({len(events)}개 이벤트) -> {filepath}")


# ---------- 재생 ----------

def list_macros():
    files = [f[:-5] for f in os.listdir(MACRO_DIR) if f.endswith(".json")]
    return sorted(files)


def choose_and_play():
    macros = list_macros()
    if not macros:
        print("[오류] 저장된 매크로가 없습니다. 먼저 F9로 녹화하세요.")
        return

    print("저장된 매크로 목록:", ", ".join(macros))
    name = input("재생할 매크로 이름을 입력하세요: ").strip()
    if name not in macros:
        print(f"[오류] '{name}' 매크로를 찾을 수 없습니다.")
        return

    play_macro(name)


def play_macro(name):
    global playing

    filepath = os.path.join(MACRO_DIR, f"{name}.json")
    with open(filepath, "r", encoding="utf-8") as f:
        saved_events = json.load(f)

    if not saved_events:
        print("[오류] 저장된 이벤트가 없습니다.")
        return

    playing = True
    print(f"[재생 시작: {name}] F6을 누르면 즉시 멈춥니다.")

    last_time = 0
    for ev in saved_events:
        if not playing:
            print("[재생 중단]")
            return

        wait = ev["time"] - last_time
        if wait > 0:
            time.sleep(wait)
        last_time = ev["time"]

        etype = ev["type"]

        if etype == "move":
            mouse_ctrl.position = (ev["x"], ev["y"])

        elif etype == "click":
            mouse_ctrl.position = (ev["x"], ev["y"])
            btn = Button.left if "left" in ev["button"] else Button.right
            if ev["pressed"]:
                mouse_ctrl.press(btn)
            else:
                mouse_ctrl.release(btn)

        elif etype == "scroll":
            mouse_ctrl.scroll(ev["dx"], ev["dy"])

        elif etype == "key_press":
            keyboard_ctrl.press(_parse_key(ev["key"]))

        elif etype == "key_release":
            keyboard_ctrl.release(_parse_key(ev["key"]))

        elif etype == "snapshot":
            # 재생 시점에는 실제로 화면을 찍지 않고, 기록 시점 스냅샷 위치만 알려줌
            print(f"  (참고) 이 시점의 원본 스냅샷: {ev['file']}")

    playing = False
    print("[재생 완료]")


def _parse_key(key_str):
    if key_str.startswith("Key."):
        return getattr(Key, key_str.split(".")[1])
    return key_str


# ---------- 메인 ----------

def main():
    print("=" * 55)
    print("PC 매크로 녹화/재생 프로그램 (스냅샷 지원)")
    print("F9:녹화시작/정지  F7:스냅샷(녹화중)  F10:재생  F6:정지  ESC:종료")
    print(f"현재 저장된 매크로: {', '.join(list_macros()) or '없음'}")
    print("=" * 55)

    m_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
    m_listener.start()

    with keyboard.Listener(on_press=on_press, on_release=on_release) as k_listener:
        k_listener.join()

    m_listener.stop()


if __name__ == "__main__":
    main()
