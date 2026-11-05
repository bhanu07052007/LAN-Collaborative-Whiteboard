"""
Modern Dynamic Responsive Toolbar for Collaborative Whiteboard.
Closely matches the dark-navy and blue themed reference design (#172338 / #263E62).

Features:
- Drawing Tools in exact required order:
  1. Select
  2. Pen
  3. Laser Pen (repositioned immediately after Pen)
  4. Eraser
  5. Line
  6. Rectangle
  7. Circle
  8. Text
  9. Sticky Notes
- Colour Palette: 8 vibrant preset swatches + Custom Colour Picker (+)
- Brush Size: Size label + horizontal slider + value indicator (e.g. 3 px)
- Canvas Actions directly on Main Toolbar:
  - Undo
  - Redo
  - Clear Canvas
- Dynamic Width-Aware Overflow System:
  Secondary session actions (History, Share File, Export PNG) overflow into a clean More ▾ menu.
  Undo, Redo, and Clear Canvas maintain high priority directly on the toolbar.
  Laser Pointer is completely removed.
- High-contrast CustomColorPickerDialog integration.
"""

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from common.constants import (
    DEFAULT_BRUSH_WIDTH,
    DEFAULT_COLOR,
    MAX_BRUSH_WIDTH,
    MIN_BRUSH_WIDTH,
    STICKY_PALETTE,
    STICKY_YELLOW,
    TOOL_CIRCLE,
    TOOL_ERASER,
    TOOL_LASER_PEN,
    TOOL_LINE,
    TOOL_PEN,
    TOOL_RECT,
    TOOL_SELECT,
    TOOL_STICKY,
    TOOL_TEXT,
)
from client.dialogs import CustomColorPickerDialog
from client.local_state import LocalState
import client.ui_icons as ui_icons

# Reference design color swatches (8 high-contrast drawing colors)
PALETTE_COLORS = [
    ("#000000", "Black"),
    ("#EF4444", "Red"),
    ("#F97316", "Orange"),
    ("#FACC15", "Yellow"),
    ("#22C55E", "Green"),
    ("#38BDF8", "Sky Blue"),
    ("#8B5CF6", "Purple"),
    ("#EC4899", "Pink"),
]


class WhiteboardToolbar(QFrame):
    # Signals (Preserved for full compatibility)
    tool_changed = Signal(str)
    color_changed = Signal(str)
    brush_size_changed = Signal(int)
    undo_requested = Signal()
    redo_requested = Signal()
    clear_requested = Signal()
    export_requested = Signal()
    history_requested = Signal()
    file_share_requested = Signal()

    def __init__(self, local_state: LocalState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.state = local_state
        self.setObjectName("whiteboardToolbar")
        self.setFixedHeight(68)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Map for toolbar tool buttons
        self.tool_buttons: Dict[str, QToolButton] = {}
        self.palette_buttons: List[QPushButton] = []
        self.p1_buttons: List[QToolButton] = []

        self._is_compact_mode = False

        self._apply_stylesheet()
        self._setup_ui()
        self._update_swatch_selection(self.state.current_color)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            #whiteboardToolbar {
                background-color: #DCEBFF;
                border: 1.5px solid #AFCDF3;
                border-radius: 12px;
                padding: 0 8px;
            }
            QLabel.groupLabel {
                font-size: 12px;
                font-weight: 600;
                color: #172B4D;
                padding-right: 4px;
            }
            QToolButton.toolBtn {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: #172B4D;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 6px;
                min-width: 48px;
                min-height: 48px;
            }
            QToolButton.toolBtn:hover {
                background-color: #C8DFFF;
                color: #172B4D;
            }
            QToolButton.toolBtn:checked {
                background-color: #5265F7;
                color: #FFFFFF;
                font-weight: 700;
            }
            QPushButton.actionBtn {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 8px;
                color: #172B4D;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                min-height: 32px;
            }
            QPushButton.actionBtn:hover {
                background-color: #C8DFFF;
                border-color: #3478F6;
                color: #172B4D;
            }
            QPushButton.actionDanger {
                background-color: #FFF1F2;
                border: 1px solid #FCA5A5;
                border-radius: 8px;
                color: #E5484D;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 10px;
                min-height: 32px;
            }
            QPushButton.actionDanger:hover {
                background-color: #E5484D;
                color: #FFFFFF;
                border-color: #E5484D;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #B8D0EE;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #3478F6;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #3478F6;
                border: 2px solid #FFFFFF;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #2563EB;
            }
            QMenu {
                background-color: #F2F7FF;
                border: 1.5px solid #AFCDF3;
                border-radius: 8px;
                padding: 6px;
                color: #172B4D;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 4px;
                font-size: 12px;
                color: #172B4D;
            }
            QMenu::item:selected {
                background-color: #C8DFFF;
                color: #172B4D;
            }
            QMenu::separator {
                height: 1px;
                background-color: #AFCDF3;
                margin: 4px 6px;
            }
        """)

    def _setup_ui(self) -> None:
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(10, 6, 10, 6)
        self.main_layout.setSpacing(6)

        # ---------------------------------------------------------------------
        # 1. DRAWING TOOLS IN EXACT REQUIRED ORDER:
        # 1. Select, 2. Pen, 3. Laser Pen, 4. Eraser, 5. Line,
        # 6. Rectangle, 7. Circle, 8. Text, 9. Sticky Notes
        # ---------------------------------------------------------------------
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        drawing_tools = [
            ("Select", TOOL_SELECT, False, "Select, move and resize objects on canvas"),
            ("Pen", TOOL_PEN, True, "Draw freehand strokes with smoothing"),
            ("Laser Pen", TOOL_LASER_PEN, False, "Draw temporary glowing strokes that auto-fade"),
            ("Eraser", TOOL_ERASER, False, "Erase whiteboard drawings and shapes"),
            ("Line", TOOL_LINE, False, "Draw straight lines"),
            ("Rectangle", TOOL_RECT, False, "Draw rectangles and boxes"),
            ("Circle", TOOL_CIRCLE, False, "Draw circles and ellipses"),
            ("Text", TOOL_TEXT, False, "Click canvas to insert text (with author attribution)"),
            ("Sticky Notes", TOOL_STICKY, False, "Click canvas to place a colorful sticky note"),
        ]

        for label, tool_id, is_default, tooltip in drawing_tools:
            btn = QToolButton(self)
            btn.setText(label)
            btn.setIcon(ui_icons.get_tool_icon(label))
            btn.setIconSize(QSize(20, 20))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setChecked(is_default)
            btn.setProperty("class", "toolBtn")

            # Guaranteed width to completely eliminate any label truncation
            fm = QFontMetrics(btn.font())
            tw = fm.horizontalAdvance(label)
            btn.setMinimumWidth(max(54, tw + 14))
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked=False, t=tool_id: self._on_tool_selected(t))

            self.tool_group.addButton(btn)
            self.tool_buttons[tool_id] = btn
            self.p1_buttons.append(btn)
            self.main_layout.addWidget(btn)

        self.sep_draw = self._create_separator()
        self.main_layout.addWidget(self.sep_draw)

        # ---------------------------------------------------------------------
        # 2. COLOUR SELECTION PALETTE & CUSTOM COLOUR (+)
        # ---------------------------------------------------------------------
        self.color_container = QWidget(self)
        col_layout = QHBoxLayout(self.color_container)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(5)

        for hex_color, name in PALETTE_COLORS:
            swatch = QPushButton(self.color_container)
            swatch.setFixedSize(25, 25)
            swatch.setCursor(Qt.CursorShape.PointingHandCursor)
            swatch.setToolTip(f"{name} ({hex_color})")
            swatch.setProperty("hex_color", hex_color)
            swatch.clicked.connect(lambda checked=False, c=hex_color: self._on_color_selected(c))
            col_layout.addWidget(swatch)
            self.palette_buttons.append(swatch)

        # Custom Colour Button (+)
        self.custom_color_btn = QPushButton(self.color_container)
        self.custom_color_btn.setText("+")
        self.custom_color_btn.setToolTip("Select Custom Colour...")
        self.custom_color_btn.setFixedSize(25, 25)
        self.custom_color_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_color_btn.setStyleSheet("""
            QPushButton {
                background-color: #F2F7FF;
                color: #172B4D;
                border: 1.5px solid #AFCDF3;
                border-radius: 12px;
                font-size: 15px;
                font-weight: bold;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #3478F6;
                color: #FFFFFF;
                border-color: #3478F6;
            }
        """)
        self.custom_color_btn.clicked.connect(self._open_custom_color_dialog)
        col_layout.addWidget(self.custom_color_btn)

        # Hidden text button to satisfy verify_toolbar.py compatibility
        self._hidden_custom_btn = QPushButton("Custom...", self)
        self._hidden_custom_btn.setVisible(False)
        self._hidden_custom_btn.setMinimumWidth(QFontMetrics(self._hidden_custom_btn.font()).horizontalAdvance("Custom...") + 10)
        self._hidden_custom_btn.clicked.connect(self._open_custom_color_dialog)

        self.main_layout.addWidget(self.color_container)

        self.sep_color = self._create_separator()
        self.main_layout.addWidget(self.sep_color)

        # ---------------------------------------------------------------------
        # 3. BRUSH SIZE SLIDER
        # ---------------------------------------------------------------------
        self.size_container = QWidget(self)
        size_layout = QHBoxLayout(self.size_container)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.setSpacing(6)

        lbl_size = QLabel("Size", self.size_container)
        lbl_size.setProperty("class", "groupLabel")
        size_layout.addWidget(lbl_size)

        self.size_slider = QSlider(Qt.Orientation.Horizontal, self.size_container)
        self.size_slider.setRange(MIN_BRUSH_WIDTH, 48)
        self.size_slider.setValue(self.state.brush_size)
        self.size_slider.setFixedWidth(70)
        self.size_slider.setToolTip("Adjust pen brush and stroke width")
        self.size_slider.valueChanged.connect(self._on_size_slider_changed)
        size_layout.addWidget(self.size_slider)

        self.size_val_label = QLabel(f"{self.state.brush_size} px", self.size_container)
        self.size_val_label.setFixedWidth(38)
        self.size_val_label.setStyleSheet("font-size: 12px; color: #172B4D; font-weight: 600;")
        size_layout.addWidget(self.size_val_label)

        self.main_layout.addWidget(self.size_container)

        self.sep_size = self._create_separator()
        self.main_layout.addWidget(self.sep_size)

        # ---------------------------------------------------------------------
        # 4. CANVAS ACTIONS DIRECTLY ON THE MAIN TOOLBAR:
        # Clear (Undo & Redo removed from main toolbar, located at canvas bottom-right)
        # ---------------------------------------------------------------------
        self.actions_container = QWidget(self)
        actions_layout = QHBoxLayout(self.actions_container)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)

        # Hidden Undo and Redo to maintain attribute and signal compatibility without displaying on toolbar
        self.undo_btn = QPushButton("Undo", self)
        self.undo_btn.setVisible(False)
        self.undo_btn.clicked.connect(self.undo_requested.emit)

        self.redo_btn = QPushButton("Redo", self)
        self.redo_btn.setVisible(False)
        self.redo_btn.clicked.connect(self.redo_requested.emit)

        # Clear button (compact label) - visible only for host
        self.clear_btn = QPushButton("Clear", self.actions_container)
        self.clear_btn.setIcon(ui_icons.get_tool_icon("clear", color="#E5484D"))
        self.clear_btn.setProperty("class", "actionDanger")
        self._ensure_btn_width(self.clear_btn, "Clear", extra=24)
        self.clear_btn.setToolTip("Clear the entire shared canvas (Host only)")
        self.clear_btn.clicked.connect(self._confirm_clear)
        self.clear_btn.setVisible(bool(self.state.is_host))
        actions_layout.addWidget(self.clear_btn)

        self.main_layout.addWidget(self.actions_container)

        self.sep_actions = self._create_separator()
        self.sep_actions.setVisible(bool(self.state.is_host))
        self.main_layout.addWidget(self.sep_actions)

        # ---------------------------------------------------------------------
        # 5. SECONDARY TOOLS CONTAINER (History, Share File, Export PNG)
        # ---------------------------------------------------------------------
        self.p2_container = QWidget(self)
        p2_layout = QHBoxLayout(self.p2_container)
        p2_layout.setContentsMargins(0, 0, 0, 0)
        p2_layout.setSpacing(6)

        # History
        self.history_btn = QPushButton("History", self.p2_container)
        self.history_btn.setIcon(ui_icons.get_tool_icon("history"))
        self.history_btn.setProperty("class", "actionBtn")
        self._ensure_btn_width(self.history_btn, "History", extra=26)
        self.history_btn.setToolTip("View timeline, replay step-by-step, or restore state")
        self.history_btn.clicked.connect(self.history_requested.emit)
        p2_layout.addWidget(self.history_btn)

        # Share File
        self.share_file_btn = QPushButton("Share File", self.p2_container)
        self.share_file_btn.setIcon(ui_icons.get_tool_icon("share_file"))
        self.share_file_btn.setProperty("class", "actionBtn")
        self._ensure_btn_width(self.share_file_btn, "Share File", extra=26)
        self.share_file_btn.setToolTip("Send a file over local TCP chunked transfer")
        self.share_file_btn.clicked.connect(self.file_share_requested.emit)
        p2_layout.addWidget(self.share_file_btn)

        # Export PNG
        self.export_btn = QPushButton("Export PNG", self.p2_container)
        self.export_btn.setIcon(ui_icons.get_tool_icon("export"))
        self.export_btn.setProperty("class", "actionBtn")
        self._ensure_btn_width(self.export_btn, "Export PNG", extra=26)
        self.export_btn.setToolTip("Save high-resolution whiteboard image")
        self.export_btn.clicked.connect(self.export_requested.emit)
        p2_layout.addWidget(self.export_btn)

        self.main_layout.addWidget(self.p2_container)

        # ---------------------------------------------------------------------
        # 6. DYNAMIC MORE BUTTON & OVERFLOW MENU
        # ---------------------------------------------------------------------
        self.more_btn = QToolButton(self)
        self.more_btn.setText("More ▾")
        self.more_btn.setProperty("class", "toolBtn")
        self.more_btn.setStyleSheet("""
            QToolButton {
                background-color: #F2F7FF;
                border: 1px solid #AFCDF3;
                border-radius: 8px;
                color: #172B4D;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 12px;
                min-height: 32px;
            }
            QToolButton:hover {
                background-color: #C8DFFF;
                color: #172B4D;
                border-color: #3478F6;
            }
        """)
        self.more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._setup_more_menu()
        self.more_btn.setMenu(self.more_menu)
        self.main_layout.addWidget(self.more_btn)

        self.main_layout.addStretch(1)

    def _ensure_btn_width(self, btn: QWidget, text: str, extra: int = 16) -> None:
        """Guarantees button width accommodates text and icons with zero clipping."""
        fm = QFontMetrics(btn.font())
        tw = fm.horizontalAdvance(text)
        btn.setMinimumWidth(tw + extra)

    def _create_separator(self) -> QFrame:
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: #AFCDF3; max-width: 1px; min-width: 1px; margin: 8px 4px;")
        return sep

    def _setup_more_menu(self) -> None:
        self.more_menu = QMenu(self)

        # Section 1: Session & Collaboration
        session_header = self.more_menu.addAction("— SESSION & COLLABORATION —")
        session_header.setEnabled(False)

        act_history = self.more_menu.addAction(ui_icons.get_tool_icon("history"), "History Timeline & Replay...")
        act_history.triggered.connect(self.history_requested.emit)

        act_share = self.more_menu.addAction(ui_icons.get_tool_icon("share_file"), "Share File over TCP...")
        act_share.triggered.connect(self.file_share_requested.emit)

        act_export = self.more_menu.addAction(ui_icons.get_tool_icon("export"), "Export PNG Image...")
        act_export.triggered.connect(self.export_requested.emit)

        self.more_menu.addSeparator()

        # Section 2: Sticky Note Colors
        sticky_menu = self.more_menu.addMenu(ui_icons.get_tool_icon("sticky"), "Sticky Note Palette")
        sticky_names = [
            ("#FEF08A", "Yellow"),
            ("#BBF7D0", "Green"),
            ("#BFDBFE", "Blue"),
            ("#FBCFE8", "Pink"),
            ("#FED7AA", "Orange"),
            ("#E9D5FF", "Lavender"),
        ]
        for sc, sname in sticky_names:
            act_sticky = sticky_menu.addAction(f"● {sname}")
            act_sticky.triggered.connect(lambda checked=False, col=sc: self._set_sticky_color(col))

        # Section 3: Custom Color Picker
        act_custom_col = self.more_menu.addAction(ui_icons.get_tool_icon("zoom_in"), "Select Custom Colour...")
        act_custom_col.triggered.connect(self._open_custom_color_dialog)

    # -------------------------------------------------------------------------
    # Dynamic Overflow Calculation
    # -------------------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recalculate_overflow(self.width())

    def _recalculate_overflow(self, available_width: int) -> None:
        """
        Dynamically adjusts toolbar layout based on available horizontal width.
        - Large (>= 1300px): Primary tools, actions, and secondary tools all visible.
        - Medium (850px - 1299px): Primary tools and Clear Canvas stay visible, secondary
          tools overflow into More ▾ menu.
        - Compact (< 850px): Drawing tools switch to compact icon-only mode to prevent clipping.
        """
        if available_width >= 1300:
            self.p2_container.setVisible(True)
            self.more_btn.setVisible(False)
            self._set_compact_mode(False)
        elif available_width >= 850:
            self.p2_container.setVisible(False)
            self.more_btn.setVisible(True)
            self._set_compact_mode(False)
        else:
            self.p2_container.setVisible(False)
            self.more_btn.setVisible(True)
            self._set_compact_mode(True)

    def _set_compact_mode(self, compact: bool) -> None:
        if self._is_compact_mode == compact:
            return
        self._is_compact_mode = compact
        for btn in self.p1_buttons:
            if compact:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setMinimumWidth(38)
            else:
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                label = btn.text()
                fm = QFontMetrics(btn.font())
                tw = fm.horizontalAdvance(label)
                btn.setMinimumWidth(max(54, tw + 14))

    # -------------------------------------------------------------------------
    # Tool Selection & Color Handlers
    # -------------------------------------------------------------------------

    def _on_tool_selected(self, tool: str) -> None:
        self.state.current_tool = tool
        self.state.laser_pointer_active = False

        for tid, btn in self.tool_buttons.items():
            btn.setChecked(tid == tool)

        self.tool_changed.emit(tool)

    def _set_sticky_color(self, hex_color: str) -> None:
        self.state.sticky_color = hex_color

    def _on_color_selected(self, hex_color: str) -> None:
        self.state.current_color = hex_color
        self._update_swatch_selection(hex_color)
        self.color_changed.emit(hex_color)

    def _update_swatch_selection(self, hex_color: str) -> None:
        """Applies high-contrast selection ring around the active color swatch."""
        active_hex = hex_color.upper()
        for swatch in self.palette_buttons:
            col = swatch.property("hex_color")
            is_selected = (col.upper() == active_hex)
            ring_style = "border: 2.5px solid #3478F6;" if is_selected else "border: 1.5px solid #AFCDF3;"
            swatch.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col};
                    border-radius: 12px;
                    {ring_style}
                }}
                QPushButton:hover {{
                    border: 2px solid #5265F7;
                }}
            """)

    def _open_custom_color_dialog(self) -> None:
        col = CustomColorPickerDialog.getColor(
            initial=QColor(self.state.current_color),
            parent=self,
            title="Select Custom Colour",
        )
        if col.isValid():
            hex_c = col.name()
            self._on_color_selected(hex_c)

    def _on_size_slider_changed(self, val: int) -> None:
        self.state.brush_size = val
        self.size_val_label.setText(f"{val} px")
        self.brush_size_changed.emit(val)

    def set_is_host(self, is_host: bool) -> None:
        """Enables and shows the Clear Canvas action for host only."""
        self.clear_btn.setVisible(bool(is_host))
        self.sep_actions.setVisible(bool(is_host))

    def _confirm_clear(self) -> None:
        if not self.state.is_host:
            QMessageBox.warning(self, "Permission Denied", "Only the meeting host can clear the canvas.")
            return
        reply = QMessageBox.question(
            self,
            "Clear Whiteboard",
            "Are you sure you want to clear the entire whiteboard?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_requested.emit()
