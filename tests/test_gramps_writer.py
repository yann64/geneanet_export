import xml.etree.ElementTree as ET
from pathlib import Path

from exportgeneanet.gramps_writer import generate_gramps_xml
from exportgeneanet.identifiers import PersonKey
from exportgeneanet.models import (
    Event,
    Family,
    GenealogyDate,
    Individual,
    Media,
    Note,
    PartialDate,
    Place,
    SourceCitation,
    Witness,
)

_NS = {"g": "http://gramps-project.org/xml/1.7.1/"}


def _parse(xml_text: str) -> ET.Element:
    return ET.fromstring(xml_text)


def _find(root: ET.Element, path: str) -> ET.Element | None:
    return root.find(path, _NS)


def _findall(root: ET.Element, path: str) -> list[ET.Element]:
    return root.findall(path, _NS)


def _sample_data():
    father_key = PersonKey(p="pierre", n="dupont", oc=0)
    mother_key = PersonKey(p="marie", n="martin", oc=0)
    child_key = PersonKey(p="jean", n="dupont", oc=0)

    father = Individual(key=father_key, given_name="Pierre", surname="Dupont", sex="M")
    mother = Individual(key=mother_key, given_name="Marie", surname="Martin", sex="F")
    child = Individual(
        key=child_key,
        given_name="Jean",
        surname="Dupont",
        sex="M",
        father=father_key,
        mother=mother_key,
        events=[
            Event(
                tag="BIRT",
                date=GenealogyDate(date=PartialDate(year=1950, month=1, day=1)),
                place=Place("Paris"),
            )
        ],
        notes=[Note("A note about Jean.")],
    )
    family = Family(
        key=f"{father_key}__{mother_key}",
        husband=father_key,
        wife=mother_key,
        children=[child_key],
        marriage=Event(tag="MARR", date=GenealogyDate(fallback_text="1945")),
    )
    individuals = {str(k): v for k, v in [(father_key, father), (mother_key, mother), (child_key, child)]}
    families = {family.key: family}
    return individuals, families


def test_generate_gramps_xml_has_doctype_and_root():
    individuals, families = _sample_data()
    xml_text = generate_gramps_xml(individuals, families)
    assert xml_text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<!DOCTYPE database PUBLIC" in xml_text
    root = _parse(xml_text)
    assert root.tag == f"{{{_NS['g']}}}database"


def test_generate_gramps_xml_person_and_family_structure():
    individuals, families = _sample_data()
    root = _parse(generate_gramps_xml(individuals, families))

    people = _findall(root, "g:people/g:person")
    assert len(people) == 3
    jean = next(p for p in people if _find(p, "g:name/g:first").text == "Jean")
    assert _find(jean, "g:gender").text == "M"
    assert _find(jean, "g:name/g:surname").text == "Dupont"

    families_el = _findall(root, "g:families/g:family")
    assert len(families_el) == 1
    assert _find(families_el[0], "g:rel").attrib["type"] == "Married"
    assert _find(families_el[0], "g:father") is not None
    assert _find(families_el[0], "g:mother") is not None
    assert len(_findall(families_el[0], "g:childref")) == 1

    # The child's own <childof> hlink points at the family's handle.
    assert _find(jean, "g:childof").attrib["hlink"] == families_el[0].attrib["handle"]


def test_generate_gramps_xml_event_is_a_standalone_record_referenced_by_eventref():
    individuals, families = _sample_data()
    root = _parse(generate_gramps_xml(individuals, families))

    events = _findall(root, "g:events/g:event")
    birth = next(e for e in events if _find(e, "g:type").text == "Birth")
    assert _find(birth, "g:dateval").attrib["val"] == "1950-01-01"
    assert _find(birth, "g:place") is not None

    jean = next(p for p in _findall(root, "g:people/g:person") if _find(p, "g:name/g:first").text == "Jean")
    eventrefs = _findall(jean, "g:eventref")
    assert any(ref.attrib["hlink"] == birth.attrib["handle"] for ref in eventrefs)
    # The person's own event has no role (Gramps's default = Primary).
    assert all("role" not in ref.attrib for ref in eventrefs)


def test_generate_gramps_xml_marriage_event_on_family_not_person():
    individuals, families = _sample_data()
    root = _parse(generate_gramps_xml(individuals, families))
    family = _find(root, "g:families/g:family")
    marriage = next(e for e in _findall(root, "g:events/g:event") if _find(e, "g:type").text == "Marriage")
    assert marriage.attrib["handle"] in [r.attrib["hlink"] for r in _findall(family, "g:eventref")]


def test_generate_gramps_xml_date_qualifiers():
    key = PersonKey(p="jean", n="dupont", oc=0)

    def event_for(date):
        individual = Individual(
            key=key, given_name="Jean", surname="Dupont", events=[Event(tag="BIRT", date=date)]
        )
        root = _parse(generate_gramps_xml({str(key): individual}, {}))
        return _find(root, "g:events/g:event")

    about = event_for(GenealogyDate(qualifier="ABT", date=PartialDate(year=1668)))
    assert _find(about, "g:dateval").attrib == {"val": "1668-00-00", "type": "about"}

    estimated = event_for(GenealogyDate(qualifier="EST", date=PartialDate(year=1946)))
    assert _find(estimated, "g:dateval").attrib == {"val": "1946-00-00", "quality": "estimated"}

    before = event_for(GenealogyDate(qualifier="BEF", date=PartialDate(year=1891)))
    assert _find(before, "g:dateval").attrib["type"] == "before"

    ranged = event_for(GenealogyDate(range_start=PartialDate(year=1652), range_end=PartialDate(year=1654)))
    daterange = _find(ranged, "g:daterange")
    assert daterange.attrib == {"start": "1652-00-00", "stop": "1654-00-00"}

    julian = event_for(GenealogyDate(date=PartialDate(year=1700, month=3, day=1), calendar="JULIAN"))
    assert "Julian" in _find(julian, "g:datestr").attrib["val"]


def test_generate_gramps_xml_resolves_real_reference_place():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[Event(tag="BIRT", place=Place("Sérignan, Hérault, Occitanie, France"))],
    )
    root = _parse(generate_gramps_xml({str(key): individual}, {}))
    placeobjs = _findall(root, "g:places/g:placeobj")
    names = {p.attrib["type"]: _find(p, "g:pname").attrib["value"] for p in placeobjs}
    assert names == {"City": "Sérignan", "Department": "Hérault", "Region": "Occitanie", "Country": "France"}
    # The real reference file's own id for Sérignan (see test_places_reference.py).
    city = next(p for p in placeobjs if p.attrib["type"] == "City")
    assert city.attrib["id"] == "P24214"


def test_generate_gramps_xml_unmatched_place_gets_fresh_ad_hoc_node():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[Event(tag="BIRT", place=Place("Nowhereville, Nonexistentia"))],
    )
    root = _parse(generate_gramps_xml({str(key): individual}, {}))
    placeobjs = _findall(root, "g:places/g:placeobj")
    assert len(placeobjs) == 1
    assert _find(placeobjs[0], "g:pname").attrib["value"] == "Nowhereville"
    assert _find(placeobjs[0], "g:placeref") is None


def test_generate_gramps_xml_witness_gets_eventref_on_own_person_not_on_event():
    key = PersonKey(p="jean", n="dupont", oc=0)
    witness_key = PersonKey(p="marie", n="martin", oc=0)
    witness = Individual(key=witness_key, given_name="Marie", surname="Martin")
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[Event(tag="MARR", witnesses=[Witness(person=witness_key, role="Witness")])],
    )
    root = _parse(generate_gramps_xml({str(key): individual, str(witness_key): witness}, {}))
    event = _find(root, "g:events/g:event")
    # Gramps has no witness field on <event> at all.
    assert _find(event, "g:eventref") is None

    witness_el = next(
        p for p in _findall(root, "g:people/g:person") if _find(p, "g:name/g:first").text == "Marie"
    )
    eventref = _find(witness_el, "g:eventref")
    assert eventref.attrib["hlink"] == event.attrib["handle"]
    assert eventref.attrib["role"] == "Witness"


def test_generate_gramps_xml_witness_not_in_export_is_skipped():
    key = PersonKey(p="jean", n="dupont", oc=0)
    ghost_key = PersonKey(p="ghost", n="nobody", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[Event(tag="MARR", witnesses=[Witness(person=ghost_key, role="Witness")])],
    )
    root = _parse(generate_gramps_xml({str(key): individual}, {}))
    assert len(_findall(root, "g:people/g:person")) == 1


def test_generate_gramps_xml_association_becomes_personref():
    key = PersonKey(p="jean", n="dupont", oc=0)
    godparent_key = PersonKey(p="marie", n="martin", oc=0)
    godparent = Individual(key=godparent_key, given_name="Marie", surname="Martin")
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        associations=[Witness(person=godparent_key, role="Godparent")],
    )
    root = _parse(generate_gramps_xml({str(key): individual, str(godparent_key): godparent}, {}))
    jean = next(p for p in _findall(root, "g:people/g:person") if _find(p, "g:name/g:first").text == "Jean")
    personref = _find(jean, "g:personref")
    assert personref.attrib["rel"] == "Godparent"
    marie = next(p for p in _findall(root, "g:people/g:person") if _find(p, "g:name/g:first").text == "Marie")
    assert personref.attrib["hlink"] == marie.attrib["handle"]


def test_generate_gramps_xml_dedupes_citations_and_links_repository():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[
            Event(
                tag="BIRT",
                sources=[SourceCitation(title="Geneanet — tree", page="url1", is_geneanet_source=True)],
            ),
            Event(
                tag="DEAT",
                sources=[SourceCitation(title="Geneanet — tree", page="url2", is_geneanet_source=True)],
            ),
        ],
    )
    root = _parse(generate_gramps_xml({str(key): individual}, {}))
    sources = _findall(root, "g:sources/g:source")
    assert len(sources) == 1
    citations = _findall(root, "g:citations/g:citation")
    assert len(citations) == 2  # different pages -> different citations, same source
    repo = _find(root, "g:repositories/g:repository")
    assert _find(repo, "g:rname").text == "Geneanet"
    assert _find(sources[0], "g:reporef").attrib["hlink"] == repo.attrib["handle"]


def test_generate_gramps_xml_no_repository_when_no_geneanet_source():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        sources=[SourceCitation(title="Some archival citation")],
    )
    root = _parse(generate_gramps_xml({str(key): individual}, {}))
    assert _find(root, "g:repositories") is None


def test_generate_gramps_xml_excludes_notes_and_media_when_disabled():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        notes=[Note("secret note")],
        media=[Media(url="https://example.com/photo.jpg")],
    )
    root = _parse(generate_gramps_xml({str(key): individual}, {}, include_notes=False, include_media=False))
    assert _find(root, "g:notes") is None
    assert _find(root, "g:objects") is None
    jean = _find(root, "g:people/g:person")
    assert _find(jean, "g:noteref") is None
    assert _find(jean, "g:objref") is None


def test_generate_gramps_xml_media_uses_local_path_when_downloaded():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        media=[Media(url="https://example.com/photo.jpg", local_path=Path("photos/p1.jpg"))],
    )
    root = _parse(generate_gramps_xml({str(key): individual}, {}))
    media_obj = _find(root, "g:objects/g:object")
    assert _find(media_obj, "g:file").attrib["src"] == "photos/p1.jpg"


def test_generate_gramps_xml_divorce_event():
    key1 = PersonKey(p="jean", n="dupont", oc=0)
    key2 = PersonKey(p="marie", n="martin", oc=0)
    family = Family(
        key="fam1",
        husband=key1,
        wife=key2,
        divorce=Event(tag="DIV", date=GenealogyDate(fallback_text="1960")),
    )
    root = _parse(generate_gramps_xml({}, {"fam1": family}))
    divorce = next(e for e in _findall(root, "g:events/g:event") if _find(e, "g:type").text == "Divorce")
    assert _find(divorce, "g:datestr").attrib["val"] == "1960"
