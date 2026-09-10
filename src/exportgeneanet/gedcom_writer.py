"""Serialize crawled Individuals/Families to a GEDCOM 5.5.1 file.

Hand-rolled rather than via a library: the format is simple line-based text
and we want exact control over which tags get emitted from our own models.
"""

from __future__ import annotations

from pathlib import Path

from .config import GENEANET_REPOSITORY_NAME, GENEANET_REPOSITORY_WWW
from .models import Event, Family, Individual, Note, SourceCitation

_MAX_LINE_CHARS = 200  # conservative CONC threshold; GEDCOM 5.5.1 caps at 255
_GENEANET_REPOSITORY_ID = "R1"


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
            chunks = [paragraph[i : i + _MAX_LINE_CHARS] for i in range(0, len(paragraph), _MAX_LINE_CHARS)] or [""]
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


def _collect_source_ids(
    individuals: dict[str, Individual], families: dict[str, Family]
) -> tuple[dict[str, str], set[str]]:
    """Assign a stable `@S<n>@` id to every distinct source citation *title*
    found anywhere (events, and Individual/Family general sources), so
    repeated citations (the same archival record cited for several facts, or
    the shared Geneanet-tree attribution every fact carries) become one SOUR
    record referenced by pointer rather than duplicated free text.

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
    source_ids: dict[str, str],
    include_notes: bool = True,
) -> None:
    g.add(level, event.tag)
    if event.type:
        g.add(level + 1, "TYPE", event.type)
    if event.date:
        g.add(level + 1, "DATE", event.date)
    if event.place:
        g.add(level + 1, "PLAC", event.place.name)
    if event.note and include_notes:
        g.add_text(level + 1, "NOTE", event.note.text)
    _write_sources(g, level + 1, event.sources, source_ids)
    for witness in event.witnesses:
        # Only link a witness who is actually part of this export — never
        # fabricate an INDI record just because someone was mentioned as a
        # witness (that would silently expand the requested export scope).
        witness_individual = individuals.get(str(witness.person))
        if witness_individual is None:
            continue
        g.add(level + 1, "ASSO", f"@{witness_individual.gedcom_id}@")
        g.add(level + 2, "TYPE", "INDI")
        if witness.role:
            g.add(level + 2, "RELA", witness.role)
        if witness.note and include_notes:
            g.add_text(level + 2, "NOTE", witness.note)


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

    source_ids, geneanet_titles = _collect_source_ids(individuals, families)

    # FAMC (family where the individual is a child) is derived from the
    # families' child lists, since Individual only stores father/mother keys.
    famc_by_person: dict[str, str] = {}
    for fam in families.values():
        for child in fam.children:
            famc_by_person[str(child)] = fam.gedcom_id

    for key, individual in individuals.items():
        g.add(0, f"@{individual.gedcom_id}@", "INDI")
        g.add(1, "NAME", f"{individual.given_name} /{individual.surname}/")
        g.add(2, "GIVN", individual.given_name)
        g.add(2, "SURN", individual.surname)
        if individual.sex in ("M", "F"):
            g.add(1, "SEX", individual.sex)

        for event in individual.events:
            _write_event(g, 1, event, individuals, source_ids, include_notes)

        if individual.occupation:
            g.add(1, "OCCU", individual.occupation)

        if include_notes:
            _write_notes(g, 1, individual.notes)

        _write_sources(g, 1, individual.sources, source_ids)

        if include_media:
            for media in individual.media:
                g.add(1, "OBJE")
                g.add(2, "FILE", media.url)
                if media.title:
                    g.add(2, "TITL", media.title)

        famc = famc_by_person.get(key)
        if famc:
            g.add(1, "FAMC", f"@{famc}@")
        for fam_key in individual.family_keys:
            fam = families.get(fam_key)
            if fam:
                g.add(1, "FAMS", f"@{fam.gedcom_id}@")

    for fam_key, fam in families.items():
        g.add(0, f"@{fam.gedcom_id}@", "FAM")
        if fam.husband and str(fam.husband) in individuals:
            g.add(1, "HUSB", f"@{individuals[str(fam.husband)].gedcom_id}@")
        if fam.wife and str(fam.wife) in individuals:
            g.add(1, "WIFE", f"@{individuals[str(fam.wife)].gedcom_id}@")
        for child in fam.children:
            if str(child) in individuals:
                g.add(1, "CHIL", f"@{individuals[str(child)].gedcom_id}@")
        if fam.marriage:
            _write_event(g, 1, fam.marriage, individuals, source_ids, include_notes)
        if fam.divorce:
            _write_event(g, 1, fam.divorce, individuals, source_ids, include_notes)
        if include_notes:
            _write_notes(g, 1, fam.notes)
        _write_sources(g, 1, fam.sources, source_ids)

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
    content = generate_gedcom(
        individuals, families, include_notes=include_notes, include_media=include_media
    )
    path.write_text(content, encoding="utf-8")
