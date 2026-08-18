# Auger - A 7 Days to Die Dedicated Server Manager

Auger is a cross-platform Python desktop application designed to streamline installing, updating, configuring, and managing a **7 Days to Die Dedicated Server**.

---

## Features

- **SteamCMD & Server Installation / Updating:** Automatically downloads SteamCMD and installs or updates the 7DTD dedicated server (supports Public Stable, Latest Experimental, and Custom branch builds).
- **Configuration Management:** Interactive editor for `serverconfig.xml` with tooltips, grouped sections, validation, backups, and reset options.
- **Admin & Permission Manager:** Manage server admins, moderators, whitelist, blacklist, and custom command permission levels for `serveradmin.xml`.
- **One-Click Server Launching:** Launch your dedicated server in an independent console session and open server directories directly.
- **No Third-Party Dependencies:** Built entirely with the Python Standard Library (`tkinter`, `xml.etree.ElementTree`, `subprocess`, `urllib`, etc.).

---

## Requirements

- **Python 3.8+** (Python 3.10+ recommended)
- **Tcl/Tk (Tkinter)** support enabled in Python
- **Internet connection** (for downloading SteamCMD and server files)

---

## Windows Setup & Execution

### Option 1: Quick Launch (Batch Script)

1. Ensure **Python 3** is installed and added to your system `PATH`.
2. Double-click **`Start_Server_Manager(WINDOWS).bat`** in this folder.
   - Alternatively, open Command Prompt or PowerShell in this folder and run:
     ```cmd
     "Start_Server_Manager(WINDOWS).bat"
     ```

### Option 2: Manual Run via Command Line

1. **Install Python:**
   - Download Python 3 from [python.org](https://www.python.org/downloads/).
   - During installation, make sure to check **"Add python.exe to PATH"** and ensure **tcl/tk and IDLE** is checked under Optional Features.
2. **Open Command Prompt / PowerShell:**
   ```cmd
   cd "C:\path\to\Auger(Python)"
   ```
3. **Launch the application:**
   ```cmd
   python main.py
   ```
   *(or `py -3 main.py`)*

---

## Linux Setup & Execution

### 1. Install System Dependencies

On Linux, Python does not always include the `tkinter` package by default. In addition, SteamCMD requires 32-bit compatibility libraries.

Install the required packages for your distribution:

- **Ubuntu / Debian / Linux Mint:**
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-tk lib32gcc-s1
  ```

- **Fedora / RHEL / CentOS:**
  ```bash
  sudo dnf install -y python3 python3-tkinter glibc.i686 libstdc++.i686
  ```

- **Arch Linux / Manjaro:**
  ```bash
  sudo pacman -Syu --needed python tk lib32-gcc-libs
  ```

### Option 1: Quick Launch (Shell Script)

1. Open a terminal in the application folder.
2. Ensure the shell script has executable permissions:
   ```bash
   chmod +x "Start_Server_Manager(LINUX).sh"
   ```
3. Run the script:
   ```bash
   ./Start_Server_Manager(LINUX).sh
   ```

### Option 2: Manual Run via Terminal

1. Open a terminal and navigate to the application folder:
   ```bash
   cd /path/to/Auger\(Python\)
   ```
2. Run the main script with Python 3:
   ```bash
   python3 main.py
   ```

---

## Directory Structure

```text
Auger(Python)/
├── main.py                           # Application entry point
├── Start_Server_Manager(WINDOWS).bat # Quick launcher for Windows
├── Start_Server_Manager(LINUX).sh    # Quick launcher for Linux
├── core/
│   ├── __init__.py
│   ├── admin_manager.py              # serveradmin.xml reader/writer
│   ├── config_manager.py             # serverconfig.xml reader/writer
│   ├── detector.py                   # SteamCMD & 7DTD auto-detection
│   ├── installer.py                  # Asynchronous SteamCMD / server updater
│   ├── settings_store.py             # Persistent user settings store
│   └── utils.py                      # Platform helpers, DPI awareness, process launchers
└── gui/
    ├── __init__.py
    ├── main_window.py                # Main application window & tabs
    └── views.py                      # Custom UI widgets, log viewer, modals
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named '_tkinter'` / `tkinter`
- **Linux:** Install the Tkinter package for Python (e.g., `sudo apt install python3-tk` or `sudo dnf install python3-tkinter`).
- **Windows:** Re-run the Python installer, select **Modify**, and make sure **tcl/tk and IDLE** is checked.

### SteamCMD Fails to Run on 64-bit Linux
- SteamCMD is a 32-bit executable and requires 32-bit runtime libraries.
- Run `sudo apt install lib32gcc-s1` (Ubuntu/Debian) or `sudo dnf install glibc.i686 libstdc++.i686` (Fedora/RHEL).

### Permission Denied on Linux
- If `./Start_Server_Manager(LINUX).sh` gives a permission error, run:
  ```bash
  chmod +x "Start_Server_Manager(LINUX).sh"
  ```
- Ensure the destination directory for your server files is writable by your current user.

### `Could not find platform independent libraries <prefix>` on Windows
- This warning occurs when a system-wide `PYTHONHOME` or `PYTHONPATH` environment variable points to an older, different, or moved Python installation.
- The included [`Start_Server_Manager(WINDOWS).bat`](file:///c:/Users/Myke/Documents/GitHub/Auger/Start_Server_Manager%28WINDOWS%29.bat) automatically clears `PYTHONHOME` for its session to avoid this issue.
- To fix it globally, search Windows for **"Edit the system environment variables"**, click **Environment Variables...**, and remove any obsolete `PYTHONHOME` entry under User or System variables.

