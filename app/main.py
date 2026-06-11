#!/usr/bin/env python3
"""
Open-Canoe App — CAN Bus Analyzer Desktop Application.

Usage:
  python main.py                        Normal mode (connect to real hardware)
  python main.py --mock                 Test mode with mock hardware simulator
  python main.py --lang zh              Chinese UI

Integrated tests (no GUI needed):
  python test/test_mock_integration.py

Dependencies: PySide6, pyserial
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.i18n.manager import I18nManager
from src.ui.styles import get_theme_stylesheet


def main():
    parser = argparse.ArgumentParser(description="Open-Canoe CAN Analyzer")
    parser.add_argument("--mock", action="store_true",
                        help="Run with mock hardware (no real device needed)")
    parser.add_argument("--lang", choices=["en", "zh"], default="en",
                        help="UI language (default: en)")
    args = parser.parse_args()

    I18nManager.set_language(args.lang)

    app = QApplication(sys.argv)
    app.setApplicationName("Open-Canoe")
    app.setStyleSheet(get_theme_stylesheet(True))

    window = MainWindow(mock_mode=args.mock)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
