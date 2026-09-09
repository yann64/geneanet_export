from exportgeneanet.identifiers import PersonKey
from exportgeneanet.mapping import (
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
