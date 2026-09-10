"""PersonSearchWidget: a lastname/firstname search box + results list, for
picking the seed individual(s) a `MainWindow` export uses — the GUI
replacement for hand-typing `--individual given.surname.oc`.

Doesn't talk to the API itself: emits `search_requested` and lets
`MainWindow` (which owns the `CrawlWorker`) drive the actual call, then
feeds results back in via `set_results`. Keeps this widget dumb/testable and
matches the project's "only one client, one worker" rule (search_widget.py
has no way to accidentally create a second one).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget

from ..identifiers import PersonKey


@dataclass(frozen=True)
class SearchResultRow:
    """One search hit, formatted for display. A pure function
    (`search_result_rows`) builds these from the raw API response so the
    conversion is unit-testable without a `QApplication`."""

    key: PersonKey
    label: str


def search_result_rows(persons: list[dict]) -> list[SearchResultRow]:
    """`persons` is `PersonSearchList.persons` (via `MessageToDict`) from
    `GeneanetApiClient.search_persons`. Skips any entry missing a usable
    `reference` (shouldn't normally happen, but stay defensive)."""
    rows = []
    for person in persons:
        ref = person.get("reference", {})
        if not ref.get("p") or not ref.get("n"):
            continue
        key = PersonKey(p=ref["p"], n=ref["n"], oc=int(ref.get("oc", 0)))
        given = person.get("firstname", ref["p"])
        surname = person.get("lastname", ref["n"])
        dates = person.get("dates")
        label = f"{given} {surname}" + (f" ({dates})" if dates else "")
        rows.append(SearchResultRow(key=key, label=label))
    return rows


class PersonSearchWidget(QWidget):
    search_requested = Signal(str, str)  # lastname, firstname
    person_selected = Signal(object)  # PersonKey

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[SearchResultRow] = []

        self._lastname_field = QLineEdit()
        self._lastname_field.setPlaceholderText("Surname")
        self._lastname_field.returnPressed.connect(self._emit_search_requested)
        self._firstname_field = QLineEdit()
        self._firstname_field.setPlaceholderText("Given name (optional)")
        self._firstname_field.returnPressed.connect(self._emit_search_requested)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._emit_search_requested)

        self._results_list = QListWidget()

        add_button = QPushButton("Add selected to export")
        add_button.clicked.connect(self._emit_person_selected)

        search_row = QHBoxLayout()
        search_row.addWidget(self._lastname_field)
        search_row.addWidget(self._firstname_field)
        search_row.addWidget(search_button)

        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addWidget(self._results_list)
        layout.addWidget(add_button)

    def _emit_search_requested(self) -> None:
        self.search_requested.emit(self._lastname_field.text().strip(), self._firstname_field.text().strip())

    def set_results(self, persons: list[dict]) -> None:
        self._rows = search_result_rows(persons)
        self._results_list.clear()
        for row in self._rows:
            self._results_list.addItem(f"{row.label}  —  {row.key}")

    def _emit_person_selected(self) -> None:
        index = self._results_list.currentRow()
        if 0 <= index < len(self._rows):
            self.person_selected.emit(self._rows[index].key)
