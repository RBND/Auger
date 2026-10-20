"""
Command-line front end for Auger (no GUI needed; works on headless Linux servers).

    python -m core.cli status
    python -m core.cli setup              # download the tool + install the server
    python -m core.cli update [--branch latest_experimental] [--validate]
    python -m core.cli start              # start the server and follow its status
    python -m core.cli set-sandbox-code CODE
"""

import argparse
import sys
import threading
import time
from typing import Callable, Optional

from . import __version__
from .service import AugerService, ServiceError


def _print_event(event: tuple) -> None:
    kind = event[0]
    if kind == "log":
        _, level, message = event
        if message.startswith("Downloading:"):
            print(f"\r  {message:<40}", end="", flush=True)
            return
        print(f"[{level}] {message}", flush=True)
    elif kind == "status":
        _, component, text = event
        print(f"  ({component}: {text})", flush=True)


def _wait(service: AugerService, start: Callable[[Callable], bool]) -> Optional[object]:
    """Run an async service command and pump events until it reports back."""
    done = threading.Event()
    result = {}

    def _on_done(value=None):
        result["value"] = value
        done.set()

    if not start(_on_done):
        return None
    while not done.is_set():
        service.dispatch_pending(_print_event)
        time.sleep(0.05)
    service.dispatch_pending(_print_event)
    print()
    return result.get("value")


def cmd_status(service: AugerService, _args) -> int:
    print(f"Download tool : {service.tool_name} -> {service.tool_path or 'not installed'}")
    print(f"Server folder : {service.server_dir}")
    print(f"Installed     : {'yes' if service.server_installed() else 'no'}")
    print(f"Auger config  : {service.config_path if service.config_available() else 'not created yet'}")
    admin = service.admin_path()
    if admin:
        print(f"Admin file    : {admin}")
    return 0


def _ensure_tool(service: AugerService) -> bool:
    if service.tool_ready():
        return True
    return bool(_wait(service, lambda cb: service.download_tool_async(on_done=cb)))


def cmd_setup(service: AugerService, args) -> int:
    if not _ensure_tool(service):
        print("Could not set up the download tool.", file=sys.stderr)
        return 1
    return cmd_update(service, args)


def cmd_update(service: AugerService, args) -> int:
    try:
        ok = _wait(
            service,
            lambda cb: service.install_server_async(
                branch=args.branch, validate=args.validate, on_done=cb
            ),
        )
    except ServiceError as err:
        print(err, file=sys.stderr)
        return 1
    return 0 if ok else 1


def cmd_start(service: AugerService, _args) -> int:
    try:
        service.start_server()
    except ServiceError as err:
        print(err, file=sys.stderr)
        return 1
    service.dispatch_pending(_print_event)
    print("Server is running. Press Ctrl+C to stop following (the server keeps running).")
    try:
        while service.server_running():
            service.poll_server()
            service.dispatch_pending(_print_event)
            time.sleep(2)
        service.poll_server()
        service.dispatch_pending(_print_event)
    except KeyboardInterrupt:
        print("\nStopped following. The server is still running.")
    return 0


def cmd_set_sandbox_code(service: AugerService, args) -> int:
    values = service.load_config()
    if values is None:
        print("Install the server first (python -m core.cli setup).", file=sys.stderr)
        return 1
    values["SandboxCode"] = args.code
    try:
        saved = service.save_config(values)
    except ServiceError as err:
        print(err, file=sys.stderr)
        return 1
    service.dispatch_pending(_print_event)
    print(f"Sandbox Code set to {saved['SandboxCode']}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auger", description="Auger - 7 Days to Die server manager (CLI)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show what Auger has detected")
    for name, helptext in (("setup", "Download the tool and install the server"), ("update", "Update the server")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--branch", default="public", help="Game branch (default: public)")
        p.add_argument("--validate", action="store_true", help="Verify all game files (slower)")
    sub.add_parser("start", help="Start the server")
    p = sub.add_parser("set-sandbox-code", help="Set the gameplay rules code")
    p.add_argument("code")
    return parser


COMMANDS = {
    "status": cmd_status,
    "setup": cmd_setup,
    "update": cmd_update,
    "start": cmd_start,
    "set-sandbox-code": cmd_set_sandbox_code,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    service = AugerService()
    service.detect_blocking(_print_event)
    service.dispatch_pending(_print_event)
    return COMMANDS[args.command](service, args)


if __name__ == "__main__":
    sys.exit(main())
