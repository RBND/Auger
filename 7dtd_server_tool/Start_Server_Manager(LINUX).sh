#!/bin/bash

# 1. Change to the directory where the script is located
# This ensures it finds Main.py and requirements.txt even if double-clicked
cd "$(dirname "$0")"

# 2. Function to install Python based on the system's package manager
install_python() {
    echo "Python3 is not installed. Attempting to install..."
    # Debian/Ubuntu based
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y python3 python3-pip python3-venv
    # Fedora/RHEL based
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3 python3-pip
    # Arch based
    elif command -v pacman &> /dev/null; then
        sudo pacman -Sy --noconfirm python python-pip
    else
        echo "Could not detect package manager. Please install Python3 manually."
        read -p "Press Enter to exit..."
        exit 1
    fi
}

# 3. Check if python3 is installed; if not, run the install function
if ! command -v python3 &> /dev/null; then
    install_python
fi

# 4. Create a virtual environment with edge-case handling
if [ ! -d "venv" ]; then
    echo "Creating a virtual environment..."
    # Try to create it; if it fails, attempt to install python3-venv (Debian/Ubuntu specific fix)
    if ! python3 -m venv venv; then
        echo "Failed to create venv. Attempting to install python3-venv..."
        if command -v apt &> /dev/null; then
            sudo apt update && sudo apt install -y python3-venv
            python3 -m venv venv
        else
            echo "Error: Please install the python3-venv package manually."
            read -p "Press Enter to exit..."
            exit 1
        fi
    fi
fi

# 5. Activate the virtual environment
source venv/bin/activate

# 6. Install requirements
if [ -f "requirements.txt" ]; then
    echo "Installing requirements..."
    pip install -r requirements.txt
else
    echo "Error: requirements.txt not found in this directory!"
fi

# 7. Run main.py
if [ -f "main.py" ]; then
    echo "Starting main.py..."
    python main.py
elif [ -f "Main.py" ]; then
    echo "Starting Main.py..."
    python Main.py
else
    echo "Error: main.py not found in this directory!"
fi

# Keep the terminal window open after the script finishes so you can see any output/errors
echo ""
read -p "Process finished. Press Enter to exit..."