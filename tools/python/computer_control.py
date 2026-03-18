"""
Overlord11 - Computer Control Tool
====================================
Provides programmatic control of mouse, keyboard, and clipboard via
pyautogui / pyperclip.  All operations are safety-gated: coordinates are
validated, delays are enforced between actions, and a FAILSAFE mode moves the
mouse to the top-left corner to abort.

Actions:
  mouse_move     - Move the mouse cursor to absolute or relative coordinates.
  mouse_click    - Click (left/right/middle) at the current or a given position.
  mouse_scroll   - Scroll the mouse wheel up or down.
  key_press      - Press one or more keys (supports modifiers: ctrl+c, alt+f4).
  type_text      - Type a string of text with a configurable delay.
  get_mouse_pos  - Return the current mouse cursor position.
  get_screen_size - Return the screen resolution.
  clipboard_get  - Read the current clipboard contents.
  clipboard_set  - Write text to the clipboard.
  hotkey         - Press a keyboard hotkey combination (e.g., ctrl+alt+delete).

Hard dependencies (graceful degradation):
  - pyautogui    — mouse, keyboard, screen info
  - pyperclip    — clipboard access

Usage (CLI):
    python computer_control.py --action get_screen_size
    python computer_control.py --action get_mouse_pos
    python computer_control.py --action mouse_move --x 100 --y 200
    python computer_control.py --action mouse_click --x 100 --y 200 --button left
    python computer_control.py --action key_press --keys "ctrl+c"
    python computer_control.py --action type_text --text "Hello world"
    python computer_control.py --action clipboard_set --text "copied text"
    python computer_control.py --action clipboard_get
    python computer_control.py --action hotkey --keys "ctrl,s"
"""

import argparse
import json
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution and optional log import
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

try:
    sys.path.insert(0, str(SCRIPT_DIR))
    from log_manager import log_tool_invocation, log_error
    HAS_LOG = True
except ImportError:
    HAS_LOG = False
    def log_tool_invocation(*a, **kw): pass
    def log_error(*a, **kw): pass

# ---------------------------------------------------------------------------
# Optional dependency probes
# ---------------------------------------------------------------------------
try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to top-left corner to abort
    pyautogui.PAUSE = 0.05    # Small delay between actions for safety
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False


def _require_pyautogui() -> dict | None:
    """Return error dict if pyautogui is unavailable, else None."""
    if not HAS_PYAUTOGUI:
        return {
            "status": "error",
            "error": "pyautogui not installed. Run: pip install pyautogui",
        }
    return None


def _require_pyperclip() -> dict | None:
    """Return error dict if pyperclip is unavailable, else None."""
    if not HAS_PYPERCLIP:
        return {
            "status": "error",
            "error": "pyperclip not installed. Run: pip install pyperclip",
        }
    return None


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def get_screen_size() -> dict:
    """Return the screen resolution."""
    err = _require_pyautogui()
    if err:
        return err
    try:
        width, height = pyautogui.size()
        return {"status": "ok", "width": width, "height": height}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def get_mouse_pos() -> dict:
    """Return the current mouse cursor position."""
    err = _require_pyautogui()
    if err:
        return err
    try:
        pos = pyautogui.position()
        return {"status": "ok", "x": pos.x, "y": pos.y}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def mouse_move(x: int, y: int, duration: float = 0.2, relative: bool = False) -> dict:
    """Move the mouse cursor.

    Args:
        x: Target X coordinate (absolute or relative offset).
        y: Target Y coordinate (absolute or relative offset).
        duration: Animation duration in seconds.
        relative: If True, move by (x, y) pixels relative to current position.

    Returns:
        dict with new cursor position.
    """
    err = _require_pyautogui()
    if err:
        return err
    try:
        screen_w, screen_h = pyautogui.size()
        if not relative:
            # Clamp to screen bounds
            x = max(0, min(x, screen_w - 1))
            y = max(0, min(y, screen_h - 1))
            pyautogui.moveTo(x, y, duration=duration)
        else:
            pyautogui.moveRel(x, y, duration=duration)
        pos = pyautogui.position()
        return {"status": "ok", "x": pos.x, "y": pos.y}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def mouse_click(
    x: int = None,
    y: int = None,
    button: str = "left",
    clicks: int = 1,
    interval: float = 0.1,
) -> dict:
    """Click the mouse at the given position (or current position if not specified).

    Args:
        x: X coordinate to click (optional; uses current position if None).
        y: Y coordinate to click (optional).
        button: 'left', 'right', or 'middle'.
        clicks: Number of clicks (1 for single, 2 for double).
        interval: Seconds between clicks.

    Returns:
        dict with click confirmation.
    """
    err = _require_pyautogui()
    if err:
        return err
    valid_buttons = {"left", "right", "middle"}
    if button not in valid_buttons:
        return {"status": "error", "error": f"Invalid button: '{button}'. Choose from {valid_buttons}"}
    try:
        kwargs = {"button": button, "clicks": clicks, "interval": interval}
        if x is not None and y is not None:
            pyautogui.click(x, y, **kwargs)
        else:
            pyautogui.click(**kwargs)
        pos = pyautogui.position()
        return {"status": "ok", "clicked_at": {"x": pos.x, "y": pos.y}, "button": button, "clicks": clicks}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def mouse_scroll(amount: int = 3, direction: str = "up", x: int = None, y: int = None) -> dict:
    """Scroll the mouse wheel.

    Args:
        amount: Number of scroll ticks.
        direction: 'up' or 'down'.
        x: X position to scroll at (optional).
        y: Y position to scroll at (optional).

    Returns:
        dict with scroll confirmation.
    """
    err = _require_pyautogui()
    if err:
        return err
    try:
        clicks = amount if direction == "up" else -amount
        if x is not None and y is not None:
            pyautogui.scroll(clicks, x=x, y=y)
        else:
            pyautogui.scroll(clicks)
        return {"status": "ok", "scrolled": direction, "amount": amount}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def key_press(keys: str, presses: int = 1, interval: float = 0.05) -> dict:
    """Press a key or key combination.

    Args:
        keys: Key name(s). Use '+' for combinations: 'ctrl+c', 'alt+f4'.
              Single keys: 'enter', 'escape', 'tab', 'space', 'f1', etc.
        presses: Number of times to press.
        interval: Seconds between repeated presses.

    Returns:
        dict confirming the key press.
    """
    err = _require_pyautogui()
    if err:
        return err
    try:
        if "+" in keys:
            parts = [k.strip() for k in keys.split("+")]
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(keys.strip(), presses=presses, interval=interval)
        return {"status": "ok", "keys": keys, "presses": presses}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def hotkey(*keys: str) -> dict:
    """Press a keyboard hotkey combination simultaneously.

    Args:
        keys: Comma-separated key names (e.g., 'ctrl,alt,delete').

    Returns:
        dict confirming the hotkey press.
    """
    err = _require_pyautogui()
    if err:
        return err
    try:
        pyautogui.hotkey(*keys)
        return {"status": "ok", "hotkey": "+".join(keys)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def type_text(text: str, interval: float = 0.02) -> dict:
    """Type a string of text with a configurable delay between characters.

    Args:
        text: The text to type.
        interval: Seconds between each character.

    Returns:
        dict confirming the typed text.
    """
    err = _require_pyautogui()
    if err:
        return err
    try:
        pyautogui.typewrite(text, interval=interval)
        return {"status": "ok", "typed_chars": len(text)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def clipboard_get() -> dict:
    """Read and return the current clipboard contents."""
    err = _require_pyperclip()
    if err:
        return err
    try:
        text = pyperclip.paste()
        return {"status": "ok", "content": text, "length": len(text)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def clipboard_set(text: str) -> dict:
    """Write text to the clipboard.

    Args:
        text: Text to copy to clipboard.

    Returns:
        dict confirming the clipboard write.
    """
    err = _require_pyperclip()
    if err:
        return err
    try:
        pyperclip.copy(text)
        return {"status": "ok", "length": len(text)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Computer Control Tool")
    parser.add_argument("--action", required=True,
                        choices=["mouse_move", "mouse_click", "mouse_scroll",
                                 "key_press", "type_text", "get_mouse_pos",
                                 "get_screen_size", "clipboard_get",
                                 "clipboard_set", "hotkey"],
                        help="Computer control action to perform")
    parser.add_argument("--x", type=int, default=None, help="X coordinate")
    parser.add_argument("--y", type=int, default=None, help="Y coordinate")
    parser.add_argument("--button", default="left",
                        choices=["left", "right", "middle"], help="Mouse button")
    parser.add_argument("--clicks", type=int, default=1, help="Number of clicks")
    parser.add_argument("--amount", type=int, default=3, help="Scroll amount")
    parser.add_argument("--direction", default="up", choices=["up", "down"],
                        help="Scroll direction")
    parser.add_argument("--keys", default="", help="Key(s) to press or hotkey combination")
    parser.add_argument("--text", default="", help="Text to type or set in clipboard")
    parser.add_argument("--duration", type=float, default=0.2,
                        help="Mouse move animation duration (seconds)")
    parser.add_argument("--interval", type=float, default=0.05,
                        help="Delay between actions (seconds)")
    parser.add_argument("--relative", action="store_true",
                        help="Use relative mouse movement")
    parser.add_argument("--presses", type=int, default=1,
                        help="Number of key presses")

    args = parser.parse_args()
    start = time.time()

    try:
        if args.action == "get_screen_size":
            result = get_screen_size()
        elif args.action == "get_mouse_pos":
            result = get_mouse_pos()
        elif args.action == "mouse_move":
            if args.x is None or args.y is None:
                result = {"error": "--x and --y are required for mouse_move"}
            else:
                result = mouse_move(args.x, args.y, args.duration, args.relative)
        elif args.action == "mouse_click":
            result = mouse_click(args.x, args.y, args.button, args.clicks, args.interval)
        elif args.action == "mouse_scroll":
            result = mouse_scroll(args.amount, args.direction, args.x, args.y)
        elif args.action == "key_press":
            if not args.keys:
                result = {"error": "--keys is required for key_press"}
            else:
                result = key_press(args.keys, args.presses, args.interval)
        elif args.action == "hotkey":
            if not args.keys:
                result = {"error": "--keys is required for hotkey (comma-separated, e.g. ctrl,s)"}
            else:
                keys = [k.strip() for k in args.keys.split(",")]
                result = hotkey(*keys)
        elif args.action == "type_text":
            if not args.text:
                result = {"error": "--text is required for type_text"}
            else:
                result = type_text(args.text, args.interval)
        elif args.action == "clipboard_get":
            result = clipboard_get()
        elif args.action == "clipboard_set":
            if not args.text:
                result = {"error": "--text is required for clipboard_set"}
            else:
                result = clipboard_set(args.text)
        else:
            result = {"error": f"Unknown action: {args.action}"}

    except Exception as exc:
        result = {"status": "error", "error": str(exc), "action": args.action}
        if HAS_LOG:
            log_error("system", "computer_control", str(exc))

    duration_ms = (time.time() - start) * 1000
    if HAS_LOG:
        log_tool_invocation(
            session_id="system",
            tool_name="computer_control",
            params={"action": args.action},
            result={"status": result.get("status", "error")},
            duration_ms=duration_ms,
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
