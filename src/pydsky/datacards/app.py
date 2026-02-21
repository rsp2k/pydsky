"""Apollo DSKY Data Cards — entry point."""

import argparse
import sys

from qtpy.QtWidgets import QApplication

from pydsky.datacards.window import DataCardWindow


def main():
    ap = argparse.ArgumentParser(
        description="Apollo DSKY Data Cards — quick-reference companion",
    )
    ap.add_argument(
        "--vehicle",
        choices=["CM", "LM"],
        default="CM",
        help="Vehicle type (default: CM)",
    )
    ap.add_argument(
        "--software",
        default=None,
        help="Software version (default: auto from vehicle)",
    )
    args = ap.parse_args()

    if args.software is None:
        args.software = "COLOSSUS 249" if args.vehicle == "CM" else "LUMINARY 099"

    app = QApplication(sys.argv)
    window = DataCardWindow(args.vehicle, args.software)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
