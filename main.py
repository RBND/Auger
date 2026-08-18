"""
Application Entry Point for 7 Days to Die Dedicated Server Management Tool.
Initializes High-DPI awareness, sets root window theme, and launches MainWindow.
"""

import sys
import tkinter as tk
from tkinter import ttk
from pathlib import Path

# Add project root directory to sys.path to enable absolute/relative imports
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.utils import set_dpi_awareness
from gui.main_window import MainWindow


def configure_theme(root: tk.Tk) -> None:
    """Configures high contrast modern TTK styles."""
    style = ttk.Style(root)

    # Use native OS themes if available
    available_styles = style.theme_names()
    if "vista" in available_styles:
        style.theme_use("vista")
    elif "clam" in available_styles:
        style.theme_use("clam")


def main() -> None:
    """Main application execution function."""
    # 1. Enable High-DPI scaling on Windows safely
    set_dpi_awareness()

    # 2. Instantiate root Tk instance
    root = tk.Tk()

    # 3. Apply style theme
    configure_theme(root)

    # 4. Instantiate MainWindow
    app = MainWindow(root)

    # 5. Start main loop
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nApplication closed by user.")


if __name__ == "__main__":
    main()
