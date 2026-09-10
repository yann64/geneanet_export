import pytest

pytest.importorskip("PySide6")

from exportgeneanet.gui.search_widget import SearchResultRow, search_result_rows  # noqa: E402
from exportgeneanet.identifiers import PersonKey  # noqa: E402


def test_search_result_rows_builds_key_and_label():
    persons = [
        {
            "index": 7,
            "firstname": "Étienne",
            "lastname": "Barbel",
            "dates": "1882-1963",
            "reference": {"p": "etienne", "n": "barbel", "oc": 0},
        }
    ]
    rows = search_result_rows(persons)
    assert rows == [
        SearchResultRow(key=PersonKey(p="etienne", n="barbel", oc=0), label="Étienne Barbel (1882-1963)")
    ]


def test_search_result_rows_without_dates():
    persons = [
        {
            "firstname": "Jean",
            "lastname": "Dupont",
            "reference": {"p": "jean", "n": "dupont", "oc": 0},
        }
    ]
    rows = search_result_rows(persons)
    assert rows[0].label == "Jean Dupont"


def test_search_result_rows_skips_entries_without_reference():
    persons = [{"firstname": "Jean", "lastname": "Dupont"}]
    assert search_result_rows(persons) == []


def test_search_result_rows_uses_occurrence_number():
    persons = [
        {
            "firstname": "Guillaume",
            "lastname": "Barbel",
            "reference": {"p": "guillaume", "n": "barbel", "oc": 2},
        }
    ]
    rows = search_result_rows(persons)
    assert rows[0].key == PersonKey(p="guillaume", n="barbel", oc=2)
