from exportgeneanet.identifiers import PersonKey
from exportgeneanet.mapping import (
    gedcom_date,
    individual_from_person,
    is_publicly_visible,
    person_ref_from_graph_node,
)


def _simple_person(**overrides):
    base = {
        "index": 1,
        "sex": "MALE",
        "lastname": "Dupont",
        "firstname": "Jean",
        "n": "dupont",
        "p": "jean",
        "occ": 0,
        "name_is_hidden": False,
        "name_is_restricted": False,
        "visible_for_visitors": "VISIBILITY_PUBLIC",
    }
    base.update(overrides)
    return base


def test_is_publicly_visible_true_for_normal_person():
    assert is_publicly_visible(_simple_person())


def test_is_publicly_visible_false_when_hidden():
    assert not is_publicly_visible(_simple_person(name_is_hidden=True))


def test_is_publicly_visible_false_when_restricted():
    assert not is_publicly_visible(_simple_person(name_is_restricted=True))


def test_is_publicly_visible_false_when_not_public_visibility():
    assert not is_publicly_visible(_simple_person(visible_for_visitors="VISIBILITY_PRIVATE"))


def test_person_ref_from_graph_node_skips_hidden():
    assert person_ref_from_graph_node(_simple_person(name_is_hidden=True)) is None


def test_person_ref_from_graph_node_returns_key_and_index():
    ref = person_ref_from_graph_node(_simple_person(index=42))
    assert ref == (PersonKey(p="jean", n="dupont", oc=0), 42)


def test_individual_from_person_maps_events_and_relations():
    person = {
        "index": 7,
        "sex": "MALE",
        "lastname": "Barbel",
        "firstname": "Étienne",
        "n": "barbel",
        "p": "etienne",
        "occ": 0,
        "occupation": "Cultivateur",
        "notes": "<p>Some notes with &#39;entity&#39;<br>second line</p>",
        "events": {
            "elements": [
                {"type": "EPERS_BIRTH", "date": "23 Jan 1882", "place": "Sérignan"},
                {"type": "EFAM_MARRIAGE", "date": "10 Feb 1906", "place": "Béziers"},
                {"type": "EPERS_DEATH", "date": "13 Mar 1963", "place": "Sérignan"},
            ]
        },
        "father": _simple_person(index=11, p="guillaume", n="barbel", firstname="Guillaume"),
        "mother": _simple_person(
            index=12, p="marguerite", n="guiraud", firstname="Marguerite", sex="FEMALE"
        ),
        "families": [
            {
                "spouse": _simple_person(
                    index=8, p="marie", n="chauvin", firstname="Marie", sex="FEMALE"
                ),
                "marriage_date": "10 Feb 1906",
                "marriage_place": "Béziers",
                "children": [
                    _simple_person(index=4, p="paul", n="barbel", firstname="Paul"),
                ],
            }
        ],
    }

    individual, families, related = individual_from_person(person)

    assert individual.key == PersonKey(p="etienne", n="barbel", oc=0)
    assert individual.given_name == "Étienne"
    assert individual.occupation == "Cultivateur"
    # EFAM_MARRIAGE is excluded from personal events (it's on the Family instead)
    assert [e.tag for e in individual.events] == ["BIRT", "DEAT"]
    assert individual.notes[0].text == "Some notes with 'entity'\nsecond line"
    assert individual.father == PersonKey(p="guillaume", n="barbel", oc=0)
    assert individual.mother == PersonKey(p="marguerite", n="guiraud", oc=0)

    assert len(families) == 1
    fam = families[0]
    assert fam.husband == individual.key
    assert fam.wife == PersonKey(p="marie", n="chauvin", oc=0)
    assert fam.children == [PersonKey(p="paul", n="barbel", oc=0)]
    assert fam.marriage.tag == "MARR"
    assert fam.marriage.date == "10 Feb 1906"

    assert (PersonKey(p="guillaume", n="barbel", oc=0), 11) in related
    assert (PersonKey(p="marguerite", n="guiraud", oc=0), 12) in related
    assert (PersonKey(p="marie", n="chauvin", oc=0), 8) in related
    assert (PersonKey(p="paul", n="barbel", oc=0), 4) in related


def test_individual_from_person_excludes_hidden_parent():
    person = {
        "index": 1,
        "sex": "MALE",
        "lastname": "Dupont",
        "firstname": "Jean",
        "n": "dupont",
        "p": "jean",
        "occ": 0,
        "father": _simple_person(index=2, name_is_hidden=True),
    }
    individual, _families, related = individual_from_person(person)
    assert individual.father is None
    assert related == set()


def test_gedcom_date_sure_full_date():
    assert gedcom_date("/1882/1/23#", "GREGORIAN", "Jan. 23, 1882") == "23 JAN 1882"


def test_gedcom_date_year_only():
    assert gedcom_date("/1906/0/0#", "GREGORIAN", "1906") == "1906"


def test_gedcom_date_month_and_year_only():
    assert gedcom_date("?/1687/1/0#", "GREGORIAN", "possibly Jan., 1687") == "EST JAN 1687"


def test_gedcom_date_maybe_maps_to_est():
    # This is the bug report: "peut-être 1946" must not leak into GEDCOM;
    # GeneWeb's "?" precision maps to GEDCOM's EST qualifier.
    assert gedcom_date("?/1946/0/0#", "GREGORIAN", "peut-être 1946") == "EST 1946"


def test_gedcom_date_about():
    assert gedcom_date("~/1668/0/0#", "GREGORIAN", "about 1668") == "ABT 1668"


def test_gedcom_date_before():
    assert gedcom_date("</1891/0/0#", "GREGORIAN", "before 1891") == "BEF 1891"


def test_gedcom_date_after():
    assert gedcom_date(">/1823/0/0#", "GREGORIAN", "after 1823") == "AFT 1823"


def test_gedcom_date_between_range():
    assert (
        gedcom_date("/1652/0/0#../1654/0/0", "GREGORIAN", "between 1652 and 1654")
        == "BET 1652 AND 1654"
    )


def test_gedcom_date_julian_uses_calendar_escape():
    assert gedcom_date("/1700/3/1#", "JULIAN", "1 Mar 1700") == "@#DJULIAN@ 1 MAR 1700"


def test_gedcom_date_unparseable_calendar_falls_back_to_text():
    # French Republican raw numbers don't reliably map to plain D/M/Y —
    # deliberately not parsed; the localized text is used as-is instead.
    assert gedcom_date("?/1805/1/13#", "FRENCH", "23 Nivose year XIII") == "23 Nivose year XIII"


def test_gedcom_date_missing_raw_falls_back_to_text():
    assert gedcom_date(None, None, "some free text") == "some free text"


def test_gedcom_date_unrecognized_raw_falls_back_to_text():
    assert gedcom_date("BEF 1905 AFT 1907", None, "(BEF 1905 AFT 1907)") == "(BEF 1905 AFT 1907)"


def test_individual_from_person_sets_type_on_generic_events_only():
    person = {
        "index": 1,
        "sex": "MALE",
        "lastname": "Dupont",
        "firstname": "Jean",
        "n": "dupont",
        "p": "jean",
        "occ": 0,
        "events": {
            "elements": [
                {"type": "EPERS_BIRTH", "name": "birth", "date": "1950"},
                {"type": "EPERS_CUSTOM", "name": "Correspondance", "date": "1946"},
            ]
        },
    }
    individual, _families, _related = individual_from_person(person)
    birth, custom = individual.events
    assert birth.tag == "BIRT"
    assert birth.type is None
    assert custom.tag == "EVEN"
    assert custom.type == "Correspondance"


def _base_person(**overrides):
    base = {
        "index": 1,
        "sex": "MALE",
        "lastname": "Dupont",
        "firstname": "Jean",
        "n": "dupont",
        "p": "jean",
        "occ": 0,
    }
    base.update(overrides)
    return base


def test_individual_from_person_maps_psources():
    person = _base_person(psources="Some &#39;archival&#39; reference")
    individual, _families, _related = individual_from_person(person)
    assert individual.sources == ["Some 'archival' reference"]


def test_individual_from_person_event_source_and_reason():
    person = _base_person(
        events={
            "elements": [
                {
                    "type": "EPERS_BIRTH",
                    "name": "birth",
                    "date": "1950",
                    "src": "Registre des naissances, acte 12",
                    "reason": "Because reasons",
                }
            ]
        }
    )
    individual, _families, _related = individual_from_person(person)
    (birth,) = individual.events
    assert birth.source == "Registre des naissances, acte 12"
    assert birth.note.text == "Reason: Because reasons"


def test_individual_from_person_event_witnesses_filters_privacy():
    visible_witness = _simple_person(index=9, p="marie", n="martin")
    hidden_witness = _simple_person(index=10, p="hidden", n="person", name_is_hidden=True)
    person = _base_person(
        events={
            "elements": [
                {
                    "type": "EPERS_BIRTH",
                    "name": "birth",
                    "witnesses": [
                        {"witness_type": "WITNESS_GODPARENT", "witness": visible_witness, "witness_note": "note"},
                        {"witness_type": "WITNESS", "witness": hidden_witness},
                    ],
                }
            ]
        }
    )
    individual, _families, _related = individual_from_person(person)
    (birth,) = individual.events
    assert len(birth.witnesses) == 1
    witness = birth.witnesses[0]
    assert witness.person == PersonKey(p="marie", n="martin", oc=0)
    assert witness.role == "Godparent"
    assert witness.note == "note"


def test_individual_from_person_family_notes_and_sources():
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "notes": "Some family note",
                "fsources": "Family source citation",
            }
        ]
    )
    individual, families, _related = individual_from_person(person)
    (fam,) = families
    assert fam.notes[0].text == "Some family note"
    assert fam.sources == ["Family source citation"]
    assert fam.key in individual.family_keys


def test_individual_from_person_marriage_src_attaches_to_marriage_event():
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "marriage_date": "1950",
                "marriage_src": "Marriage register citation",
            }
        ]
    )
    _individual, families, _related = individual_from_person(person)
    (fam,) = families
    assert fam.marriage.source == "Marriage register citation"


def test_individual_from_person_marriage_type_engaged_maps_to_enga():
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "marriage_date": "1950",
                "marriage_type": "ENGAGED",
            }
        ]
    )
    _individual, families, _related = individual_from_person(person)
    (fam,) = families
    assert fam.marriage.tag == "ENGA"
    assert fam.marriage.type is None


def test_individual_from_person_marriage_type_no_mention_falls_back_to_generic_event():
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "marriage_place": "Somewhere",
                "marriage_type": "NO_MENTION",
            }
        ]
    )
    _individual, families, _related = individual_from_person(person)
    (fam,) = families
    assert fam.marriage.tag == "EVEN"
    assert fam.marriage.type == "No mention"


def test_individual_from_person_divorce_event_mapped_to_div():
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "divorce_type": "DIVORCED",
                "divorce_date": "1960",
            }
        ]
    )
    _individual, families, _related = individual_from_person(person)
    (fam,) = families
    assert fam.divorce.tag == "DIV"


def test_individual_from_person_no_divorce_event_when_not_divorced():
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "divorce_type": "NOT_DIVORCED",
            }
        ]
    )
    _individual, families, _related = individual_from_person(person)
    (fam,) = families
    assert fam.divorce is None


def test_individual_from_person_family_witnesses_on_marriage():
    witness = _simple_person(index=9, p="paul", n="temoin")
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "marriage_date": "1950",
                "witnesses": [{"witness_type": "WITNESS_CIVILOFFICER", "witness": witness}],
            }
        ]
    )
    _individual, families, _related = individual_from_person(person)
    (fam,) = families
    assert len(fam.marriage.witnesses) == 1
    assert fam.marriage.witnesses[0].role == "Civil officer"
