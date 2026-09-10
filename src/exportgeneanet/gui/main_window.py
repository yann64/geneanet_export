"""MainWindow: the whole exportgeneanet-gui window.

v1 scope is CLI parity — everything here maps directly onto
`cli.py export`'s options (scope, seeds, nb_asc, include_notes/media,
resume, min/max delay, lang) plus a search-based picker replacing having to
type `given.surname.oc` by hand.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_LANG, DEFAULT_MAX_DELAY_SECONDS, DEFAULT_MIN_DELAY_SECONDS
from ..identifiers import PersonKey
from ..models import Individual
from ..tree_crawler import CrawlState
from .crawl_worker import CrawlWorker
from .search_widget import PersonSearchWidget


def default_state_path(username: str, scope: str) -> Path:
    """Same naming convention as `cli.py`'s default, so a checkpoint started
    in the CLI can be resumed in the GUI and vice versa."""
    return Path.cwd() / f"crawl-state-{username}-{scope}.json"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ExportGeneanet")
        self.resize(720, 720)

        self._worker: CrawlWorker | None = None
        self._worker_username: str | None = None
        self._seeds: list[PersonKey] = []
        self._output_path: Path | None = None

        self._build_ui()

    # ---------------------------------------------------------------- UI --

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        username_row = QHBoxLayout()
        username_row.addWidget(QLabel("Geneanet username:"))
        self._username_field = QLineEdit()
        self._username_field.setPlaceholderText("e.g. yann64")
        username_row.addWidget(self._username_field)
        layout.addLayout(username_row)

        self._search_widget = PersonSearchWidget()
        self._search_widget.search_requested.connect(self._on_search_requested)
        self._search_widget.person_selected.connect(self._add_seed)
        layout.addWidget(self._search_widget)

        seeds_group = QGroupBox("Selected individual(s)")
        seeds_layout = QVBoxLayout(seeds_group)
        self._seeds_list = QListWidget()
        seeds_layout.addWidget(self._seeds_list)
        remove_button = QPushButton("Remove selected")
        remove_button.clicked.connect(self._remove_selected_seed)
        seeds_layout.addWidget(remove_button)
        layout.addWidget(seeds_group)

        scope_group = QGroupBox("Scope")
        scope_layout = QHBoxLayout(scope_group)
        self._scope_all = QRadioButton("All (full tree)")
        self._scope_ascendants = QRadioButton("Ascendants")
        self._scope_ascendants.setChecked(True)
        scope_layout.addWidget(self._scope_all)
        scope_layout.addWidget(self._scope_ascendants)
        scope_layout.addWidget(QLabel("Generations:"))
        self._nb_asc = QSpinBox()
        self._nb_asc.setRange(1, 50)
        self._nb_asc.setValue(20)
        scope_layout.addWidget(self._nb_asc)
        self._scope_ascendants.toggled.connect(self._nb_asc.setEnabled)
        layout.addWidget(scope_group)

        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        self._include_notes = QCheckBox("Include notes")
        self._include_notes.setChecked(True)
        self._include_media = QCheckBox("Include media")
        self._include_media.setChecked(True)
        self._resume = QCheckBox("Resume from checkpoint if one exists for this username/scope")
        options_layout.addWidget(self._include_notes)
        options_layout.addWidget(self._include_media)
        options_layout.addWidget(self._resume)
        layout.addWidget(options_group)

        output_row = QHBoxLayout()
        self._output_field = QLineEdit()
        self._output_field.setReadOnly(True)
        self._output_field.setPlaceholderText("Choose where to save the .ged file…")
        output_button = QPushButton("Choose output file…")
        output_button.clicked.connect(self._choose_output)
        output_row.addWidget(self._output_field)
        output_row.addWidget(output_button)
        layout.addLayout(output_row)

        advanced_group = QGroupBox("Advanced")
        advanced_layout = QFormLayout(advanced_group)
        self._lang_field = QLineEdit(DEFAULT_LANG)
        self._min_delay = QDoubleSpinBox()
        self._min_delay.setRange(0.0, 120.0)
        self._min_delay.setValue(DEFAULT_MIN_DELAY_SECONDS)
        self._max_delay = QDoubleSpinBox()
        self._max_delay.setRange(0.0, 120.0)
        self._max_delay.setValue(DEFAULT_MAX_DELAY_SECONDS)
        advanced_layout.addRow("Language:", self._lang_field)
        advanced_layout.addRow("Min delay (s):", self._min_delay)
        advanced_layout.addRow("Max delay (s):", self._max_delay)
        layout.addWidget(advanced_group)

        buttons_row = QHBoxLayout()
        self._start_button = QPushButton("Start export")
        self._start_button.clicked.connect(self._start_export)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._cancel_export)
        buttons_row.addWidget(self._start_button)
        buttons_row.addWidget(self._cancel_button)
        layout.addLayout(buttons_row)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        layout.addWidget(self._progress_bar)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        layout.addWidget(self._log)

    # --------------------------------------------------- worker lifecycle --

    def _get_worker(self) -> CrawlWorker:
        username = self._username_field.text().strip()
        if not username:
            raise ValueError("Enter a Geneanet username first.")
        if self._worker is None or self._worker_username != username:
            if self._worker is not None:
                self._worker.stop()
                self._worker.wait()
            worker = CrawlWorker(
                username,
                self._lang_field.text().strip() or DEFAULT_LANG,
                self._min_delay.value(),
                self._max_delay.value(),
            )
            worker.search_results.connect(self._on_search_results)
            worker.search_failed.connect(self._on_search_failed)
            worker.progress.connect(self._on_progress)
            worker.export_finished.connect(self._on_export_finished)
            worker.export_cancelled.connect(self._on_export_cancelled)
            worker.export_failed.connect(self._on_export_failed)
            worker.start()
            self._worker = worker
            self._worker_username = username
        return self._worker

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait()
        super().closeEvent(event)

    # ------------------------------------------------------------ search --

    def _on_search_requested(self, lastname: str, firstname: str) -> None:
        try:
            self._get_worker().submit_search(lastname, firstname)
        except ValueError as exc:
            QMessageBox.warning(self, "Missing username", str(exc))

    def _on_search_results(self, persons: list) -> None:
        self._search_widget.set_results(persons)
        if not persons:
            QMessageBox.information(self, "No results", "No individuals matched that search.")

    def _on_search_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Search failed", message)

    # -------------------------------------------------------------- seeds --

    def _add_seed(self, key: PersonKey) -> None:
        if key in self._seeds:
            return
        self._seeds.append(key)
        self._seeds_list.addItem(str(key))

    def _remove_selected_seed(self) -> None:
        index = self._seeds_list.currentRow()
        if 0 <= index < len(self._seeds):
            del self._seeds[index]
            self._seeds_list.takeItem(index)

    # ------------------------------------------------------------- output --

    def _choose_output(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(self, "Save GEDCOM as", filter="GEDCOM files (*.ged)")
        if path_str:
            self._output_path = Path(path_str)
            self._output_field.setText(path_str)

    # ------------------------------------------------------------- export --

    def _start_export(self) -> None:
        username = self._username_field.text().strip()
        if not username:
            QMessageBox.warning(self, "Missing username", "Enter a Geneanet username first.")
            return
        if not self._seeds:
            QMessageBox.warning(self, "No individual selected", "Search for and add at least one individual.")
            return
        if self._output_path is None:
            QMessageBox.warning(self, "No output file", "Choose where to save the .ged file first.")
            return

        scope = "all" if self._scope_all.isChecked() else "ascendants"
        # Always pass a state_path (even if "resume" isn't checked) so a
        # cancellation mid-crawl stays recoverable — see CrawlCancelled.
        state_path = default_state_path(username, scope)
        state = CrawlState.load(state_path) if self._resume.isChecked() and state_path.exists() else None

        try:
            worker = self._get_worker()
        except ValueError as exc:
            QMessageBox.warning(self, "Missing username", str(exc))
            return

        self._log.clear()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setValue(0)
        self._start_button.setEnabled(False)
        self._cancel_button.setEnabled(True)

        worker.submit_export(
            scope,
            list(self._seeds),
            self._output_path,
            self._nb_asc.value(),
            self._include_notes.isChecked(),
            self._include_media.isChecked(),
            state,
            state_path,
        )

    def _cancel_export(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
        self._cancel_button.setEnabled(False)

    def _on_progress(self, individual: Individual, done: int | None, total: int | None) -> None:
        if total is not None:
            if self._progress_bar.maximum() != total:
                self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(done or 0)
        self._log.appendPlainText(f"[{done}/{total or '?'}] {individual.given_name} {individual.surname}")

    def _on_export_finished(self, state: CrawlState, output: Path | None) -> None:
        self._start_button.setEnabled(True)
        self._cancel_button.setEnabled(False)
        self._progress_bar.setRange(0, 1)
        self._progress_bar.setValue(1)
        message = f"Wrote {len(state.individuals)} individuals / {len(state.families)} families to {output}"
        self._log.appendPlainText(message)
        QMessageBox.information(self, "Export complete", message)

    def _on_export_cancelled(self, state: CrawlState) -> None:
        self._start_button.setEnabled(True)
        self._cancel_button.setEnabled(False)
        message = (
            f"Cancelled — {len(state.individuals)} individuals saved to checkpoint. "
            'Check "Resume" and start again to continue.'
        )
        self._log.appendPlainText(message)
        QMessageBox.information(self, "Export cancelled", message)

    def _on_export_failed(self, message: str) -> None:
        self._start_button.setEnabled(True)
        self._cancel_button.setEnabled(False)
        QMessageBox.critical(self, "Export failed", message)
