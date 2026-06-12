"""Canoe — Open CAN Bus Analyzer entry point."""

from gui.app import MainWindow


def main():
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
