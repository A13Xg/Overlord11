import argparse
import subprocess
import sys


def get_listener_pid(port: int) -> int | None:
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    pid_text = (out.stdout or "").strip()
    if not pid_text:
        return None
    try:
        return int(pid_text)
    except ValueError:
        return None


def stop_process(pid: int) -> tuple[bool, str]:
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"Stop-Process -Id {pid} -Force -ErrorAction Stop",
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if out.returncode == 0:
        return True, ""
    return False, (out.stderr or out.stdout or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Kill the process listening on a TCP port (Windows).")
    parser.add_argument("--port", type=int, default=7900, help="TCP port to free (default: 7900)")
    args = parser.parse_args()

    pid = get_listener_pid(args.port)
    if pid is None:
        print(f"No process is listening on port {args.port}.")
        return 0

    ok, err = stop_process(pid)
    if ok:
        print(f"Stopped process {pid} on port {args.port}.")
        return 0

    print(f"Failed to stop process {pid} on port {args.port}. {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
