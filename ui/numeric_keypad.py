from PyQt6.QtWidgets import QDialog, QWidget, QLabel, QGridLayout, QHBoxLayout, QVBoxLayout, QPushButton
from PyQt6.QtCore import Qt

from ui.theme import T


class NumericKeypad(QDialog):
    """虛擬數字鍵盤對話框"""
    
    def __init__(self, parent=None, current_value=0.0):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
        self._result_value: float | None = None
        self.current_input = str(int(current_value)) if current_value > 0 else ""
        
        self.setFixedSize(400, 500)
        
        container = QWidget(self)
        container.setGeometry(0, 0, 400, 500)
        container.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2a2a35, stop:1 #1a1a25);
                border-radius: 20px;
                border: 3px solid {T('PRIMARY')};
            }}
        """)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("輸入總里程")
        title.setStyleSheet(f"""
            color: {{T('PRIMARY')}};
            font-size: 20px;
            font-weight: bold;
            background: transparent;
        """)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.display = QLabel(self.current_input if self.current_input else "0")
        self.display.setFixedHeight(60)
        self.display.setStyleSheet("""
            QLabel {
                background: #1a1a25;
                color: white;
                font-size: 36px;
                font-weight: bold;
                border: 2px solid #4a4a55;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        unit_label = QLabel("km")
        unit_label.setStyleSheet("""
            color: #888;
            font-size: 14px;
            background: transparent;
        """)
        unit_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
        button_grid = QGridLayout()
        button_grid.setSpacing(10)
        
        for i in range(9):
            btn = self.create_number_button(str(i + 1))
            row = i // 3
            col = i % 3
            button_grid.addWidget(btn, row, col)
        
        btn_0 = self.create_number_button("0")
        button_grid.addWidget(btn_0, 3, 0, 1, 2)
        
        btn_bs = self.create_function_button("⌫", self.backspace)
        button_grid.addWidget(btn_bs, 3, 2)
        
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(50)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: #555;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #666; }}
            QPushButton:pressed {{ background-color: #444; }}
        """)
        btn_cancel.clicked.connect(self.cancel)
        
        btn_ok = QPushButton("確定")
        btn_ok.setFixedHeight(50)
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {{T('PRIMARY')}};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #5ad; }}
            QPushButton:pressed {{ background-color: #49c; }}
        """)
        btn_ok.clicked.connect(self.confirm)
        
        action_layout.addWidget(btn_cancel)
        action_layout.addWidget(btn_ok)
        
        layout.addWidget(title)
        layout.addWidget(self.display)
        layout.addWidget(unit_label)
        layout.addSpacing(10)
        layout.addLayout(button_grid)
        layout.addLayout(action_layout)
    
    def create_number_button(self, text):
        btn = QPushButton(text)
        btn.setFixedSize(110, 60)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a45;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a4a55; }
            QPushButton:pressed { background-color: #2a2a35; }
        """)
        btn.clicked.connect(lambda: self.append_digit(text))
        return btn
    
    def create_function_button(self, text, callback):
        btn = QPushButton(text)
        btn.setFixedSize(110, 60)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #6a5acd;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #7a6add; }
            QPushButton:pressed { background-color: #5a4abd; }
        """)
        btn.clicked.connect(callback)
        return btn
    
    def append_digit(self, digit):
        if len(self.current_input) < 7:
            self.current_input += digit
            self.display.setText(self.current_input if self.current_input else "0")
    
    def backspace(self):
        if self.current_input:
            self.current_input = self.current_input[:-1]
            self.display.setText(self.current_input if self.current_input else "0")
    
    def confirm(self):
        try:
            self._result_value = float(self.current_input) if self.current_input else 0.0
        except ValueError:
            self._result_value = 0.0
        self.close()
    
    def cancel(self):
        self._result_value = None
        self.close()
    
    def get_result(self):
        return self._result_value
