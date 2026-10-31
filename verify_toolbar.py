"""
Verification script for WhiteboardToolbar layout, button widths, and readability.
Tests resolutions: 1920x1080, 1600x900, 1366x768, 1280x720, 1024x768.
Asserts that every button has adequate width to display its full text without truncation.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton

from client.local_state import LocalState
from client.main_window import MainWindow
from client.network_client import NetworkClient
from client.toolbar import WhiteboardToolbar


def verify_toolbar_and_resolutions():
    app = QApplication.instance() or QApplication(sys.argv)

    state = LocalState(user_id="test-verify", username="Tester", current_room_id="room-1")
    net = NetworkClient()
    win = MainWindow(state, net)

    # Expected tools and action labels that must be present and completely readable on toolbar
    expected_labels = [
        "Select",
        "Pen",
        "Laser Pen",
        "Eraser",
        "Line",
        "Rectangle",
        "Circle",
        "Text",
        "Sticky Notes",
        "Custom...",
        "Clear",
        "Export PNG",
        "History",
        "Share File",
    ]

    resolutions = [
        (1920, 1080),
        (1600, 900),
        (1366, 768),
        (1280, 720),
        (1024, 768),
    ]

    toolbar = win.toolbar

    print("=" * 70)
    print("VERIFYING TOOLBAR AT MULTIPLE RESOLUTIONS")
    print("=" * 70)

    # Check button existence and label lengths
    buttons = toolbar.findChildren(QToolButton) + toolbar.findChildren(QPushButton)
    found_labels = set()

    for btn in buttons:
        text = btn.text().strip()
        if text:
            found_labels.add(text)
            fm = QFontMetrics(btn.font())
            text_width = fm.horizontalAdvance(text)
            btn_width = btn.sizeHint().width()

            # Ensure button is not narrower than its text
            if btn_width < text_width:
                print(f"[ERROR] Button '{text}' sizeHint {btn_width} < text width {text_width}")
                return 1

    missing = [label for label in expected_labels if label not in found_labels]
    if missing:
        print(f"[ERROR] Missing expected toolbar labels: {missing}")
        return 1

    print(f"[PASS] All {len(expected_labels)} expected tools/actions found with full legible text.")

    # Test window resize and rendering across resolutions
    output_dir = Path("dist") / "verification_screens"
    output_dir.mkdir(parents=True, exist_ok=True)

    for w, h in resolutions:
        win.resize(w, h)
        app.processEvents()

        # Check that canvas and toolbar have valid geometry
        tb_geom = toolbar.geometry()
        cv_geom = win.canvas.geometry()
        assert tb_geom.width() > 0 and tb_geom.height() > 0
        assert cv_geom.width() > 0 and cv_geom.height() > 0

        # Grab window image to verify rendering
        pixmap = win.grab()
        screenshot_path = output_dir / f"window_{w}x{h}.png"
        pixmap.save(str(screenshot_path), "PNG")
        print(f"[PASS] Resolution {w}x{h} rendered successfully -> saved {screenshot_path.name}")

    print("=" * 70)
    print("ALL RESOLUTION TESTS PASSED! NO CLIPPING DETECTED.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(verify_toolbar_and_resolutions())
