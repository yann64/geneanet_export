from exportgeneanet.identifiers import PersonKey
from exportgeneanet.mapping import (
    gedcom_date,
    geneanet_tree_citation,
    individual_from_person,
    is_publicly_visible,
    person_citation_url,
    person_ref_from_graph_node,
)
from exportgeneanet.models import AlternateName

USERNAME = "yann64"


def _titles(citations):
    return [c.title for c in citations]


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

    individual, families, related = individual_from_person(person, USERNAME)

    assert individual.key == PersonKey(p="etienne", n="barbel", oc=0)
    assert individual.given_name == "Étienne"
    assert individual.occupation == "Cultivateur"
    # EFAM_MARRIAGE is excluded from personal events (it's on the Family instead)
    assert [e.tag for e in individual.events] == ["BIRT", "DEAT"]
    assert individual.notes[0].text == "Some notes with 'entity'\nsecond line"
    assert individual.father == PersonKey(p="guillaume", n="barbel", oc=0)
    assert individual.mother == PersonKey(p="marguerite", n="guiraud", oc=0)
    assert individual.source_url == person_citation_url(USERNAME, individual.key)

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
    individual, _families, related = individual_from_person(person, USERNAME)
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
    individual, _families, _related = individual_from_person(person, USERNAME)
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
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert "Some 'archival' reference" in _titles(individual.sources)
    # Every individual also gets the shared Geneanet-tree attribution.
    assert any(c.is_geneanet_source for c in individual.sources)


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
    individual, _families, _related = individual_from_person(person, USERNAME)
    (birth,) = individual.events
    assert "Registre des naissances, acte 12" in _titles(birth.sources)
    assert any(c.is_geneanet_source for c in birth.sources)
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
    individual, _families, _related = individual_from_person(person, USERNAME)
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
    individual, families, _related = individual_from_person(person, USERNAME)
    (fam,) = families
    assert fam.notes[0].text == "Some family note"
    assert "Family source citation" in _titles(fam.sources)
    assert any(c.is_geneanet_source for c in fam.sources)
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
    _individual, families, _related = individual_from_person(person, USERNAME)
    (fam,) = families
    assert "Marriage register citation" in _titles(fam.marriage.sources)
    assert any(c.is_geneanet_source for c in fam.marriage.sources)


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
    _individual, families, _related = individual_from_person(person, USERNAME)
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
    _individual, families, _related = individual_from_person(person, USERNAME)
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
    _individual, families, _related = individual_from_person(person, USERNAME)
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
    _individual, families, _related = individual_from_person(person, USERNAME)
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
    _individual, families, _related = individual_from_person(person, USERNAME)
    (fam,) = families
    assert len(fam.marriage.witnesses) == 1
    assert fam.marriage.witnesses[0].role == "Civil officer"


def test_person_citation_url_builds_gw_geneanet_url():
    key = PersonKey(p="jean", n="dupont", oc=2)
    assert person_citation_url("yann64", key) == "https://gw.geneanet.org/yann64?p=jean&n=dupont&oc=2"


def test_geneanet_tree_citation_is_flagged_and_shares_title_across_pages():
    citation1 = geneanet_tree_citation(USERNAME, "https://gw.geneanet.org/yann64?p=jean&n=dupont&oc=0")
    citation2 = geneanet_tree_citation(USERNAME, "https://gw.geneanet.org/yann64?p=marie&n=martin&oc=0")
    assert citation1.is_geneanet_source
    assert citation1.title == citation2.title  # same tree -> dedupes to one SOUR record
    assert citation1.page != citation2.page  # but each citation keeps its own PAGE
    assert USERNAME in citation1.title


def test_individual_from_person_divorce_event_gets_geneanet_source():
    person = _base_person(
        families=[
            {
                "spouse": _simple_person(index=2, p="marie", n="martin", sex="FEMALE"),
                "divorce_type": "DIVORCED",
                "divorce_date": "1960",
            }
        ]
    )
    _individual, families, _related = individual_from_person(person, USERNAME)
    (fam,) = families
    assert any(c.is_geneanet_source for c in fam.divorce.sources)


def test_individual_from_person_event_without_src_still_gets_geneanet_source():
    person = _base_person(events={"elements": [{"type": "EPERS_BIRTH", "name": "birth", "date": "1950"}]})
    individual, _families, _related = individual_from_person(person, USERNAME)
    (birth,) = individual.events
    assert len(birth.sources) == 1
    assert birth.sources[0].is_geneanet_source


def test_individual_from_person_maps_nickname_from_qualifiers():
    person = _base_person(qualifiers=["Cyr"])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert individual.nickname == "Cyr"


def test_individual_from_person_joins_multiple_qualifiers():
    person = _base_person(qualifiers=["Cyr", "Le Grand"])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert individual.nickname == "Cyr, Le Grand"


def test_individual_from_person_maps_titles():
    person = _base_person(titles=["Comte de Something"])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert individual.titles == ["Comte de Something"]


def test_individual_from_person_maps_aliases_unslashed():
    person = _base_person(aliases=["Marguerite Chauzy"])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert individual.names == [AlternateName(given="Marguerite Chauzy", surname=None)]


def test_individual_from_person_maps_public_name_unslashed():
    person = _base_person(public_name="Some Public Name")
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert individual.names == [AlternateName(given="Some Public Name", surname=None)]


def test_individual_from_person_maps_firstname_and_surname_aliases_slashed():
    person = _base_person(firstname_aliases=["Bobby"], surname_aliases=["Dupond"])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert AlternateName(given="Bobby", surname="Dupont") in individual.names
    assert AlternateName(given="Jean", surname="Dupond") in individual.names


def test_individual_from_person_maps_rparents_godparent():
    godparent = _simple_person(index=13, p="marie", n="godmother", sex="FEMALE")
    person = _base_person(rparents=[{"r_type": "RPARENT_GOD_PARENT", "person": godparent}])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert len(individual.associations) == 1
    assoc = individual.associations[0]
    assert assoc.person == PersonKey(p="marie", n="godmother", oc=0)
    assert assoc.role == "Godparent"


def test_individual_from_person_maps_related_godchild():
    godchild = _simple_person(index=14, p="paul", n="godchild")
    person = _base_person(related=[{"r_type": "RCHILD_GOD_PARENT", "person": godchild}])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert individual.associations[0].role == "Godchild"


def test_individual_from_person_excludes_hidden_rparent():
    hidden = _simple_person(index=13, p="x", n="x", name_is_hidden=True)
    person = _base_person(rparents=[{"r_type": "RPARENT_GOD_PARENT", "person": hidden}])
    individual, _families, _related = individual_from_person(person, USERNAME)
    assert individual.associations == []
