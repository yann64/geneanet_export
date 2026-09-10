"""In-memory representation of the genealogical data scraped from Geneanet.

Format-agnostic by design (despite a few GEDCOM-flavored field names, e.g.
`Event.tag`) — both `gedcom_writer.py` and `gramps_writer.py` serialize
these same dataclasses, so either stays a thin serializer rather than a
second place that understands genealogy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .identifiers import PersonKey


@dataclass
class Place:
    name: str


@dataclass(frozen=True)
class PartialDate:
    """One point in time with GeneWeb's partial-precision semantics: year is
    always known, `month`/`day` may be `0` (unknown) — the same convention
    GeneWeb's own `*_date_raw` encoding already uses, so `mapping.py`'s
    parser can build this directly without inventing a new precision
    scheme."""

    year: int
    month: int = 0
    day: int = 0


@dataclass(frozen=True)
class GenealogyDate:
    """A format-agnostic date, parsed once by `mapping.py` and rendered by
    each writer into its own textual/structured syntax (GEDCOM's `DATE`
    value string / Gramps's `dateval`+`daterange` elements) — keeps the
    GeneWeb date-precision parsing itself shared rather than duplicated per
    writer. Exactly one of `date` or `range_start`+`range_end` is set for a
    successfully parsed date; `fallback_text` is set instead (with
    everything else left at its default) when parsing wasn't possible —
    e.g. an unrecognized calendar, where Geneanet's own localized display
    text is used rather than risk emitting a wrong date."""

    qualifier: str | None = None  # None | "EST" | "ABT" | "BEF" | "AFT" (GEDCOM vocabulary)
    date: PartialDate | None = None  # a single point in time
    range_start: PartialDate | None = None  # BET...AND, together with range_end
    range_end: PartialDate | None = None
    calendar: str = "GREGORIAN"  # or "JULIAN"
    fallback_text: str | None = None


@dataclass
class Note:
    text: str


@dataclass
class Media:
    url: str
    title: str = ""
    # Same Geneanet-tree-attribution citation every other fact carries (see
    # mapping.geneanet_tree_citation) — gedcom_writer.py emits Media as a
    # standalone GEDCOM OBJE record specifically so it can carry a
    # SOURCE_CITATION substructure (the embedded MULTIMEDIA_LINK form used
    # by earlier versions of this writer can't).
    sources: list[SourceCitation] = field(default_factory=list)


@dataclass
class Witness:
    """A person + their role, attached either to an `Event` (a witness) or
    directly to an `Individual` (a godparent/adoptive/foster relation, etc.
    — see `Individual.associations`) — both become a GEDCOM ASSO/RELA
    structure, just at different levels, so this one shape covers both."""

    person: PersonKey
    role: str | None = None  # e.g. "Godparent", "Civil officer"
    note: str | None = None


@dataclass
class AlternateName:
    """A GEDCOM alternate NAME record (`Individual.names`). `surname=None`
    means Geneanet gave a single free-text alias it can't be reliably split
    into given/surname (e.g. "Marguerite Chauzy" could be a multi-word
    surname) — emitted unslashed rather than risk a wrong split."""

    given: str
    surname: str | None = None
    type: str = "aka"  # GEDCOM NAME_TYPE: aka/birth/immigrant/maiden/married/...


@dataclass
class SourceCitation:
    """A GEDCOM SOURCE_CITATION. `title` identifies which shared SOUR record
    this belongs to — gedcom_writer.py dedupes citations with equal `title`
    into one record, so the same archival act cited on several facts (or the
    same Geneanet-tree attribution cited on every fact) becomes one SOUR
    referenced by pointer rather than repeated free text. `page` is that
    citation's own SOURCE_CITATION.PAGE (e.g. a specific person's URL) and
    varies per instance even when `title` is shared."""

    title: str
    page: str | None = None
    # True only for the Geneanet-tree-attribution citation every mapped
    # fact gets (see mapping.geneanet_tree_citation) — tells gedcom_writer.py
    # to link that SOUR record to the "Geneanet" REPO record. Never set for
    # Geneanet's own archival-source text (psources/fsources/*_src): those
    # are sourced from the underlying civil/church archive, not from
    # Geneanet-as-a-repository.
    is_geneanet_source: bool = False


@dataclass
class Event:
    """A GEDCOM-style event: tag is e.g. "BIRT", "DEAT", "MARR", "OCCU"."""

    tag: str
    date: GenealogyDate | None = None
    place: Place | None = None
    note: Note | None = None
    # Subordinate TYPE value, e.g. Geneanet's own event label ("Correspondance")
    # for events mapped to the generic GEDCOM "EVEN" tag — GEDCOM expects EVEN
    # to carry a TYPE describing what kind of event it actually is.
    type: str | None = None
    sources: list[SourceCitation] = field(default_factory=list)
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
    # This person's own Geneanet page URL — citation-only (see
    # mapping.person_citation_url), this project never fetches it.
    source_url: str | None = None
    # General (not fact-specific) source citations, e.g. Geneanet's `psources`.
    sources: list[SourceCitation] = field(default_factory=list)
    nickname: str | None = None  # Geneanet's `qualifiers` ("sobriquet")
    titles: list[str] = field(default_factory=list)  # e.g. nobility titles
    names: list[AlternateName] = field(default_factory=list)
    # Godparent/adoptive/foster/etc. relations (Geneanet's `rparents` +
    # `related`) — privacy-checked like any other person reference; see
    # `Witness`'s docstring for why this reuses that type.
    associations: list[Witness] = field(default_factory=list)


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
    sources: list[SourceCitation] = field(default_factory=list)
