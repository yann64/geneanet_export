"""Serialize crawled Individuals/Families to a GEDCOM 5.5.1 file.

Hand-rolled rather than via a library: the format is simple line-based text
and we want exact control over which tags get emitted from our own models.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .config import GENEANET_REPOSITORY_NAME, GENEANET_REPOSITORY_WWW
from .models import Event, Family, GenealogyDate, Individual, Media, Note, SourceCitation, Witness

_MAX_LINE_CHARS = 200  # conservative CONC threshold; GEDCOM 5.5.1 caps at 255
_GENEANET_REPOSITORY_ID = "R1"

_MONTH_ABBR = [
    None,
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]

# GEDCOM calendar escape for calendars where GenealogyDate's Y/M/D numbers
# are straightforward (Gregorian needs no escape; Julian uses the same D/M/Y
# numbering — see mapping._PARSEABLE_RAW_CALENDARS).
_CALENDAR_ESCAPE = {"JULIAN": "@#DJULIAN@"}


def _format_dmy(year: int, month: int, day: int) -> str:
    parts = []
    if month and day:
        parts.append(str(day))
    if month:
        parts.append(_MONTH_ABBR[month])
    parts.append(str(year))
    return " ".join(parts)


def _render_gedcom_date(d: GenealogyDate) -> str:
    """Render a `GenealogyDate` into a GEDCOM 5.5.1 DATE value (`DD MON
    YYYY`, with ABT/EST/BEF/AFT/BET...AND qualifiers as needed) — the exact
    same output the old `mapping.gedcom_date()` used to produce directly,
    before it split into `mapping.parse_geneweb_date()` (parsing) and this
    function (rendering). `fallback_text` (Geneanet's own
    localized display text, not GEDCOM-valid) passes straight through
    unchanged, same as before."""
    if d.fallback_text is not None:
        return d.fallback_text
    if d.range_start and d.range_end:
        left = _format_dmy(d.range_start.year, d.range_start.month, d.range_start.day)
        right = _format_dmy(d.range_end.year, d.range_end.month, d.range_end.day)
        return f"BET {left} AND {right}"
    dmy = _format_dmy(d.date.year, d.date.month, d.date.day)
    rendered = f"{d.qualifier} {dmy}" if d.qualifier else dmy
    escape = _CALENDAR_ESCAPE.get(d.calendar)
    return f"{escape} {rendered}" if escape else rendered


class GedcomLines:
    def __init__(self) -> None:
        self._lines: list[str] = []

    def add(self, level: int, tag: str, value: str = "") -> None:
        line = f"{level} {tag}" if value == "" else f"{level} {tag} {value}"
        self._lines.append(line)

    def add_text(self, level: int, tag: str, text: str) -> None:
        """Emit `text` under `tag`, splitting on newlines (CONT) and long runs
        of text (CONC), per the GEDCOM line-length convention."""
        paragraphs = text.split("\n")
        first = True
        for paragraph in paragraphs:
            chunks = [
                paragraph[i : i + _MAX_LINE_CHARS] for i in range(0, len(paragraph), _MAX_LINE_CHARS)
            ] or [""]
            for j, chunk in enumerate(chunks):
                if first:
                    self.add(level, tag, chunk)
                    first = False
                elif j == 0:
                    self.add(level + 1, "CONT", chunk)
                else:
                    self.add(level + 1, "CONC", chunk)

    def render(self) -> str:
        return "\n".join(self._lines) + "\n"


def _number_ids(keys: Iterable[str], prefix: str) -> dict[str, str]:
    """Assign sequential GEDCOM pointer ids (`I1`, `I2`, ... / `F1`, `F2`,
    ...) in iteration order — plain sequential numbers rather than ids
    derived from the person's/family's name, matching normal GEDCOM
    convention (and avoiding very long or illegible pointers for long
    names/non-Latin scripts)."""
    return {key: f"{prefix}{i}" for i, key in enumerate(keys, start=1)}


def _collect_source_ids(
    individuals: dict[str, Individual], families: dict[str, Family], include_media: bool = True
) -> tuple[dict[str, str], set[str]]:
    """Assign a stable `@S<n>@` id to every distinct source citation *title*
    found anywhere (events, Individual/Family general sources, and — when
    `include_media` — Media sources), so repeated citations (the same
    archival record cited for several facts, or the shared Geneanet-tree
    attribution every fact carries) become one SOUR record referenced by
    pointer rather than duplicated free text.

    Also returns the subset of titles that are the Geneanet-tree attribution
    (`SourceCitation.is_geneanet_source`) — only those get linked to the
    "Geneanet" REPO record; Geneanet's own archival citation text
    (psources/fsources/*_src) is sourced from the underlying civil/church
    archive, not from Geneanet-as-a-repository, so this project never
    fabricates a REPO record for those.
    """
    source_ids: dict[str, str] = {}
    geneanet_titles: set[str] = set()

    def register(citations: list[SourceCitation]) -> None:
        for citation in citations:
            if citation.title not in source_ids:
                source_ids[citation.title] = f"S{len(source_ids) + 1}"
            if citation.is_geneanet_source:
                geneanet_titles.add(citation.title)

    for individual in individuals.values():
        register(individual.sources)
        for event in individual.events:
            register(event.sources)
        if include_media:
            for media in individual.media:
                register(media.sources)

    for family in families.values():
        register(family.sources)
        if family.marriage:
            register(family.marriage.sources)
        if family.divorce:
            register(family.divorce.sources)

    return source_ids, geneanet_titles


def _write_event(
    g: GedcomLines,
    level: int,
    event: Event,
    individuals: dict[str, Individual],
    individual_ids: dict[str, str],
    source_ids: dict[str, str],
    include_notes: bool = True,
) -> None:
    g.add(level, event.tag)
    if event.type:
        g.add(level + 1, "TYPE", event.type)
    if event.date:
        g.add(level + 1, "DATE", _render_gedcom_date(event.date))
    if event.place:
        g.add(level + 1, "PLAC", event.place.name)
    if event.note and include_notes:
        g.add_text(level + 1, "NOTE", event.note.text)
    _write_sources(g, level + 1, event.sources, source_ids)
    _write_associations(g, level + 1, event.witnesses, individuals, individual_ids, include_notes)


def _write_associations(
    g: GedcomLines,
    level: int,
    associations: list[Witness],
    individuals: dict[str, Individual],
    individual_ids: dict[str, str],
    include_notes: bool = True,
) -> None:
    """Shared by event witnesses and `Individual.associations` (godparent/
    adoptive/etc. relations) — both are a GEDCOM ASSO/RELA structure, just
    attached at different levels."""
    for assoc in associations:
        # Only link a person who is actually part of this export — never
        # fabricate an INDI record just because someone was referenced as a
        # witness/relation (that would silently expand the export scope).
        assoc_key = str(assoc.person)
        if assoc_key not in individuals:
            continue
        g.add(level, "ASSO", f"@{individual_ids[assoc_key]}@")
        g.add(level + 1, "TYPE", "INDI")
        if assoc.role:
            g.add(level + 1, "RELA", assoc.role)
        if assoc.note and include_notes:
            g.add_text(level + 1, "NOTE", assoc.note)


def _write_notes(g: GedcomLines, level: int, notes: list[Note]) -> None:
    for note in notes:
        g.add_text(level, "NOTE", note.text)


def _write_sources(
    g: GedcomLines, level: int, citations: list[SourceCitation], source_ids: dict[str, str]
) -> None:
    for citation in citations:
        source_id = source_ids.get(citation.title)
        if not source_id:
            continue
        g.add(level, "SOUR", f"@{source_id}@")
        if citation.page:
            g.add(level + 1, "PAGE", citation.page)


def generate_gedcom(
    individuals: dict[str, Individual],
    families: dict[str, Family],
    include_notes: bool = True,
    include_media: bool = True,
) -> str:
    g = GedcomLines()

    g.add(0, "HEAD")
    g.add(1, "SOUR", "ExportGeneanet")
    g.add(1, "GEDC")
    g.add(2, "VERS", "5.5.1")
    g.add(2, "FORM", "LINEAGE-LINKED")
    g.add(1, "CHAR", "UTF-8")

    source_ids, geneanet_titles = _collect_source_ids(individuals, families, include_media)
    individual_ids = _number_ids(individuals.keys(), "I")
    family_ids = _number_ids(families.keys(), "F")

    # Media becomes a standalone OBJE record (not an embedded MULTIMEDIA_LINK)
    # specifically so it can carry a SOURCE_CITATION — assign ids up front in
    # a fixed order so the INDI loop below can emit pointers before the
    # records themselves are written out.
    media_records: list[tuple[str, Media]] = []
    if include_media:
        for individual in individuals.values():
            for media in individual.media:
                media_records.append((f"O{len(media_records) + 1}", media))
    media_ids = {id(media): media_id for media_id, media in media_records}

    # FAMC (family where the individual is a child) is derived from the
    # families' child lists, since Individual only stores father/mother keys.
    famc_by_person: dict[str, str] = {}
    for fam_key, fam in families.items():
        for child in fam.children:
            famc_by_person[str(child)] = family_ids[fam_key]

    for key, individual in individuals.items():
        g.add(0, f"@{individual_ids[key]}@", "INDI")
        g.add(1, "NAME", f"{individual.given_name} /{individual.surname}/")
        g.add(2, "GIVN", individual.given_name)
        g.add(2, "SURN", individual.surname)
        if individual.nickname:
            g.add(2, "NICK", individual.nickname)
        if individual.sex in ("M", "F"):
            g.add(1, "SEX", individual.sex)

        for alt_name in individual.names:
            if alt_name.surname is not None:
                g.add(1, "NAME", f"{alt_name.given} /{alt_name.surname}/")
            else:
                g.add(1, "NAME", alt_name.given)
            g.add(2, "TYPE", alt_name.type)

        for event in individual.events:
            _write_event(g, 1, event, individuals, individual_ids, source_ids, include_notes)

        if individual.occupation:
            g.add(1, "OCCU", individual.occupation)

        for title in individual.titles:
            g.add(1, "TITL", title)

        if include_notes:
            _write_notes(g, 1, individual.notes)

        _write_sources(g, 1, individual.sources, source_ids)

        _write_associations(g, 1, individual.associations, individuals, individual_ids, include_notes)

        if include_media:
            for media in individual.media:
                g.add(1, "OBJE", f"@{media_ids[id(media)]}@")

        famc = famc_by_person.get(key)
        if famc:
            g.add(1, "FAMC", f"@{famc}@")
        for fam_key in individual.family_keys:
            if fam_key in families:
                g.add(1, "FAMS", f"@{family_ids[fam_key]}@")

    for fam_key, fam in families.items():
        g.add(0, f"@{family_ids[fam_key]}@", "FAM")
        if fam.husband and str(fam.husband) in individuals:
            g.add(1, "HUSB", f"@{individual_ids[str(fam.husband)]}@")
        if fam.wife and str(fam.wife) in individuals:
            g.add(1, "WIFE", f"@{individual_ids[str(fam.wife)]}@")
        for child in fam.children:
            if str(child) in individuals:
                g.add(1, "CHIL", f"@{individual_ids[str(child)]}@")
        if fam.marriage:
            _write_event(g, 1, fam.marriage, individuals, individual_ids, source_ids, include_notes)
        if fam.divorce:
            _write_event(g, 1, fam.divorce, individuals, individual_ids, source_ids, include_notes)
        if include_notes:
            _write_notes(g, 1, fam.notes)
        _write_sources(g, 1, fam.sources, source_ids)

    for media_id, media in media_records:
        g.add(0, f"@{media_id}@", "OBJE")
        g.add(1, "FILE", str(media.local_path) if media.local_path else media.url)
        if media.title:
            g.add(1, "TITL", media.title)
        _write_sources(g, 1, media.sources, source_ids)

    if geneanet_titles:
        g.add(0, f"@{_GENEANET_REPOSITORY_ID}@", "REPO")
        g.add(1, "NAME", GENEANET_REPOSITORY_NAME)
        g.add(1, "WWW", GENEANET_REPOSITORY_WWW)

    for title, source_id in source_ids.items():
        g.add(0, f"@{source_id}@", "SOUR")
        g.add_text(1, "TITL", title)
        if title in geneanet_titles:
            g.add(1, "REPO", f"@{_GENEANET_REPOSITORY_ID}@")

    g.add(0, "TRLR")
    return g.render()


def write_gedcom_file(
    path: Path,
    individuals: dict[str, Individual],
    families: dict[str, Family],
    include_notes: bool = True,
    include_media: bool = True,
) -> None:
    content = generate_gedcom(individuals, families, include_notes=include_notes, include_media=include_media)
    path.write_text(content, encoding="utf-8")
