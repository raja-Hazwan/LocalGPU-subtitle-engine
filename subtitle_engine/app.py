"""PySide6 window: Upload → Generate → (edit) → Export."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .engine import (
    ENGLISH, LANGUAGE, Transcriber, bundle_dir, detect_device, english_to_malay_cues, extract_audio,
)
from .subtitles import (
    Cue, format_timestamp, parse_timestamp, sentence_text, to_srt, to_vtt, validate_cues,
)
from .translate import Translator
from .vocabulary import Vocabulary, parse_corrections, parse_words

VIDEO_FILTER = "Video files (*.mp4 *.mkv *.mov *.avi);;All files (*)"
SPEECH_OPTIONS = [("Malay speech → Malay subtitles", LANGUAGE),
                  ("English speech → Malay subtitles (translated)", ENGLISH)]

STYLE = """
QWidget { font-family: 'Segoe UI'; font-size: 10.5pt; color: #1f2328; }
QMainWindow, #root { background: #f6f7f9; }
#title { font-size: 16pt; font-weight: 600; }
#subtitle, #file, #status { color: #59636e; }
#badge { border-radius: 10px; padding: 4px 12px; font-weight: 600; }
#badge[kind="gpu"] { background: #dafbe1; color: #116329; }
#badge[kind="cpu"] { background: #fff1d6; color: #7a4a00; }
#badge[kind="unknown"] { background: #eaeef2; color: #59636e; }
QComboBox { background: white; border: 1px solid #d0d7de; border-radius: 6px; padding: 6px 10px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dbe9ff; selection-color: #1f2328; }
QPushButton { background: white; border: 1px solid #d0d7de; border-radius: 6px; padding: 7px 18px; }
QPushButton:hover:enabled { background: #f3f4f6; }
QPushButton:disabled { color: #a0a7b0; }
QPushButton#primary { background: #1f6feb; border-color: #1f6feb; color: white; font-weight: 600; }
QPushButton#primary:hover:enabled { background: #1a5fcc; }
QPushButton#primary:disabled { background: #9dbcf4; border-color: #9dbcf4; }
QPushButton#link { border: none; background: transparent; color: #1f6feb; padding: 7px 6px; }
QPushButton#link:hover:enabled { text-decoration: underline; background: transparent; }
QPlainTextEdit { background: white; border: 1px solid #d0d7de; border-radius: 6px; padding: 4px; }
#hint { color: #59636e; font-size: 9.5pt; }
QProgressBar { border: none; background: #e4e7eb; border-radius: 4px; height: 8px; }
QProgressBar::chunk { background: #1f6feb; border-radius: 4px; }
QTableWidget { background: white; border: 1px solid #d0d7de; border-radius: 6px; gridline-color: #eef0f2; }
QTableWidget { selection-background-color: #dbe9ff; selection-color: #1f2328; alternate-background-color: #fafbfc; }
QHeaderView::section { background: #f6f7f9; border: none; border-bottom: 1px solid #d0d7de; padding: 6px; font-weight: 600; }
QHeaderView::section:vertical { border-bottom: none; border-right: 1px solid #eef0f2; padding: 0 8px; color: #59636e; }
QTableCornerButton::section { background: #f6f7f9; border: none; border-bottom: 1px solid #d0d7de; }
QTableWidget QLineEdit { background: white; color: #1f2328; border: 2px solid #1f6feb; border-radius: 3px;
                         padding: 0 4px; selection-background-color: #1f6feb; selection-color: white; }
"""


class TranscribeWorker(QThread):
    status = Signal(str)
    progress = Signal(int)          # 0-100, or -1 for "busy" (indeterminate)
    device = Signal(str, bool)      # label, is_gpu
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, transcriber: Transcriber, translator: Translator, video: str,
                 vocabulary: Vocabulary, language: str = LANGUAGE) -> None:
        super().__init__()
        self.transcriber, self.translator = transcriber, translator
        self.video, self.vocabulary, self.language = video, vocabulary, language
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        try:
            self.progress.emit(-1)
            dev = self.transcriber.load(self.status.emit)
            self.device.emit(dev.label, dev.is_gpu)
            self.status.emit("Extracting audio with ffmpeg…")
            audio = extract_audio(self.video)
            self.progress.emit(0)

            def on_status(msg: str) -> None:
                self.status.emit(msg)
                self.device.emit(self.transcriber.device.label, self.transcriber.device.is_gpu)

            progress = dict(on_progress=lambda p: self.progress.emit(int(p * 100)),
                            should_stop=lambda: self._stop, on_status=on_status)
            if self.language == ENGLISH:
                cues = self._english_to_malay(audio, progress)
            else:
                self.status.emit("Transcribing (Malay)…")
                cues = self.transcriber.transcribe(audio, vocabulary=self.vocabulary, **progress)
                self.device.emit(self.transcriber.device.label, self.transcriber.device.is_gpu)
            self.finished_ok.emit(cues)
        except InterruptedError:
            self.failed.emit("Cancelled.")
        except Exception as exc:  # surfaced in a dialog
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _english_to_malay(self, audio, progress: dict) -> list[Cue]:
        self.status.emit("Transcribing (English)…")
        sentences = self.transcriber.transcribe_sentences(audio, vocabulary=self.vocabulary, **progress)
        self.device.emit(self.transcriber.device.label, self.transcriber.device.is_gpu)
        self.progress.emit(-1)
        self.translator.load(self.status.emit)
        self.status.emit(f"Translating {len(sentences)} sentences to Malay…")
        self.progress.emit(0)
        texts = [sentence_text(s) for s in sentences]
        translations = self.translator.translate(texts, **{**progress, "on_status": self.status.emit})
        return english_to_malay_cues(sentences, translations, self.vocabulary)


class VocabularyDialog(QDialog):
    """Custom words (fed to Whisper as context) and auto-corrections (applied afterwards)."""

    def __init__(self, vocabulary: Vocabulary, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Vocabulary")
        self.resize(520, 460)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Custom words</b>"))
        layout.addWidget(QLabel("Names and terms this speaker uses, one per line or comma-separated. "
                                "Whisper is told to expect them.", objectName="hint", wordWrap=True))
        self.words = QPlainTextEdit("\n".join(vocabulary.custom_words))
        self.words.setPlaceholderText("dahsyat\nDr Rozaimi\nimma'ah")
        layout.addWidget(self.words)

        layout.addWidget(QLabel("<b>Auto-corrections</b>"))
        layout.addWidget(QLabel("Mistakes Whisper keeps making, one per line as  wrong = right. "
                                "Whole words only; applied after transcription.",
                                objectName="hint", wordWrap=True))
        self.corrections = QPlainTextEdit("\n".join(f"{k} = {v}" for k, v in vocabulary.corrections.items()))
        self.corrections.setPlaceholderText("rasyak = dahsyat\ntakzi = ta'zir")
        layout.addWidget(self.corrections)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def vocabulary(self) -> Vocabulary:
        return Vocabulary(custom_words=parse_words(self.words.toPlainText()),
                          corrections=parse_corrections(self.corrections.toPlainText()))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Subtitle Engine")
        self.resize(900, 640)
        self.video: str | None = None
        self.transcriber = Transcriber()
        self.translator = Translator()
        self.worker: TranscribeWorker | None = None
        self.vocabulary = Vocabulary.load()

        root = QWidget(objectName="root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(QLabel("Subtitle Engine", objectName="title"))
        titles.addWidget(QLabel("Offline Malay subtitles · faster-whisper large-v3 · English → Malay via NLLB-200", objectName="subtitle"))
        header.addLayout(titles)
        header.addStretch()
        self.badge = QLabel("Detecting device…", objectName="badge")
        self.badge.setProperty("kind", "unknown")
        header.addWidget(self.badge, alignment=Qt.AlignTop)
        layout.addLayout(header)

        buttons = QHBoxLayout()
        self.upload_btn = QPushButton("Upload")
        self.generate_btn = QPushButton("Generate", objectName="primary")
        self.export_btn = QPushButton("Export")
        self.vtt_check = QCheckBox("Also save .vtt")
        self.speech_combo = QComboBox()
        for label, code in SPEECH_OPTIONS:
            self.speech_combo.addItem(label, code)
        for b in (self.upload_btn, self.generate_btn, self.export_btn):
            buttons.addWidget(b)
        buttons.addSpacing(8)
        buttons.addWidget(self.vtt_check)
        buttons.addSpacing(8)
        buttons.addWidget(self.speech_combo)
        buttons.addStretch()
        self.vocab_btn = QPushButton("Vocabulary…", objectName="link")
        buttons.addWidget(self.vocab_btn)
        layout.addLayout(buttons)

        self.file_label = QLabel("No video selected", objectName="file")
        layout.addWidget(self.file_label)

        self.progress = QProgressBar(textVisible=False)
        self.status = QLabel("Upload a video to begin.", objectName="status")
        layout.addWidget(self.progress)
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Start", "End", "Text"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.AnyKeyPressed)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(QLabel("Double-click a cell to edit. Times use HH:MM:SS,mmm.", objectName="status"))

        self.setCentralWidget(root)
        self.setStyleSheet(STYLE)

        self.upload_btn.clicked.connect(self.choose_video)
        self.generate_btn.clicked.connect(self.generate)
        self.export_btn.clicked.connect(self.export)
        self.vocab_btn.clicked.connect(self.edit_vocabulary)
        self._update_buttons()

    # --- device badge -------------------------------------------------------
    def show_device(self, label: str, is_gpu: bool) -> None:
        self.badge.setText(label)
        self.badge.setProperty("kind", "gpu" if is_gpu else "cpu")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)

    def detect(self) -> None:
        try:
            dev = detect_device()
            self.show_device(dev.label, dev.is_gpu)
        except Exception as exc:
            self.badge.setText(f"Device check failed: {exc}")

    # --- actions ------------------------------------------------------------
    def _busy(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def _update_buttons(self) -> None:
        busy = self._busy()
        self.upload_btn.setEnabled(not busy)
        self.vocab_btn.setEnabled(not busy)
        self.speech_combo.setEnabled(not busy)
        self.generate_btn.setEnabled(not busy and self.video is not None)
        self.export_btn.setEnabled(not busy and self.table.rowCount() > 0)

    def edit_vocabulary(self) -> None:
        dialog = VocabularyDialog(self.vocabulary, self)
        if dialog.exec() == QDialog.Accepted:
            self.vocabulary = dialog.vocabulary()
            try:
                self.vocabulary.save()
            except OSError as exc:
                QMessageBox.warning(self, "Not saved", f"Vocabulary is used for now but could not be saved:\n{exc}")
            self.status.setText(f"Vocabulary saved · {len(self.vocabulary.custom_words)} custom words, "
                                f"{len(self.vocabulary.corrections)} corrections. Applies to the next Generate.")

    def choose_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select a video", "", VIDEO_FILTER)
        if path:
            self.video = path
            self.file_label.setText(Path(path).name)
            self.status.setText("Ready. Click Generate.")
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self._update_buttons()

    def generate(self) -> None:
        if not self.video:
            return
        if self.table.rowCount() and QMessageBox.question(
                self, "Replace subtitles?", "Generating again replaces the current (edited) subtitles. Continue?"
        ) != QMessageBox.Yes:
            return
        self.worker = TranscribeWorker(self.transcriber, self.translator, self.video, self.vocabulary,
                                       self.speech_combo.currentData())
        self.worker.status.connect(self.status.setText)
        self.worker.progress.connect(self._on_progress)
        self.worker.device.connect(self.show_device)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._update_buttons)
        self.worker.start()
        self._update_buttons()

    def _on_progress(self, value: int) -> None:
        if value < 0:
            self.progress.setRange(0, 0)  # indeterminate
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(value)

    def _on_done(self, cues: list[Cue]) -> None:
        self.table.setRowCount(0)
        for cue in cues:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(format_timestamp(cue.start)))
            self.table.setItem(row, 1, QTableWidgetItem(format_timestamp(cue.end)))
            self.table.setItem(row, 2, QTableWidgetItem(cue.text))
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText(f"Done · {len(cues)} subtitles. Review and edit, then Export.")
        self._update_buttons()

    def _on_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.status.setText(message.splitlines()[0])
        if message != "Cancelled.":
            QMessageBox.critical(self, "Transcription failed", message)
        self._update_buttons()

    def _cues_from_table(self) -> tuple[list[Cue], list[str]]:
        cues, errors = [], []
        for row in range(self.table.rowCount()):
            cells = [self.table.item(row, c).text() if self.table.item(row, c) else "" for c in range(3)]
            try:
                cues.append(Cue(parse_timestamp(cells[0]), parse_timestamp(cells[1]), cells[2]))
            except ValueError as exc:
                errors.append(f"Row {row + 1}: {exc}")
        return cues, errors + validate_cues(cues)

    def export(self) -> None:
        cues, errors = self._cues_from_table()
        if errors:
            QMessageBox.warning(self, "Fix these rows first", "\n".join(errors[:15]))
            return
        default = str(Path(self.video).with_suffix(".srt")) if self.video else "subtitles.srt"
        path, chosen = QFileDialog.getSaveFileName(
            self, "Export subtitles", default, "SubRip (*.srt);;WebVTT (*.vtt)")
        if not path:
            return
        target = Path(path)
        as_vtt = "vtt" in chosen.lower() or target.suffix.lower() == ".vtt"
        target = target.with_suffix(".vtt" if as_vtt else ".srt")
        written = [target]
        target.write_text(to_vtt(cues) if as_vtt else to_srt(cues), encoding="utf-8")
        if self.vtt_check.isChecked() and not as_vtt:
            vtt = target.with_suffix(".vtt")
            vtt.write_text(to_vtt(cues), encoding="utf-8")
            written.append(vtt)
        self.status.setText("Saved " + ", ".join(p.name for p in written))

    def closeEvent(self, event) -> None:
        if self._busy():
            self.worker.stop()
            self.worker.wait(5000)
        super().closeEvent(event)


def _light_palette() -> QPalette:
    """Fixed light palette so Windows dark mode can't turn unstyled widgets (cell editors,
    row headers) dark grey."""
    pal = QPalette()
    colors = {
        QPalette.Window: "#f6f7f9", QPalette.WindowText: "#1f2328", QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#fafbfc", QPalette.Text: "#1f2328", QPalette.Button: "#ffffff",
        QPalette.ButtonText: "#1f2328", QPalette.Highlight: "#1f6feb", QPalette.HighlightedText: "#ffffff",
        QPalette.ToolTipBase: "#ffffff", QPalette.ToolTipText: "#1f2328", QPalette.PlaceholderText: "#8c959f",
    }
    for role, color in colors.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#a0a7b0"))
    return pal


def run() -> int:
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")  # the native windows11 style follows the OS dark mode and ignores parts of the stylesheet
    app.setPalette(_light_palette())
    app.setWindowIcon(QIcon(str(bundle_dir() / "assets" / "app.ico")))
    window = MainWindow()
    window.show()
    app.processEvents()
    window.detect()
    return app.exec()
