#!/usr/bin/env python3
"""Cross-platform script to run Repomix on the Auger codebase."""

import os
import shutil
import subprocess
import sys


def find_repomix_runner():
    """Find repomix or npx executable."""
    # 1. Check for global repomix executable
    repomix_path = shutil.which("repomix")
    if repomix_path:
        return [repomix_path]

    # 2. Check for npx
    if sys.platform == "win32":
        npx_path = shutil.which("npx.cmd") or shutil.which("npx")
    else:
        npx_path = shutil.which("npx")

    if npx_path:
        return [npx_path, "--yes", "repomix"]

    return None


def main():
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(repo_dir)

    runner = find_repomix_runner()
    if not runner:
        print("[ERROR] Neither 'repomix' nor 'npx' (Node.js) was found on your PATH.", file=sys.stderr)
        print("\nTo run Repomix, please install Node.js (v18+ recommended):", file=sys.stderr)
        print("  - Download and install: https://nodejs.org/", file=sys.stderr)
        print("  - Or install globally:  npm install -g repomix", file=sys.stderr)
        sys.exit(1)

    cmd = runner + sys.argv[1:]
    print("=" * 56)
    print("  Running Repomix on Auger Codebase")
    print("=" * 56)
    print(f"Command: {' '.join(cmd)}\n")

    try:
        # On Windows, shell=True may be required when calling .cmd files if not directly resolved
        use_shell = sys.platform == "win32" and runner[0].lower().endswith(".cmd")
        result = subprocess.run(cmd, shell=use_shell)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
