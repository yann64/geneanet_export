"""Translate Geneanet protobuf API responses into `models.py` dataclasses.

Works on plain dicts from `google.protobuf.json_format.MessageToDict(...,
preserving_proto_field_name=True)` rather than protobuf message objects
directly, matching the reference Gramps addon's approach and keeping this
module free of protobuf-specific code.

Privacy: Geneanet's API includes `name_is_hidden` / `name_is_restricted` /
`visible_for_visitors` flags on every person reference it returns (this is
how the site's own frontend decides whether to render a name, e.g. the
"Cette personne est masquée" placeholder for hidden individuals). This
module treats those flags as authoritative and drops any reference that
isn't publicly visible — the crawler must never follow or record a
non-public person, even if the API technically included their raw index in
a response.
"""

from __future__ import annotations

import html
import re

from .identifiers import PersonKey
from .models import Event, Family, Individual, Media, Note, Place, Witness

_SEX_MAP = {"MALE": "M", "FEMALE": "F", "UNKNOWN": "U"}

# Geneanet's EPERS_*/EFAM_* event-name enum -> GEDCOM 5.5.1 tag. Adapted from
# the reference Gramps addon's gn_constants.py, which maps the same enum to
# Gramps' EventType instead. Anything not listed here becomes a generic
# GEDCOM `EVEN` with the Geneanet event name kept as its `TYPE`.
EVENT_TAG_MAP = {
    "EPERS_BIRTH": "BIRT",
    "EPERS_BAPTISM": "BAPM",
    "EPERS_DEATH": "DEAT",
    "EPERS_BURIAL": "BURI",
    "EPERS_CREMATION": "CREM",
    "EPERS_ADOPTION": "ADOP",
    "EPERS_BAPTISMLDS": "BAPL",
    "EPERS_BARMITZVAH": "BARM",
    "EPERS_BATMITZVAH": "BASM",
    "EPERS_CONFIRMATION": "CONF",
    "EPERS_CONFIRMATIONLDS": "CONL",
    "EPERS_EMIGRATION": "EMIG",
    "EPERS_IMMIGRATION": "IMMI",
    "EPERS_FIRSTCOMMUNION": "FCOM",
    "EPERS_GRADUATE": "GRAD",
    "EPERS_NATURALISATION": "NATU",
    "EPERS_OCCUPATION": "OCCU",
    "EPERS_ORDINATION": "ORDN",
    "EPERS_RETIRED": "RETI",
    "EPERS_RESIDENCE": "RESI",
    "EPERS_WILL": "WILL",
    "EPERS_RECENSEMENT": "CENS",
    "EPERS_PROPERTY": "PROP",
    "EPERS_EDUCATION": "EDUC",
    "EPERS_ELECTION": "EVEN",
}

# Geneanet's MarriageType enum -> GEDCOM tag. Only MARRIED-like values map to
# a specific tag; anything else falls back to a generic EVEN with a TYPE
# label derived from the enum name (`_label_from_enum`), same philosophy as
# EVENT_TAG_MAP above. Confirmed against real data that NO_MENTION is common
# in practice (usually with no date at all, so no event gets emitted then).
MARRIAGE_TYPE_TAG_MAP = {
    "MARRIED": "MARR",
    "NO_SEXES_CHECK_MARRIED": "MARR",
    "ENGAGED": "ENGA",
    "MARRIAGE_BANN": "MARB",
    "MARRIAGE_CONTRACT": "MARC",
    "MARRIAGE_LICENSE": "MARL",
    "RESIDENCE": "RESI",
}

# Geneanet's DivorceType enum -> GEDCOM tag. NOT_DIVORCED means "no divorce
# event" (handled by the caller, not this map). GEDCOM 5.5.1 has no dedicated
# "separated" tag, so that falls back to EVEN+TYPE.
DIVORCE_TYPE_TAG_MAP = {"DIVORCED": "DIV"}

# Geneanet's WitnessType enum -> a human-readable GEDCOM ASSO/RELA role.
WITNESS_TYPE_LABEL = {
    "WITNESS": "Witness",
    "WITNESS_GODPARENT": "Godparent",
    "WITNESS_CIVILOFFICER": "Civil officer",
    "WITNESS_RELIGIOUSOFFICER": "Religious officer",
    "WITNESS_INFORMANT": "Informant",
    "WITNESS_ATTENDING": "Attending",
    "WITNESS_MENTIONED": "Mentioned",
    "WITNESS_OTHER": "Witness",
}


def _label_from_enum(value: str) -> str:
    """"NO_SEXES_CHECK_NOT_MARRIED" -> "No sexes check not married"."""
    return value.replace("_", " ").capitalize()


# GeneWeb's raw date encoding, e.g. "?/1946/0/0#" (possibly 1946),
# "~/1668/0/0#" (about 1668), "</1891/0/0#" (before 1891),
# ">/1823/0/0#" (after 1823), "/1882/1/23#" (23 Jan 1882, sure). The
# trailing "#" is a fixed terminator (present regardless of calendar, not a
# Gregorian marker) — the actual calendar comes from the separate `date_cal`
# field. Confirmed against ~180 real date_raw values from yann64's tree.
_DATE_PART_RE = re.compile(r"^(?P<prefix>[?~<>]?)/?(?P<year>-?\d+)/(?P<month>\d+)/(?P<day>\d+)#?$")

# GeneWeb precision prefix -> closest GEDCOM 5.5.1 date qualifier. "?"
# (Geneanet's "possibly") maps to EST (estimated) rather than a made-up
# "maybe" qualifier GEDCOM doesn't have.
_PRECISION_TO_QUALIFIER = {"?": "EST", "~": "ABT", "<": "BEF", ">": "AFT"}

_MONTH_ABBR = [
    None, "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]

# GEDCOM calendar escapes for calendars where date_raw's Y/M/D numbers are
# straightforward (Gregorian needs no escape; Julian uses the same D/M/Y
# numbering). FRENCH/HEBREW raw values were NOT confirmed to use plain D/M/Y
# numbering (a real French-Republican example's numbers didn't match its own
# displayed date) — rather than risk silently emitting a wrong date, those
# fall back to Geneanet's localized display text instead of being parsed.
_CALENDAR_ESCAPE = {"JULIAN": "@#DJULIAN@"}
_PARSEABLE_RAW_CALENDARS = {"GREGORIAN", "JULIAN", None}


def _format_dmy(year: str, month: int, day: int) -> str:
    parts = []
    if month and day:
        parts.append(str(day))
    if month:
        parts.append(_MONTH_ABBR[month])
    parts.append(year)
    return " ".join(parts)


def _parse_date_part(raw: str) -> str | None:
    m = _DATE_PART_RE.match(raw)
    if not m:
        return None
    dmy = _format_dmy(m["year"], int(m["month"]), int(m["day"]))
    qualifier = _PRECISION_TO_QUALIFIER.get(m["prefix"])
    return f"{qualifier} {dmy}" if qualifier else dmy


def gedcom_date(raw: str | None, calendar: str | None, fallback_text: str | None) -> str | None:
    """Convert a GeneWeb `*_date_raw` value into a GEDCOM 5.5.1 DATE value
    (`DD MON YYYY`, with ABT/EST/BEF/AFT/BET...AND qualifiers as needed).
    Falls back to Geneanet's own localized display text — not GEDCOM-valid,
    but better than losing the information — when `raw` is absent or in a
    form this parser doesn't recognize (e.g. an unparsed calendar, or the
    rare non-D/M/Y interval encodings GeneWeb occasionally emits)."""
    if not raw or calendar not in _PARSEABLE_RAW_CALENDARS:
        return _text(fallback_text)

    if "#.." in raw:
        left_raw, right_raw = raw.split("#..", 1)
        left = _parse_date_part(left_raw)
        right = _parse_date_part(right_raw)
        if left and right:
            return f"BET {left} AND {right}"
        return _text(fallback_text)

    date_str = _parse_date_part(raw)
    if date_str is None:
        return _text(fallback_text)
    escape = _CALENDAR_ESCAPE.get(calendar or "GREGORIAN")
    return f"{escape} {date_str}" if escape else date_str


def _html_to_text(text: str) -> str:
    """Geneanet notes are simple HTML (`<p>`, `<br>`, entities); flatten to
    plain text for a GEDCOM NOTE rather than pulling in an HTML parser
    dependency for this one bounded case."""
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _text(value: str | None) -> str | None:
    """Plain (non-HTML) fields like names/dates/places still come back with
    HTML entities escaped (e.g. "Prud&#39;Homie") — unescape those too."""
    return html.unescape(value) if value else value


def is_publicly_visible(person_ref: dict) -> bool:
    """True unless Geneanet's own flags say this person shouldn't be shown."""
    if person_ref.get("nameIsHidden") or person_ref.get("nameIsRestricted"):
        return False
    if person_ref.get("name_is_hidden") or person_ref.get("name_is_restricted"):
        return False
    visibility = person_ref.get("visible_for_visitors") or person_ref.get("visibleForVisitors")
    if visibility is not None and visibility != "VISIBILITY_PUBLIC":
        return False
    return True


def person_key_from_summary(d: dict) -> PersonKey:
    """`SimplePerson`/`Person`/`PersonTree`-shaped dicts use field `occ`."""
    return PersonKey(p=d["p"], n=d["n"], oc=int(d.get("occ", 0)))


def person_ref_from_summary(d: dict) -> tuple[PersonKey, int]:
    """Same as `person_key_from_summary`, plus the numeric `index` needed for
    a follow-up `GeneanetApiClient.get_person` call."""
    return person_key_from_summary(d), int(d["index"])


def _place(name: str | None) -> Place | None:
    return Place(_text(name)) if name else None


def _witnesses_from(raw_witnesses: list[dict]) -> list[Witness]:
    """`WitnessEvent`-shaped dicts (personal event or family `witnesses`
    list) -> `Witness` models. Same privacy rule as everywhere else: a
    witness who isn't publicly visible is dropped, not just unlinked."""
    witnesses = []
    for w in raw_witnesses:
        person = w.get("witness")
        if not person or not is_publicly_visible(person):
            continue
        witnesses.append(
            Witness(
                person=person_key_from_summary(person),
                role=WITNESS_TYPE_LABEL.get(w.get("witness_type")),
                note=_text(w.get("witness_note")) or None,
            )
        )
    return witnesses


def individual_from_person(
    person: dict,
) -> tuple[Individual, list[Family], set[tuple[PersonKey, int]]]:
    """Map a full `Person` (from `GeneanetApiClient.get_person`) into an
    Individual, the Family records where they're a spouse, and every other
    publicly-visible (PersonKey, index) referenced (parents, spouses,
    children) — worth the crawler visiting next."""
    key = person_key_from_summary(person)
    individual = Individual(
        key=key,
        given_name=_text(person.get("firstname", "")),
        surname=_text(person.get("lastname", "")),
        sex=_SEX_MAP.get(person.get("sex", "UNKNOWN"), "U"),
        occupation=_text(person.get("occupation")),
    )
    if person.get("image"):
        individual.media.append(Media(url=person["image"]))

    for element in person.get("events", {}).get("elements", []):
        event_type = element.get("type")
        if event_type is None or event_type.startswith("EFAM_"):
            continue  # family events are attached to the Family record instead
        gedcom_tag = EVENT_TAG_MAP.get(event_type, "EVEN")

        # "reason" isn't confirmed against any real data in this project (never
        # observed populated) and its exact semantics are unclear, so rather
        # than guess a GEDCOM tag (e.g. CAUS) that might be wrong, fold it
        # into the note as labeled free text — preserves the information
        # without asserting an unconfirmed meaning.
        note_parts = []
        if element.get("note"):
            note_parts.append(_html_to_text(element["note"]))
        if element.get("reason"):
            note_parts.append(f"Reason: {_html_to_text(element['reason'])}")

        individual.events.append(
            Event(
                tag=gedcom_tag,
                date=gedcom_date(element.get("date_raw"), element.get("date_cal"), element.get("date")),
                place=_place(element.get("place")),
                note=Note("\n".join(note_parts)) if note_parts else None,
                # Only the generic fallback tag needs a TYPE to say what it
                # actually is; BIRT/DEAT/etc already say that via the tag.
                type=_text(element.get("name")) if gedcom_tag == "EVEN" else None,
                source=_html_to_text(element["src"]) if element.get("src") else None,
                witnesses=_witnesses_from(element.get("witnesses", [])),
            )
        )

    if person.get("notes"):
        individual.notes.append(Note(_html_to_text(person["notes"])))

    if person.get("psources"):
        individual.sources.append(_html_to_text(person["psources"]))

    related: set[tuple[PersonKey, int]] = set()

    father = person.get("father")
    if father and is_publicly_visible(father):
        individual.father = person_key_from_summary(father)
        related.add(person_ref_from_summary(father))

    mother = person.get("mother")
    if mother and is_publicly_visible(mother):
        individual.mother = person_key_from_summary(mother)
        related.add(person_ref_from_summary(mother))

    families: list[Family] = []
    for fam in person.get("families", []):
        spouse = fam.get("spouse")
        spouse_key = None
        if spouse and is_publicly_visible(spouse):
            spouse_key = person_key_from_summary(spouse)
            related.add(person_ref_from_summary(spouse))

        if individual.sex == "F":
            husband, wife = spouse_key, key
        else:
            husband, wife = key, spouse_key

        children = []
        for child in fam.get("children", []):
            if is_publicly_visible(child):
                child_key = person_key_from_summary(child)
                children.append(child_key)
                related.add(person_ref_from_summary(child))

        marriage = None
        if fam.get("marriage_date") or fam.get("marriage_place"):
            marriage_type = fam.get("marriage_type", "MARRIED")
            marriage_tag = MARRIAGE_TYPE_TAG_MAP.get(marriage_type, "EVEN")
            marriage = Event(
                tag=marriage_tag,
                date=gedcom_date(
                    fam.get("marriage_date_raw"), fam.get("marriage_date_cal"), fam.get("marriage_date")
                ),
                place=_place(fam.get("marriage_place")),
                type=_label_from_enum(marriage_type) if marriage_tag == "EVEN" else None,
                source=_html_to_text(fam["marriage_src"]) if fam.get("marriage_src") else None,
                witnesses=_witnesses_from(fam.get("witnesses", [])),
            )

        divorce = None
        divorce_type = fam.get("divorce_type", "NOT_DIVORCED")
        if divorce_type != "NOT_DIVORCED" and (fam.get("divorce_date") or fam.get("divorce_date_raw")):
            divorce_tag = DIVORCE_TYPE_TAG_MAP.get(divorce_type, "EVEN")
            divorce = Event(
                tag=divorce_tag,
                date=gedcom_date(
                    fam.get("divorce_date_raw"), fam.get("divorce_date_cal"), fam.get("divorce_date")
                ),
                type=_label_from_enum(divorce_type) if divorce_tag == "EVEN" else None,
            )

        fam_key = f"{husband or 'UNK'}__{wife or 'UNK'}"
        families.append(
            Family(
                key=fam_key,
                husband=husband,
                wife=wife,
                children=children,
                marriage=marriage,
                divorce=divorce,
                notes=[Note(_html_to_text(fam["notes"]))] if fam.get("notes") else [],
                sources=[_html_to_text(fam["fsources"])] if fam.get("fsources") else [],
            )
        )
        individual.family_keys.append(fam_key)

    return individual, families, related


def person_ref_from_graph_node(node_person: dict) -> tuple[PersonKey, int] | None:
    """A `PersonTree`-shaped node from a `graph_v2` response, used only to
    discover who's in a lineage (see `tree_crawler.py`) — full details are
    then fetched per-person via `get_person`."""
    if not is_publicly_visible(node_person):
        return None
    return person_ref_from_summary(node_person)
