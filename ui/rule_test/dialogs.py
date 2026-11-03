"""Nonblocking choice/preparation dialogs; no dialog pauses a running clock."""
import chess
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout
from ui.widgets import label

PIECE_NAMES={chess.QUEEN:'Dame',chess.ROOK:'Turm',chess.BISHOP:'Läufer',chess.KNIGHT:'Springer'}


class PromotionDialog(QDialog):
    def __init__(self,choices,parent=None):
        super().__init__(parent);self.setWindowTitle('Bauernumwandlung');self.selected_piece=None
        layout=QVBoxLayout(self);layout.addWidget(label('Umwandlungsfigur wählen','pageTitle'))
        layout.addWidget(label('Die Uhr läuft weiter. Abbrechen führt keinen Zug aus; die Figur bleibt gebunden.','subtitle'))
        self.choice_buttons={}
        for kind in choices:
            button=QPushButton(PIECE_NAMES[kind]);self.choice_buttons[kind]=button
            button.clicked.connect(lambda checked=False,value=kind:self.choose(value));layout.addWidget(button)
        cancel=QPushButton('Abbrechen');cancel.clicked.connect(self.reject);layout.addWidget(cancel)

    def choose(self,kind):
        self.selected_piece=kind;self.accept()


class DrawClaimDialog(QDialog):
    def __init__(self,session,parent=None):
        super().__init__(parent);self.setWindowTitle('Remisantrag vorbereiten');self.session=session;self.intended_move=None
        layout=QVBoxLayout(self)
        layout.addWidget(label('Remis beantragen','pageTitle'))
        layout.addWidget(label('Die Uhr läuft bis zur verbindlichen Antragstellung weiter. Ein gestellter Antrag kann nicht zurückgenommen werden.','subtitle'))
        self.basis=QComboBox();self.basis.addItems(['Aktuelle Stellung','Mit beabsichtigtem Zug'])
        layout.addWidget(self.basis)
        fields=QFormLayout();self.source=QLineEdit();self.target=QLineEdit()
        for widget in (self.source,self.target):widget.setMaxLength(2);widget.setPlaceholderText('z. B. e2')
        fields.addRow('Startfeld',self.source);fields.addRow('Zielfeld',self.target)
        self.promotion=QComboBox();self.promotion.addItem('Keine Umwandlung',None)
        for kind,text in PIECE_NAMES.items():self.promotion.addItem(text,kind)
        fields.addRow('Umwandlung',self.promotion);layout.addLayout(fields)
        self.error=label('','notice');self.error.hide();layout.addWidget(self.error)
        layout.addWidget(label('Ein unbegründeter Antrag gibt dem Gegner 60 Sekunden. Ein dabei angegebener legaler Zug wird verbindlich ausgeführt und erhält genau sein normales Inkrement.','smallText'))
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Antrag verbindlich stellen')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Vorbereitung abbrechen')
        self.buttons.accepted.connect(self.submit);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.basis.currentIndexChanged.connect(self.update_fields);self.update_fields()

    def update_fields(self):
        for widget in (self.source,self.target,self.promotion):widget.setEnabled(self.basis.currentIndex()==1)

    def submit(self):
        if self.basis.currentIndex()==1:
            try:
                source=chess.parse_square(self.source.text().strip().lower())
                target=chess.parse_square(self.target.text().strip().lower())
                move=chess.Move(source,target,promotion=self.promotion.currentData())
                if move not in self.session.board.legal_moves:raise ValueError()
            except ValueError:
                self.error.setText('Bitte einen legalen beabsichtigten Zug und gegebenenfalls eine Umwandlungsfigur angeben. Noch kein Antrag gestellt.');self.error.show();return
            self.intended_move=move
        else:self.intended_move=None
        self.accept()
