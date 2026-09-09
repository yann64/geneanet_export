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
from .models import Event, Family, Individual, Media, Note, Place

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
        individual.events.append(
            Event(
                tag=EVENT_TAG_MAP.get(event_type, "EVEN"),
                date=_text(element.get("date")),
                place=_place(element.get("place")),
                note=Note(_html_to_text(element["note"])) if element.get("note") else None,
            )
        )

    if person.get("notes"):
        individual.notes.append(Note(_html_to_text(person["notes"])))

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
            marriage = Event(
                tag="MARR",
                date=_text(fam.get("marriage_date")),
                place=_place(fam.get("marriage_place")),
            )

        fam_key = f"{husband or 'UNK'}__{wife or 'UNK'}"
        families.append(
            Family(key=fam_key, husband=husband, wife=wife, children=children, marriage=marriage)
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
