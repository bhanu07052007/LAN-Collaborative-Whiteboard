"""
Custom Themed Dialogs for Collaborative Whiteboard.
Implements dark-navy & blue themed modal dialogs with high contrast,
eliminating any black-on-black or illegible native styling:

1. TextInputDialog: For inserting text with clear label, input field, and OK/Cancel buttons.
2. StickyNoteDialog: For creating and editing sticky notes with large multiline editor.
3. CustomColorPickerDialog: Full-featured custom colour picker with RGB, HSV, Hex inputs,
   real-time preview, visual palette, and custom colour storage.
"""

from typing import Optional, Tuple

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIntValidator, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import client.ui_icons as ui_icons

DIALOG_STYLE = """
QDialog {
    background-color: #FFFFFF;
    border: 1.5px solid #AFCDF3;
    border-radius: 12px;
}
QLabel {
    color: #172B4D;
    font-size: 13px;
    font-weight: 500;
}
QLabel.titleLabel {
    color: #172B4D;
    font-size: 16px;
    font-weight: 800;
}
QLabel.descLabel {
    color: #64748B;
    font-size: 12px;
}
QLineEdit, QTextEdit {
    background-color: #FFFFFF;
    color: #172B4D;
    border: 1.5px solid #B8D0EE;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: #3478F6;
}
QLineEdit:focus, QTextEdit:focus {
    border-color: #3478F6;
    background-color: #FFFFFF;
}
QPushButton.primaryBtn {
    background-color: #3478F6;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 700;
    font-size: 13px;
}
QPushButton.primaryBtn:hover {
    background-color: #2563EB;
}
QPushButton.primaryBtn:pressed {
    background-color: #1D4ED8;
}
QPushButton.secondaryBtn {
    background-color: #F2F7FF;
    color: #64748B;
    border: 1px solid #AFCDF3;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton.secondaryBtn:hover {
    background-color: #C8DFFF;
    color: #172B4D;
    border-color: #3478F6;
}
QSpinBox {
    background-color: #FFFFFF;
    color: #172B4D;
    border: 1.5px solid #AFCDF3;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: bold;
}
QSpinBox:focus {
    border-color: #3478F6;
}
"""


# =============================================================================
# 1. TEXT INPUT DIALOG
# =============================================================================

class TextInputDialog(QDialog):
    """Custom dark-navy dialog for entering single-line or multi-line whiteboard text."""

    def __init__(
        self,
        title: str = "Insert Text",
        prompt: str = "Enter text to place on whiteboard (Author attribution attached):",
        default_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(460, 220)
        self.setStyleSheet(DIALOG_STYLE)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Title
        title_lbl = QLabel(title, self)
        title_lbl.setProperty("class", "titleLabel")
        layout.addWidget(title_lbl)

        # Instruction prompt
        desc_lbl = QLabel(prompt, self)
        desc_lbl.setProperty("class", "descLabel")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Text input
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Type your text here...")
        self.input_field.setText(default_text)
        self.input_field.selectAll()
        layout.addWidget(self.input_field)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setProperty("class", "secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("OK", self)
        self.btn_ok.setProperty("class", "primaryBtn")
        self.btn_ok.clicked.connect(self.accept)
        self.input_field.returnPressed.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)

        layout.addLayout(btn_layout)

    @classmethod
    def getText(
        cls,
        parent: Optional[QWidget],
        title: str,
        prompt: str,
        text: str = "",
    ) -> Tuple[str, bool]:
        dlg = cls(title=title, prompt=prompt, default_text=text, parent=parent)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            return dlg.input_field.text(), True
        return "", False


# =============================================================================
# 2. STICKY NOTE DIALOG
# =============================================================================

class StickyNoteDialog(QDialog):
    """Custom dark-navy dialog for creating and editing colorful sticky notes."""

    def __init__(
        self,
        title: str = "New Sticky Note",
        prompt: str = "Enter sticky note content:",
        default_text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(500, 320)
        self.setStyleSheet(DIALOG_STYLE)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # Title
        title_lbl = QLabel(title, self)
        title_lbl.setProperty("class", "titleLabel")
        layout.addWidget(title_lbl)

        # Instruction prompt
        desc_lbl = QLabel(prompt, self)
        desc_lbl.setProperty("class", "descLabel")
        layout.addWidget(desc_lbl)

        # Large multiline editor
        self.text_edit = QTextEdit(self)
        self.text_edit.setPlaceholderText("Write your notes, ideas, or action items here...")
        self.text_edit.setPlainText(default_text)
        self.text_edit.selectAll()
        layout.addWidget(self.text_edit, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setProperty("class", "secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("OK", self)
        self.btn_ok.setProperty("class", "primaryBtn")
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)

        layout.addLayout(btn_layout)

    @classmethod
    def getStickyText(
        cls,
        parent: Optional[QWidget],
        title: str,
        prompt: str,
        text: str = "",
    ) -> Tuple[str, bool]:
        dlg = cls(title=title, prompt=prompt, default_text=text, parent=parent)
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            return dlg.text_edit.toPlainText(), True
        return "", False


# =============================================================================
# 3. CUSTOM COLOUR PICKER DIALOG
# =============================================================================

# Preset basic palette
STANDARD_SWATCHES = [
    "#000000", "#FFFFFF", "#1E293B", "#64748B",
    "#EF4444", "#F97316", "#FACC15", "#22C55E",
    "#10B981", "#38BDF8", "#397BFF", "#594BFA",
    "#8B5CF6", "#A855F7", "#EC4899", "#F43F5E",
]


class CustomColorPickerDialog(QDialog):
    """
    High-contrast custom colour picker dialog replacing native QColorDialog.
    Features:
    - Basic colours grid & Custom colour swatches
    - Direct Red, Green, Blue (0-255) numeric inputs
    - Direct Hue, Saturation, Value numeric inputs
    - HTML Hex code input (e.g. #397BFF)
    - Real-time colour preview swatch
    - Add to Custom Colours storage
    - Fully legible white labels on dark navy background
    """

    _custom_palette: list = [
        "#1E293B", "#397BFF", "#594BFA", "#20D6A0",
        "#F59E0B", "#EF4444", "#EC4899", "#8B5CF6",
    ]

    def __init__(self, initial_color: str = "#000000", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Custom Colour")
        self.setFixedSize(540, 460)
        self.setStyleSheet(DIALOG_STYLE)
        self.setModal(True)

        self.current_color = QColor(initial_color)
        if not self.current_color.isValid():
            self.current_color = QColor("#000000")

        self._updating = False
        self._setup_ui()
        self._sync_from_color(self.current_color)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Title
        title_lbl = QLabel("Select Custom Colour", self)
        title_lbl.setProperty("class", "titleLabel")
        main_layout.addWidget(title_lbl)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(18)

        # -------------------------------------------------------------
        # Left Column: Palette Swatches & Custom Palette
        # -------------------------------------------------------------
        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # Basic Colours Header
        basic_lbl = QLabel("Basic Colours", self)
        basic_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #172B4D;")
        left_col.addWidget(basic_lbl)

        basic_grid = QGridLayout()
        basic_grid.setSpacing(6)
        row, col = 0, 0
        for hex_code in STANDARD_SWATCHES:
            btn = self._create_swatch_button(hex_code)
            basic_grid.addWidget(btn, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1
        left_col.addLayout(basic_grid)

        left_col.addSpacing(6)

        # Custom Colours Header
        custom_lbl = QLabel("Custom Colours", self)
        custom_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #172B4D;")
        left_col.addWidget(custom_lbl)

        self.custom_grid = QGridLayout()
        self.custom_grid.setSpacing(6)
        self._custom_buttons = []
        row, col = 0, 0
        for i, hex_code in enumerate(self._custom_palette[:8]):
            btn = self._create_swatch_button(hex_code, is_custom=True)
            self._custom_buttons.append(btn)
            self.custom_grid.addWidget(btn, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1
        left_col.addLayout(self.custom_grid)

        # Add to Custom Colours button
        self.btn_add_custom = QPushButton("Add to Custom Colours", self)
        self.btn_add_custom.setProperty("class", "secondaryBtn")
        self.btn_add_custom.clicked.connect(self._add_to_custom_palette)
        left_col.addWidget(self.btn_add_custom)

        left_col.addStretch()
        content_layout.addLayout(left_col, 1)

        # Separator line
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background-color: #AFCDF3; max-width: 1px; min-width: 1px;")
        content_layout.addWidget(sep)

        # -------------------------------------------------------------
        # Right Column: Preview, RGB, HSV, HTML Hex inputs
        # -------------------------------------------------------------
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        # Preview Swatch
        prev_lbl = QLabel("Colour Preview", self)
        prev_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #172B4D;")
        right_col.addWidget(prev_lbl)

        self.preview_box = QFrame(self)
        self.preview_box.setFixedHeight(48)
        self.preview_box.setStyleSheet(f"""
            background-color: {self.current_color.name()};
            border: 2px solid #AFCDF3;
            border-radius: 8px;
        """)
        right_col.addWidget(self.preview_box)

        # Numeric Values Form Grid
        form_grid = QGridLayout()
        form_grid.setSpacing(8)
        form_grid.setVerticalSpacing(8)

        # Red, Green, Blue inputs
        lbl_r = QLabel("Red (R):", self)
        self.spin_r = self._create_spinbox(0, 255)
        self.spin_r.valueChanged.connect(self._on_rgb_changed)
        form_grid.addWidget(lbl_r, 0, 0)
        form_grid.addWidget(self.spin_r, 0, 1)

        lbl_g = QLabel("Green (G):", self)
        self.spin_g = self._create_spinbox(0, 255)
        self.spin_g.valueChanged.connect(self._on_rgb_changed)
        form_grid.addWidget(lbl_g, 1, 0)
        form_grid.addWidget(self.spin_g, 1, 1)

        lbl_b = QLabel("Blue (B):", self)
        self.spin_b = self._create_spinbox(0, 255)
        self.spin_b.valueChanged.connect(self._on_rgb_changed)
        form_grid.addWidget(lbl_b, 2, 0)
        form_grid.addWidget(self.spin_b, 2, 1)

        # Hue, Saturation, Value inputs
        lbl_h = QLabel("Hue (H):", self)
        self.spin_h = self._create_spinbox(0, 359)
        self.spin_h.valueChanged.connect(self._on_hsv_changed)
        form_grid.addWidget(lbl_h, 0, 2)
        form_grid.addWidget(self.spin_h, 0, 3)

        lbl_s = QLabel("Sat (S):", self)
        self.spin_s = self._create_spinbox(0, 255)
        self.spin_s.valueChanged.connect(self._on_hsv_changed)
        form_grid.addWidget(lbl_s, 1, 2)
        form_grid.addWidget(self.spin_s, 1, 3)

        lbl_v = QLabel("Val (V):", self)
        self.spin_v = self._create_spinbox(0, 255)
        self.spin_v.valueChanged.connect(self._on_hsv_changed)
        form_grid.addWidget(lbl_v, 2, 2)
        form_grid.addWidget(self.spin_v, 2, 3)

        right_col.addLayout(form_grid)

        # HTML Hex code input
        hex_layout = QHBoxLayout()
        hex_lbl = QLabel("HTML Code:", self)
        hex_lbl.setStyleSheet("font-weight: bold; color: #172B4D;")
        hex_layout.addWidget(hex_lbl)

        self.hex_input = QLineEdit(self)
        self.hex_input.setMaxLength(7)
        self.hex_input.setText(self.current_color.name().upper())
        self.hex_input.textChanged.connect(self._on_hex_changed)
        hex_layout.addWidget(self.hex_input)
        right_col.addLayout(hex_layout)

        right_col.addStretch()
        content_layout.addLayout(right_col, 1)

        main_layout.addLayout(content_layout)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setProperty("class", "secondaryBtn")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("OK", self)
        self.btn_ok.setProperty("class", "primaryBtn")
        self.btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_ok)

        main_layout.addLayout(btn_layout)

    def _create_swatch_button(self, hex_code: str, is_custom: bool = False) -> QPushButton:
        btn = QPushButton(self)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("hex_code", hex_code)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {hex_code};
                border: 1.5px solid #AFCDF3;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                border: 2px solid #3478F6;
            }}
        """)
        btn.clicked.connect(lambda checked=False, h=hex_code: self._sync_from_hex(h))
        return btn

    def _create_spinbox(self, min_val: int, max_val: int) -> QSpinBox:
        sp = QSpinBox(self)
        sp.setRange(min_val, max_val)
        sp.setFixedWidth(72)
        return sp

    def _sync_from_color(self, color: QColor) -> None:
        if self._updating:
            return
        self._updating = True
        self.current_color = color

        self.spin_r.setValue(color.red())
        self.spin_g.setValue(color.green())
        self.spin_b.setValue(color.blue())

        h = max(0, color.hue())
        s = max(0, color.saturation())
        v = max(0, color.value())
        self.spin_h.setValue(h)
        self.spin_s.setValue(s)
        self.spin_v.setValue(v)

        self.hex_input.setText(color.name().upper())
        self.preview_box.setStyleSheet(f"""
            background-color: {color.name()};
            border: 2px solid #3478F6;
            border-radius: 8px;
        """)
        self._updating = False

    def _sync_from_hex(self, hex_code: str) -> None:
        c = QColor(hex_code)
        if c.isValid():
            self._sync_from_color(c)

    def _on_rgb_changed(self) -> None:
        if self._updating:
            return
        r = self.spin_r.value()
        g = self.spin_g.value()
        b = self.spin_b.value()
        self._sync_from_color(QColor(r, g, b))

    def _on_hsv_changed(self) -> None:
        if self._updating:
            return
        h = self.spin_h.value()
        s = self.spin_s.value()
        v = self.spin_v.value()
        c = QColor.fromHsv(h, s, v)
        self._sync_from_color(c)

    def _on_hex_changed(self, text: str) -> None:
        if self._updating:
            return
        clean = text.strip()
        if not clean.startswith("#"):
            clean = "#" + clean
        if len(clean) == 7:
            c = QColor(clean)
            if c.isValid():
                self._sync_from_color(c)

    def _add_to_custom_palette(self) -> None:
        hex_c = self.current_color.name().upper()
        if hex_c not in self._custom_palette:
            self._custom_palette.insert(0, hex_c)
            if len(self._custom_palette) > 8:
                self._custom_palette.pop()

            for i, btn in enumerate(self._custom_buttons):
                if i < len(self._custom_palette):
                    col = self._custom_palette[i]
                    btn.setProperty("hex_code", col)
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: {col};
                            border: 1.5px solid #263E62;
                            border-radius: 6px;
                        }}
                        QPushButton:hover {{
                            border: 2px solid #397BFF;
                        }}
                    """)

    @classmethod
    def getColor(
        cls,
        initial: QColor = QColor("#000000"),
        parent: Optional[QWidget] = None,
        title: str = "Select Custom Colour",
    ) -> QColor:
        dlg = cls(initial_color=initial.name() if isinstance(initial, QColor) else str(initial), parent=parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.current_color
        return QColor()  # Invalid QColor when cancelled
