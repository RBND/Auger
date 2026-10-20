#!/bin/bash

# Change to the directory where this script is located
cd "$(dirname "$0")"

# Helper function to detect Python 3 binary
get_python_cmd() {
    if command -v python3 &> /dev/null; then
        echo "python3"
    elif command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
        echo "python"
    else
        echo ""
    fi
}

PYTHON=$(get_python_cmd)

# Helper function to check if Tkinter GUI module is available
check_tkinter() {
    if [ -n "$PYTHON" ]; then
        $PYTHON -c "import tkinter" &> /dev/null
        return $?
    fi
    return 1
}

# Function to install missing dependencies (Python 3 + Tkinter).
# Server files are downloaded with DepotDownloader (64-bit), so SteamCMD's
# 32-bit compatibility libraries are NOT required on Linux.
install_dependencies() {
    echo "=========================================================="
    echo "  Installing Python 3 + Tkinter (needed to run Auger)"
    echo "=========================================================="

    # Debian / Ubuntu / Mint / Pop!_OS
    if command -v apt-get &> /dev/null; then
        echo "Detected Debian/Ubuntu-based package manager (apt)."
        sudo apt-get update
        sudo apt-get install -y python3 python3-tk

    # Fedora / RHEL 8+
    elif command -v dnf &> /dev/null; then
        echo "Detected Fedora/RHEL-based package manager (dnf)."
        sudo dnf install -y python3 python3-tkinter

    # CentOS / older RHEL
    elif command -v yum &> /dev/null; then
        echo "Detected CentOS/RHEL package manager (yum)."
        sudo yum install -y python3 python3-tkinter

    # Arch Linux / Manjaro / EndeavourOS
    elif command -v pacman &> /dev/null; then
        echo "Detected Arch-based package manager (pacman)."
        sudo pacman -S --needed --noconfirm python tk

    # openSUSE / SLES
    elif command -v zypper &> /dev/null; then
        echo "Detected openSUSE package manager (zypper)."
        sudo zypper install -y python3 python3-tk

    else
        echo "[!] Could not automatically detect system package manager."
        echo "    Please manually install: Python 3 and Tkinter."
        read -p "Press Enter to continue..."
        return 1
    fi
}

# 1. Verify Python 3 & Tkinter existence
if [ -z "$PYTHON" ] || ! check_tkinter; then
    if [ -z "$PYTHON" ]; then
        echo "[!] Python 3 was not found on your system."
    else
        echo "[!] Python 3 is installed, but the Tkinter GUI module is missing."
    fi

    install_dependencies

    # Refresh python detection
    PYTHON=$(get_python_cmd)
fi

# 2. Re-test Tkinter availability
if ! check_tkinter; then
    echo ""
    echo "[ERROR] Tkinter is still unavailable."
    echo "        Please ensure python3-tk (or distro equivalent) is installed."
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

# 3. Execute main.py
echo "Starting Auger Dedicated Server Manager..."
if [ -f "main.py" ]; then
    $PYTHON main.py
elif [ -f "Main.py" ]; then
    $PYTHON Main.py
else
    echo "[ERROR] main.py not found in $(pwd)!"
fi

# Keep terminal window open if launched from a desktop GUI environment
echo ""
read -p "Process finished. Press Enter to exit..."