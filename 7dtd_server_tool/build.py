"""
Automated PyInstaller Packaging Script for 7 Days to Die Dedicated Server Management Tool.

AV false-positive reduction measures applied:
  --onedir   : Produces a folder instead of a self-extracting dropper; far less suspicious
               to heuristic scanners. Distribute via the Inno Setup script in installer/.
  --noupx    : UPX compression is heavily flagged by AV heuristics; disabled entirely.
  --version-file : Embeds publisher / product metadata into the Windows PE header,
                   improving reputation with Windows Defender and AV vendors.
  --exclude-module : Trims unused stdlib network / debug modules from the bundle.

Linux support:
  - find_tcl_tk_dirs() searches both Windows and common Linux Tcl/Tk locations.
  - PYTHONPATH separator uses os.pathsep (colon on Linux, semicolon on Windows).
  - Output path is correct for both platforms.
"""

import os
import sys
import subprocess
from pathlib import Path


def find_tcl_tk_dirs() -> tuple[Path | None, Path | None]:
    """
    Locates tcl8.6 and tk8.6 directories on the build system.
    Searches Windows and common Linux installation paths.
    Each candidate is the *parent* directory of tcl8.6/ and tk8.6/.
    """
    candidate_roots = [
        # Windows paths
        Path(sys.prefix) / "tcl",
        Path(sys.base_prefix) / "tcl",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python313/tcl",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Python/Python312/tcl",
        Path("C:/Python313/tcl"),
        # Linux paths
        Path("/usr/lib"),              # /usr/lib/tcl8.6 and /usr/lib/tk8.6
        Path("/usr/share/tcltk"),      # /usr/share/tcltk/tcl8.6 and /usr/share/tcltk/tk8.6
        Path(sys.prefix) / "lib",      # venv-local: <venv>/lib/tcl8.6
        Path(sys.base_prefix) / "lib", # system Python: /usr/local/lib/tcl8.6
    ]
    for root in candidate_roots:
        try:
            tcl_dir = root / "tcl8.6"
            tk_dir = root / "tk8.6"
            if tcl_dir.exists() and tk_dir.exists():
                return tcl_dir, tk_dir
        except Exception:
            continue
    return None, None


def run_build() -> bool:
    """Invokes PyInstaller to create a --onedir distribution bundle."""
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    main_script = script_dir / "main.py"
    dist_dir = script_dir / "dist"
    version_info_file = script_dir / "version_info.txt"

    # 1. Configure environment (PYTHONPATH, TCL_LIBRARY, TK_LIBRARY)
    site_packages = project_root / "Lib" / "site-packages"
    env = os.environ.copy()
    if site_packages.exists():
        existing_pp = env.get("PYTHONPATH", "")
        # Use os.pathsep so this works on both Windows (;) and Linux (:)
        env["PYTHONPATH"] = f"{site_packages}{os.pathsep}{existing_pp}" if existing_pp else str(site_packages)

    tcl_dir, tk_dir = find_tcl_tk_dirs()
    if tcl_dir and tk_dir:
        env["TCL_LIBRARY"] = str(tcl_dir)
        env["TK_LIBRARY"] = str(tk_dir)
        print(f"Located Tcl/Tk data dirs: {tcl_dir.parent}")

    print("==================================================")
    print(" [BUILD] Building 7DTD Server Management Tool")
    print("==================================================")

    # 2. Define PyInstaller command arguments
    exe_name = "7DTD_Server_Manager"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",    # AV-friendly: no self-extracting dropper written to %TEMP%
        "--windowed",  # No console window for GUI app
        "--noupx",     # AV-friendly: UPX-compressed binaries trigger heuristic flags
        f"--name={exe_name}",
        f"--paths={script_dir}",
        # Trim unused stdlib modules to reduce bundle surface area
        "--exclude-module=unittest",
        "--exclude-module=doctest",
        "--exclude-module=pdb",
        "--exclude-module=ftplib",
        "--exclude-module=imaplib",
        "--exclude-module=poplib",
        "--exclude-module=smtplib",
        "--exclude-module=nntplib",
        "--exclude-module=telnetlib",
    ]

    # Windows only: embed PE version resource (publisher metadata improves AV reputation)
    if sys.platform == "win32" and version_info_file.exists():
        cmd.append(f"--version-file={version_info_file}")
        print(f"Embedding version info: {version_info_file.name}")

    # Include Tcl/Tk data assets into bundle if present
    if tcl_dir and tk_dir:
        cmd.append(f"--add-data={tcl_dir}{os.pathsep}tcl/tcl8.6")
        cmd.append(f"--add-data={tk_dir}{os.pathsep}tcl/tk8.6")

    cmd.append(str(main_script))

    print(f"Executing: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, cwd=str(script_dir), env=env, check=True)
        if result.returncode == 0:
            app_dir = dist_dir / exe_name
            exe_ext = ".exe" if sys.platform == "win32" else ""
            exe_path = app_dir / f"{exe_name}{exe_ext}"

            print("\n==================================================")
            print(" [SUCCESS] Build Completed Successfully!")
            print(f" Output folder:  {app_dir}")
            print(f" Executable:     {exe_path}")
            if sys.platform == "win32":
                print("\n Next step — build the Windows installer:")
                print("   iscc installer\\auger_setup.iss")
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
