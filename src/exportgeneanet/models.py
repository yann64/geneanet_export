"""In-memory representation of the genealogical data scraped from Geneanet.

These map fairly directly onto GEDCOM concepts so `gedcom_writer.py` can stay
a thin serializer rather than a second place that understands genealogy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .identifiers import PersonKey


def _sanitize_id(text: str) -> str:
    """Keep GEDCOM pointers (@...@) safe: ASCII letters/digits/underscore only."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").upper()


@dataclass
class Place:
    name: str


@dataclass
class Note:
    text: str


@dataclass
class Media:
    url: str
    title: str = ""


@dataclass
class Witness:
    person: PersonKey
    role: str | None = None  # e.g. "Godparent", "Civil officer"
    note: str | None = None


@dataclass
class Event:
    """A GEDCOM-style event: tag is e.g. "BIRT", "DEAT", "MARR", "OCCU"."""

    tag: str
    date: str | None = None
    place: Place | None = None
    note: Note | None = None
    # Subordinate TYPE value, e.g. Geneanet's own event label ("Correspondance")
    # for events mapped to the generic GEDCOM "EVEN" tag — GEDCOM expects EVEN
    # to carry a TYPE describing what kind of event it actually is.
    type: str | None = None
    # Source citation text for this specific fact (Geneanet's per-event `src`).
    # Deduplicated into GEDCOM SOUR records by gedcom_writer.py.
    source: str | None = None
    witnesses: list[Witness] = field(default_factory=list)


@dataclass
class Individual:
    key: PersonKey
    given_name: str
    surname: str
    sex: str = "U"  # "M", "F", or "U"
    events: list[Event] = field(default_factory=list)
    occupation: str | None = None
    notes: list[Note] = field(default_factory=list)
    media: list[Media] = field(default_factory=list)
    father: PersonKey | None = None
    mother: PersonKey | None = None
    family_keys: list[str] = field(default_factory=list)  # families where this person is a spouse
    source_url: str | None = None
    # General (not fact-specific) source citations, e.g. Geneanet's `psources`.
    sources: list[str] = field(default_factory=list)

    @property
    def gedcom_id(self) -> str:
        return "I" + _sanitize_id(f"{self.key.p}_{self.key.n}_{self.key.oc}")


@dataclass
class Family:
    key: str  # stable id, e.g. f"{husband_key}__{wife_key}"
    husband: PersonKey | None = None
    wife: PersonKey | None = None
    children: list[PersonKey] = field(default_factory=list)
    marriage: Event | None = None
    divorce: Event | None = None
    notes: list[Note] = field(default_factory=list)
    # General (not fact-specific) source citations, e.g. Geneanet's `fsources`.
    sources: list[str] = field(default_factory=list)

    @property
    def gedcom_id(self) -> str:
        return "F" + _sanitize_id(self.key)
