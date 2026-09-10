"""Serialize crawled Individuals/Families to a Gramps XML 1.7.1 file.

Built with `xml.etree.ElementTree` (unlike gedcom_writer.py's hand-rolled
line builder — GEDCOM is naturally line-based, Gramps XML is naturally a
tree). Structural notes on how this differs from GEDCOM, since Gramps's
data model isn't just "the same facts in XML syntax":

- Every fact is a top-level record (`person`, `family`, `event`, `source`,
  `citation`, `repository`, `note`, `object` (media), `placeobj`), cross
  referenced by `hlink` pointers — GEDCOM's inline MARR/DEAT-under-INDI
  embedding has no equivalent here; every event, including a family's
  marriage/divorce, is its own `<event>` record referenced via
  `<eventref>`.
- Sources split into two tiers: `<source>` (the bibliographic record) +
  `<citation>` (one specific use of it, carrying the per-use `<page>`) —
  see `SourceCitation`'s docstring; dedupe `Source` by `title` (same as
  `gedcom_writer._collect_source_ids` dedupes `SOUR`), `Citation` by
  `(title, page)`.
- **Event witnesses point the opposite direction from GEDCOM's ASSO.**
  Gramps has no "this event has these witnesses" field at all — instead,
  the *witness's own* `<person>` record gets an `<eventref
  role="Witness">` pointing at the event (same mechanism a spouse's own
  participation in their marriage uses, just with a different `role`).
  `Individual.associations` (godparent/adoptive/etc. — a person-to-person
  relation, not an event) maps directly to `<personref rel="...">`
  instead, which *is* a close GEDCOM-ASSO equivalent.
- **Places are matched against `places_reference.py`'s bundled hierarchy**
  so a place already in the user's reference Gramps database's place tree
  reuses the exact same `handle`/`id` (see that module's docstring) —
  only a place the reference data doesn't have gets a freshly generated
  handle.
- **`<person>`'s children must appear in the DTD's declared order**
  (`gender, name*, eventref*, objref*, attribute*, childof*, parentin*,
  personref*, noteref*, citationref*` — Gramps's DTD is a strict sequence,
  not an unordered bag) — including a person's witness `eventref`s
  (discovered while processing *other* people's events) and `childof`/
  `parentin` (only known once every family has been processed). This is
  why person/family building here is collect-then-emit in two passes
  (`_PersonBuild`/`_FamilyBuild` gather everything first) rather than
  appending elements to the tree as each fact is encountered, the way
  gedcom_writer.py can (GEDCOM's own line-based grammar has no such
  ordering constraint).
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import uuid4

from . import places_reference
from .models import Event, Family, GenealogyDate, Individual, Media, Note, SourceCitation

_GRAMPS_NS = "http://gramps-project.org/xml/1.7.1/"
_DOCTYPE = (
    '<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN" '
    '"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">'
)
_GENEANET_REPOSITORY_HANDLE = "_r1"
_GENEANET_REPOSITORY_ID = "R1"

# DTD-mandated top-level child order of <database>.
_SECTION_ORDER = [
    "header",
    "events",
    "people",
    "families",
    "citations",
    "sources",
    "places",
    "objects",
    "repositories",
    "notes",
]

# GEDCOM-flavored Event.tag -> Gramps's own standard event-type name, for
# the tags common enough that Gramps's standard (non-custom) vocabulary is
# well-established and unambiguous. Anything else (rarer tags, and the
# generic "EVEN" fallback) uses a plain descriptive string instead — Gramps
# accepts any text as a valid "custom" event type, so this is never wrong,
# just less specifically iconified in the Gramps UI than a standard type.
_EVENT_TYPE_MAP = {
    "BIRT": "Birth",
    "BAPM": "Baptism",
    "DEAT": "Death",
    "BURI": "Burial",
    "CREM": "Cremation",
    "ADOP": "Adoption",
    "CONF": "Confirmation",
    "EMIG": "Emigration",
    "IMMI": "Immigration",
    "FCOM": "First Communion",
    "GRAD": "Graduation",
    "NATU": "Naturalization",
    "OCCU": "Occupation",
    "ORDN": "Ordination",
    "RETI": "Retirement",
    "RESI": "Residence",
    "WILL": "Will",
    "CENS": "Census",
    "EDUC": "Education",
    "MARR": "Marriage",
    "DIV": "Divorce",
    "ENGA": "Engagement",
    # Rarer/LDS-specific tags: no standard Gramps type confirmed, so a
    # plain descriptive string (still a perfectly valid custom type).
    "BAPL": "LDS Baptism",
    "BARM": "Bar Mitzvah",
    "BASM": "Bas Mitzvah",
    "CONL": "LDS Confirmation",
    "PROP": "Property",
    "MARB": "Marriage Banns",
    "MARC": "Marriage Contract",
    "MARL": "Marriage License",
}


def _gramps_ymd(d) -> str:
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"


def _render_gramps_date(parent: ET.Element, d: GenealogyDate | None) -> None:
    if d is None:
        return
    if d.fallback_text is not None:
        ET.SubElement(parent, "datestr", val=d.fallback_text)
        return
    if d.range_start and d.range_end:
        ET.SubElement(parent, "daterange", start=_gramps_ymd(d.range_start), stop=_gramps_ymd(d.range_end))
        return
    if d.calendar != "GREGORIAN":
        # No calendar attribute is documented on dateval in the DTD, and
        # guessing Gramps's internal non-Gregorian encoding risks silently
        # mislabeling the date as Gregorian (shifting it ~10-13 days with
        # no indication) — fall back to free text instead for this case.
        ET.SubElement(parent, "datestr", val=f"{_gramps_ymd(d.date)} ({d.calendar.title()} calendar)")
        return
    attrs = {"val": _gramps_ymd(d.date)}
    attr_name = {"EST": "quality", "ABT": "type", "BEF": "type", "AFT": "type"}.get(d.qualifier or "")
    attr_value = {"EST": "estimated", "ABT": "about", "BEF": "before", "AFT": "after"}.get(d.qualifier or "")
    if attr_name and attr_value:
        attrs[attr_name] = attr_value
    ET.SubElement(parent, "dateval", **attrs)


def _tool_version() -> str:
    try:
        return version("exportgeneanet")
    except PackageNotFoundError:
        return "0.0.0"


def _city_name_from_raw(raw_place_text: str) -> str:
    """Same first-segment handling as `places_reference.resolve()` (a
    `"Locality - City"` prefix keeps only the part after the last
    `" - "`) — duplicated here (not imported) since it's two lines and
    only needed for labeling an ad hoc place, not for matching."""
    first_segment = raw_place_text.split(",", 1)[0]
    return first_segment.rsplit(" - ", 1)[-1].strip()


@dataclass
class _PersonBuild:
    """Everything one `<person>` element needs, gathered before any XML is
    emitted — see the module docstring for why this can't just be built
    incrementally like gedcom_writer.py's INDI records can."""

    handle: str
    record_id: str
    individual: Individual
    event_refs: list[tuple[str, str | None]] = field(default_factory=list)  # (event handle, role)
    media_refs: list[str] = field(default_factory=list)
    attributes: list[tuple[str, str]] = field(default_factory=list)  # (type, value)
    childof: str | None = None
    parentin: list[str] = field(default_factory=list)
    personrefs: list[tuple[str, str, str | None]] = field(default_factory=list)  # (target, rel, note handle)
    noterefs: list[str] = field(default_factory=list)
    citationrefs: list[str] = field(default_factory=list)


@dataclass
class _FamilyBuild:
    handle: str
    record_id: str
    family: Family
    event_refs: list[str] = field(default_factory=list)
    childrefs: list[str] = field(default_factory=list)
    noterefs: list[str] = field(default_factory=list)
    citationrefs: list[str] = field(default_factory=list)


class _Registry:
    """Assigns sequential `handle`/`id` pairs and owns every top-level
    collection except `people`/`families` (built separately once — see
    `_PersonBuild`/`_FamilyBuild` above — since they need a second pass).
    """

    def __init__(self, include_notes: bool, include_media: bool) -> None:
        self.include_notes = include_notes
        self.include_media = include_media
        self.sections: dict[str, ET.Element] = {tag: ET.Element(tag) for tag in _SECTION_ORDER}
        self._counters: dict[str, int] = {}
        self.ts = int(time.time())

        self._source_handles: dict[str, str] = {}
        self._citation_handles: dict[tuple[str, str | None], str] = {}
        self._note_handles: dict[int, str] = {}
        self._media_handles: dict[int, str] = {}
        self.geneanet_titles: set[str] = set()
        self.needs_repository = False

        self._place_records: dict[str, dict] = {}
        self._leaf_handle_by_place_text: dict[str, str] = {}
        self._new_place_counter = 0

    def new_handle(self, prefix: str) -> tuple[str, str]:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"_{prefix}{n}", f"{prefix.upper()}{n}"

    def new_record(self, section: str, tag: str, prefix: str) -> ET.Element:
        handle, record_id = self.new_handle(prefix)
        return ET.SubElement(self.sections[section], tag, handle=handle, id=record_id, change=str(self.ts))

    # ------------------------------------------------------------- notes --
    def note_ref(self, note: Note, note_type: str = "General") -> str:
        if id(note) not in self._note_handles:
            note_el = self.new_record("notes", "note", "n")
            note_el.set("type", note_type)
            ET.SubElement(note_el, "text").text = note.text
            self._note_handles[id(note)] = note_el.attrib["handle"]
        return self._note_handles[id(note)]

    # --------------------------------------------------------- citations --
    def citation_ref(self, citation: SourceCitation) -> str:
        key = (citation.title, citation.page)
        if key in self._citation_handles:
            return self._citation_handles[key]

        if citation.title not in self._source_handles:
            source_el = self.new_record("sources", "source", "s")
            self._source_handles[citation.title] = source_el.attrib["handle"]
            ET.SubElement(source_el, "stitle").text = citation.title
            if citation.is_geneanet_source:
                ET.SubElement(source_el, "reporef", hlink=_GENEANET_REPOSITORY_HANDLE)
        if citation.is_geneanet_source:
            self.geneanet_titles.add(citation.title)
            self.needs_repository = True

        citation_el = self.new_record("citations", "citation", "c")
        if citation.page:
            ET.SubElement(citation_el, "page").text = citation.page
        ET.SubElement(citation_el, "confidence").text = "2"  # Normal — nothing more specific is known
        ET.SubElement(citation_el, "sourceref", hlink=self._source_handles[citation.title])
        self._citation_handles[key] = citation_el.attrib["handle"]
        return citation_el.attrib["handle"]

    # -------------------------------------------------------------- media --
    def media_ref(self, media: Media) -> str:
        if id(media) not in self._media_handles:
            object_el = self.new_record("objects", "object", "o")
            src = str(media.local_path) if media.local_path else media.url
            ET.SubElement(object_el, "file", src=src, mime="image/jpeg", description=media.title or src)
            for citation in media.sources:
                ET.SubElement(object_el, "citationref", hlink=self.citation_ref(citation))
            self._media_handles[id(media)] = object_el.attrib["handle"]
        return self._media_handles[id(media)]

    # ------------------------------------------------------------- places --
    def place_ref(self, raw_place_text: str) -> str | None:
        """Resolves (or fabricates) a place chain for `raw_place_text`,
        registering every node it needs along the way, and returns the
        leaf node's handle for the caller's `<place hlink=...>`."""
        if raw_place_text in self._leaf_handle_by_place_text:
            return self._leaf_handle_by_place_text[raw_place_text]

        chain = places_reference.resolve(raw_place_text)
        if chain and chain[-1].type != "Country":
            self._register_place_chain(chain)
            handle = chain[-1].handle
            self._leaf_handle_by_place_text[raw_place_text] = handle
            return handle

        # Either nothing matched, or only the Country did — still need a
        # City-level node for the actual name (parented to the matched
        # Country, when there is one).
        parent_handle = None
        if chain:
            self._register_place_chain(chain)
            parent_handle = chain[0].handle
        _, record_id = self.new_handle("np")
        handle = f"_np{uuid4().hex[:16]}"
        self._place_records[handle] = {
            "id": record_id,
            "type": "City",
            "name": _city_name_from_raw(raw_place_text),
            "code": "",
            "parent": parent_handle,
        }
        self._leaf_handle_by_place_text[raw_place_text] = handle
        return handle

    def _register_place_chain(self, chain: list[places_reference.PlaceNode]) -> None:
        for i, node in enumerate(chain):
            if node.handle not in self._place_records:
                self._place_records[node.handle] = {
                    "id": node.id,
                    "type": node.type,
                    "name": node.name,
                    "code": node.code,
                    "parent": chain[i - 1].handle if i > 0 else None,
                }

    def write_place_records(self) -> None:
        places_section = self.sections["places"]
        for handle, record in self._place_records.items():
            placeobj = ET.SubElement(
                places_section,
                "placeobj",
                handle=handle,
                id=record["id"],
                type=record["type"],
                change=str(self.ts),
            )
            ET.SubElement(placeobj, "pname", value=record["name"])
            if record["code"]:
                ET.SubElement(placeobj, "code").text = record["code"]
            if record["parent"]:
                ET.SubElement(placeobj, "placeref", hlink=record["parent"])

    def write_repository(self) -> None:
        if not self.needs_repository:
            return
        repo_el = ET.SubElement(
            self.sections["repositories"],
            "repository",
            handle=_GENEANET_REPOSITORY_HANDLE,
            id=_GENEANET_REPOSITORY_ID,
            change=str(self.ts),
        )
        ET.SubElement(repo_el, "rname").text = "Geneanet"
        ET.SubElement(repo_el, "type").text = "Website"


def _write_event_record(registry: _Registry, event: Event) -> str:
    """Creates the top-level `<event>` record and returns its handle —
    does not attach any `<eventref>` (the caller decides where those go:
    the participant's own person/family, and every in-export witness's
    person record — see `_collect` below)."""
    event_el = registry.new_record("events", "event", "e")
    ET.SubElement(event_el, "type").text = _EVENT_TYPE_MAP.get(event.tag, event.type or event.tag)
    _render_gramps_date(event_el, event.date)
    if event.place:
        leaf_handle = registry.place_ref(event.place.name)
        if leaf_handle:
            ET.SubElement(event_el, "place", hlink=leaf_handle)
    if event.note and registry.include_notes:
        ET.SubElement(event_el, "noteref", hlink=registry.note_ref(event.note, note_type="Event Note"))
    for citation in event.sources:
        ET.SubElement(event_el, "citationref", hlink=registry.citation_ref(citation))
    return event_el.attrib["handle"]


def _collect(
    registry: _Registry, individuals: dict[str, Individual], families: dict[str, Family]
) -> tuple[dict[str, _PersonBuild], dict[str, _FamilyBuild]]:
    people: dict[str, _PersonBuild] = {}
    person_handles: dict[str, str] = {}
    for key, individual in individuals.items():
        handle, record_id = registry.new_handle("p")
        # Registered via new_handle (not new_record: the <person> element
        # itself is only built once every cross-reference below is known).
        person_handles[key] = handle
        people[key] = _PersonBuild(handle=handle, record_id=record_id, individual=individual)

    for build in people.values():
        individual = build.individual
        for event in individual.events:
            event_handle = _write_event_record(registry, event)
            build.event_refs.append((event_handle, None))
            for witness in event.witnesses:
                witness_key = str(witness.person)
                witness_build = people.get(witness_key)
                if witness_build is not None:
                    witness_build.event_refs.append((event_handle, witness.role))

        if individual.occupation:
            build.attributes.append(("Occupation", individual.occupation))
        for title in individual.titles:
            build.attributes.append(("Title", title))

        for assoc in individual.associations:
            target_handle = person_handles.get(str(assoc.person))
            if target_handle is None:
                continue
            note_handle = None
            if assoc.note and registry.include_notes:
                note_handle = registry.note_ref(Note(assoc.note), note_type="Association Note")
            build.personrefs.append((target_handle, assoc.role or "Unknown", note_handle))

        if registry.include_notes:
            build.noterefs = [registry.note_ref(note) for note in individual.notes]
        build.citationrefs = [registry.citation_ref(c) for c in individual.sources]
        if registry.include_media:
            build.media_refs = [registry.media_ref(m) for m in individual.media]

    families_build: dict[str, _FamilyBuild] = {}
    family_handles: dict[str, str] = {}
    for fam_key, family in families.items():
        handle, record_id = registry.new_handle("f")
        family_handles[fam_key] = handle
        families_build[fam_key] = _FamilyBuild(handle=handle, record_id=record_id, family=family)

    for fbuild in families_build.values():
        family = fbuild.family
        for event in (family.marriage, family.divorce):
            if event is None:
                continue
            event_handle = _write_event_record(registry, event)
            fbuild.event_refs.append(event_handle)
            for witness in event.witnesses:
                witness_build = people.get(str(witness.person))
                if witness_build is not None:
                    witness_build.event_refs.append((event_handle, witness.role))

        for child in family.children:
            child_handle = person_handles.get(str(child))
            if child_handle is None:
                continue
            fbuild.childrefs.append(child_handle)
            child_build = people.get(str(child))
            if child_build is not None:
                child_build.childof = fbuild.handle

        if registry.include_notes:
            fbuild.noterefs = [registry.note_ref(note) for note in family.notes]
        fbuild.citationrefs = [registry.citation_ref(c) for c in family.sources]

        for parent_key in (family.husband, family.wife):
            parent_build = people.get(str(parent_key)) if parent_key else None
            if parent_build is not None:
                parent_build.parentin.append(fbuild.handle)

    return people, families_build


def _write_person(registry: _Registry, build: _PersonBuild) -> None:
    individual = build.individual
    person_el = ET.SubElement(
        registry.sections["people"],
        "person",
        handle=build.handle,
        id=build.record_id,
        change=str(registry.ts),
    )
    ET.SubElement(person_el, "gender").text = individual.sex

    name_el = ET.SubElement(person_el, "name")
    ET.SubElement(name_el, "first").text = individual.given_name
    ET.SubElement(name_el, "surname").text = individual.surname
    if individual.nickname:
        ET.SubElement(name_el, "nick").text = individual.nickname
    for alt in individual.names:
        alt_name_el = ET.SubElement(person_el, "name", alt="1")
        ET.SubElement(alt_name_el, "first").text = alt.given
        if alt.surname is not None:
            ET.SubElement(alt_name_el, "surname").text = alt.surname

    for event_handle, role in build.event_refs:
        eventref_el = ET.SubElement(person_el, "eventref", hlink=event_handle)
        if role:
            eventref_el.set("role", role)

    for media_handle in build.media_refs:
        ET.SubElement(person_el, "objref", hlink=media_handle)

    for attr_type, attr_value in build.attributes:
        ET.SubElement(person_el, "attribute", type=attr_type, value=attr_value)

    if build.childof:
        ET.SubElement(person_el, "childof", hlink=build.childof)
    for family_handle in build.parentin:
        ET.SubElement(person_el, "parentin", hlink=family_handle)

    for target_handle, rel, note_handle in build.personrefs:
        personref_el = ET.SubElement(person_el, "personref", hlink=target_handle, rel=rel)
        if note_handle:
            ET.SubElement(personref_el, "noteref", hlink=note_handle)

    for note_handle in build.noterefs:
        ET.SubElement(person_el, "noteref", hlink=note_handle)
    for citation_handle in build.citationrefs:
        ET.SubElement(person_el, "citationref", hlink=citation_handle)


def _write_family(registry: _Registry, build: _FamilyBuild, person_handles: dict[str, str]) -> None:
    family = build.family
    family_el = ET.SubElement(
        registry.sections["families"],
        "family",
        handle=build.handle,
        id=build.record_id,
        change=str(registry.ts),
    )
    ET.SubElement(family_el, "rel", type="Married" if family.marriage else "Unknown")
    if family.husband and str(family.husband) in person_handles:
        ET.SubElement(family_el, "father", hlink=person_handles[str(family.husband)])
    if family.wife and str(family.wife) in person_handles:
        ET.SubElement(family_el, "mother", hlink=person_handles[str(family.wife)])

    for event_handle in build.event_refs:
        ET.SubElement(family_el, "eventref", hlink=event_handle)
    for child_handle in build.childrefs:
        ET.SubElement(family_el, "childref", hlink=child_handle)
    for note_handle in build.noterefs:
        ET.SubElement(family_el, "noteref", hlink=note_handle)
    for citation_handle in build.citationrefs:
        ET.SubElement(family_el, "citationref", hlink=citation_handle)


def generate_gramps_xml(
    individuals: dict[str, Individual],
    families: dict[str, Family],
    include_notes: bool = True,
    include_media: bool = True,
) -> str:
    registry = _Registry(include_notes=include_notes, include_media=include_media)

    people, families_build = _collect(registry, individuals, families)
    person_handles = {key: build.handle for key, build in people.items()}

    for build in people.values():
        _write_person(registry, build)
    for build in families_build.values():
        _write_family(registry, build, person_handles)

    registry.write_place_records()
    registry.write_repository()

    header = registry.sections["header"]
    ET.SubElement(header, "created", date=time.strftime("%Y-%m-%d"), version=_tool_version())
    researcher = ET.SubElement(header, "researcher")
    ET.SubElement(researcher, "resname").text = "ExportGeneanet"

    root = ET.Element("database", xmlns=_GRAMPS_NS)
    for tag in _SECTION_ORDER:
        section = registry.sections[tag]
        if len(section) or tag == "header":
            root.append(section)

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n\n{_DOCTYPE}\n\n{body}\n'


def write_gramps_file(
    path: Path,
    individuals: dict[str, Individual],
    families: dict[str, Family],
    include_notes: bool = True,
    include_media: bool = True,
) -> None:
    content = generate_gramps_xml(
        individuals, families, include_notes=include_notes, include_media=include_media
    )
    path.write_text(content, encoding="utf-8")
