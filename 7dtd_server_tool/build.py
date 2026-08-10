"""
Automated PyInstaller Packaging Script for 7 Days to Die Dedicated Server Management Tool.
Bundles the application into a single standalone executable file (--onefile --windowed).
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def find_tcl_tk_dirs() -> tuple[Path | None, Path | None]:
    """Locates tcl8.6 and tk8.6 directories on the build system."""
    candidate_roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python313/tcl",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python312/tcl",
        Path(sys.prefix) / "tcl",
        Path(sys.base_prefix) / "tcl",
        Path("C:/Python313/tcl"),
    ]
    for root in candidate_roots:
        tcl_dir = root / "tcl8.6"
        tk_dir = root / "tk8.6"
        if tcl_dir.exists() and tk_dir.exists():
            return tcl_dir, tk_dir
    return None, None


def run_build() -> bool:
    """Invokes PyInstaller to create a single-file executable."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    main_script = script_dir / "main.py"
    dist_dir = script_dir / "dist"

    # 1. Configure environment (PYTHONPATH, TCL_LIBRARY, TK_LIBRARY)
    site_packages = project_root / "Lib" / "site-packages"
    env = os.environ.copy()
    if site_packages.exists():
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{site_packages};{existing_pp}" if existing_pp else str(site_packages)

    tcl_dir, tk_dir = find_tcl_tk_dirs()
    if tcl_dir and tk_dir:
        env["TCL_LIBRARY"] = str(tcl_dir)
        env["TK_LIBRARY"] = str(tk_dir)
        print(f"Located Tcl/Tk data dirs: {tcl_dir.parent}")

    print("==================================================")
    print(" [BUILD] Building 7DTD Server Management Tool Exe")
    print("==================================================")

    # 2. Define PyInstaller command arguments
    exe_name = "7DTD_Server_Manager"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        f"--name={exe_name}",
        f"--paths={script_dir}",
    ]

    # Include Tcl/Tk data assets into executable bundle if present
    if tcl_dir and tk_dir:
        cmd.append(f"--add-data={tcl_dir}{os.pathsep}tcl/tcl8.6")
        cmd.append(f"--add-data={tk_dir}{os.pathsep}tcl/tk8.6")

    cmd.append(str(main_script))

    print(f"Executing command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=str(script_dir), env=env, check=True)
        if result.returncode == 0:
            exe_path = dist_dir / f"{exe_name}.exe" if sys.platform == "win32" else dist_dir / exe_name
            print("\n==================================================")
            print(" [SUCCESS] Build Completed Successfully!")
            print(f" Standalone Executable Location: {exe_path}")
            print("==================================================")
            return True
        else:
            print(f"[Error] Build exited with code: {result.returncode}")
            return False
    except subprocess.CalledProcessError as err:
        print(f"[Error] Build failed: {err}")
        return False


if __name__ == "__main__":
    success = run_build()
    sys.exit(0 if success else 1)
