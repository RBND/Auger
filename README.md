# Auger - A 7 Days to Die Dedicated Server Manager

Auger is a cross-platform Python desktop application designed to streamline installing, updating, configuring, and managing a **7 Days to Die Dedicated Server**.

---

## Features

- **Server Installation / Updating:** Automatically downloads the right tool for your OS (**SteamCMD** on Windows, **DepotDownloader** on Linux) and installs or updates the 7DTD dedicated server (supports Public Stable, Latest Experimental, and Custom branch builds). Your `serverconfig.xml` is backed up and restored around every update.
- **Configuration Management:** Interactive editor for `serverconfig.xml` with tooltips, grouped sections, validation, backups, and reset options.
- **Gameplay Rules (Sandbox Code):** Paste the code from the game's Sandbox Options screen with one click. See the step-by-step [Sandbox Code Guide](docs/SANDBOX_CODE_GUIDE.md).
- **Admin & Permission Manager:** Manage server admins, moderators, whitelist, blacklist, and custom command permission levels for `serveradmin.xml`.
- **One-Click Server Launching:** Starts the server directly (no `.bat`/`.sh` wrappers) and shows whether it is running.
- **Headless / CLI Mode:** Includes a command-line interface (`python -m core.cli`) for headless Linux servers or scripting without a GUI.
- **Isolated Configuration:** Operates with a dedicated `serverconfig.auger.xml` and isolated instance userdata, preventing Steam updates and validations from overwriting custom rules.
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
   cd "C:\path\to\Auger"
   ```
3. **Launch the application:**
   ```cmd
   python main.py
   ```
   *(or `py -3 main.py`)*

---

## Linux Setup & Execution

### 1. Install System Dependencies

On Linux, Python does not always include the `tkinter` package by default. (32-bit libraries are **not** needed: Auger downloads the server with the 64-bit DepotDownloader instead of SteamCMD on Linux.)

Install the required packages for your distribution (the quick-launch script below does this for you):

- **Ubuntu / Debian / Linux Mint:**
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-tk
  ```

- **Fedora / RHEL / CentOS:**
  ```bash
  sudo dnf install -y python3 python3-tkinter
  ```

- **Arch Linux / Manjaro:**
  ```bash
  sudo pacman -S --needed python tk
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
   cd /path/to/Auger
   ```
2. Run the main script with Python 3:
   ```bash
   python3 main.py
   ```

---

## Headless / CLI Execution

For headless Linux servers or automation, Auger can be operated without the GUI via `core.cli`:

```bash
# Check detected tools, server path, and installation status
python3 -m core.cli status

# Download the download tool and install the server
python3 -m core.cli setup

# Update server (supports optional --branch and --validate)
python3 -m core.cli update --branch latest_experimental --validate

# Apply a gameplay rules Sandbox Code
python3 -m core.cli set-sandbox-code AAAJABJACJADJARFBNC

# Launch the dedicated server and follow its status
python3 -m core.cli start
```

## Directory Structure

```text
Auger/
├── main.py                           # Application entry point
├── Start_Server_Manager(WINDOWS).bat # Quick launcher for Windows
├── Start_Server_Manager(LINUX).sh    # Quick launcher for Linux
├── core/
│   ├── __init__.py
│   ├── admin_manager.py              # serveradmin.xml reader/writer
│   ├── cli.py                        # Headless command-line interface
│   ├── config_manager.py             # serverconfig.xml reader/writer, Sandbox Code cleanup
│   ├── config_schema.py              # Server configuration schema & validation
│   ├── detector.py                   # Download tool & 7DTD auto-detection
│   ├── downloaders.py                # SteamCMD / DepotDownloader commands & output parsing
│   ├── installer.py                  # Asynchronous tool setup & server install/update
│   ├── instance.py                   # Server instance config & userdata management
│   ├── server_launcher.py            # Starts the server directly and tracks if it is running
│   ├── service.py                    # Service coordinator
│   ├── settings_store.py             # Persistent user settings store
│   └── utils.py                      # Platform helpers, DPI awareness, paths
├── gui/
│   ├── __init__.py
│   ├── main_window.py                # Main application window & tabs
│   └── views.py                      # Custom UI widgets, log viewer, dialogs
├── docs/
│   └── SANDBOX_CODE_GUIDE.md         # How to create and paste a Sandbox Code
└── tests/                            # Unit tests (python -m unittest discover -s tests -t .)
```

### Where Auger puts files by default

| | Windows | Linux |
|---|---|---|
| Download tool | `%LOCALAPPDATA%\Auger\steamcmd` | `~/.local/share/auger/depotdownloader` |
| Server files | `%LOCALAPPDATA%\Auger\instances\default\server` | `~/.local/share/auger/instances/default/server` |
| Saves & User Data | `%LOCALAPPDATA%\Auger\instances\default\userdata` | `~/.local/share/auger/instances/default/userdata` |

*(Auger also automatically detects existing servers installed in legacy paths like `%LOCALAPPDATA%\Auger\7dtd_server` or standard Steam libraries.)*

To install somewhere else, click **📁 Browse** next to *7DTD Server Folder* before clicking *Install / Update*.

### Running the tests

```bash
python -m unittest discover -s tests -t . -v
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named '_tkinter'` / `tkinter`
- **Linux:** Install the Tkinter package for Python (e.g., `sudo apt install python3-tk` or `sudo dnf install python3-tkinter`).
- **Windows:** Re-run the Python installer, select **Modify**, and make sure **tcl/tk and IDLE** is checked.

### DepotDownloader fails to start on Linux
- Auger downloads the self-contained 64-bit DepotDownloader, so no .NET install or 32-bit libraries are needed.
- If it still fails, make sure the folder isn't on a drive mounted with `noexec`, and that basic system libraries (e.g. `libssl`) are installed.

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

