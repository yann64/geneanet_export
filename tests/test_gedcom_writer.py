from exportgeneanet.gedcom_writer import generate_gedcom
from exportgeneanet.models import Event, Family, Individual, Note, Place, Witness
from exportgeneanet.identifiers import PersonKey


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
        events=[Event(tag="BIRT", date="1 JAN 1950", place=Place("Paris"))],
        notes=[Note("A note about Jean.")],
    )

    family = Family(
        key=f"{father_key}__{mother_key}",
        husband=father_key,
        wife=mother_key,
        children=[child_key],
        marriage=Event(tag="MARR", date="5 JUN 1945"),
    )

    individuals = {str(k): v for k, v in [(father_key, father), (mother_key, mother), (child_key, child)]}
    families = {family.key: family}
    return individuals, families


def test_generate_gedcom_has_head_and_trailer():
    individuals, families = _sample_data()
    gedcom = generate_gedcom(individuals, families)
    assert gedcom.startswith("0 HEAD\n")
    assert gedcom.rstrip("\n").endswith("0 TRLR")


def test_generate_gedcom_individual_record():
    individuals, families = _sample_data()
    gedcom = generate_gedcom(individuals, families)
    assert "1 NAME Jean /Dupont/" in gedcom
    assert "1 SEX M" in gedcom
    assert "1 BIRT" in gedcom
    assert "2 DATE 1 JAN 1950" in gedcom
    assert "2 PLAC Paris" in gedcom


def test_generate_gedcom_family_links():
    individuals, families = _sample_data()
    gedcom = generate_gedcom(individuals, families)
    assert "1 HUSB" in gedcom
    assert "1 WIFE" in gedcom
    assert "1 CHIL" in gedcom
    assert "1 FAMC" in gedcom  # child links back to the family
    assert "1 MARR" in gedcom
    assert "2 DATE 5 JUN 1945" in gedcom


def test_generate_gedcom_excludes_notes_when_disabled():
    individuals, families = _sample_data()
    gedcom = generate_gedcom(individuals, families, include_notes=False)
    assert "A note about Jean." not in gedcom


def test_generate_gedcom_generic_event_includes_type():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[Event(tag="EVEN", date="1946", type="Correspondance")],
    )
    gedcom = generate_gedcom({str(key): individual}, {})
    lines = gedcom.splitlines()
    even_idx = lines.index("1 EVEN")
    assert lines[even_idx + 1] == "2 TYPE Correspondance"


def test_generate_gedcom_dedupes_repeated_source_citation():
    key1 = PersonKey(p="jean", n="dupont", oc=0)
    key2 = PersonKey(p="paul", n="dupont", oc=0)
    same_text = "Registre des naissances, acte 12"
    ind1 = Individual(
        key=key1,
        given_name="Jean",
        surname="Dupont",
        events=[Event(tag="BIRT", date="1950", source=same_text)],
    )
    ind2 = Individual(
        key=key2,
        given_name="Paul",
        surname="Dupont",
        events=[Event(tag="BIRT", date="1952", source=same_text)],
    )
    gedcom = generate_gedcom({str(key1): ind1, str(key2): ind2}, {})
    assert gedcom.count("0 @S1@ SOUR") == 1
    assert gedcom.count("@S1@") == 3  # one record + two citation pointers
    assert "1 TITL Registre des naissances, acte 12" in gedcom


def test_generate_gedcom_individual_and_family_level_sources():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key, given_name="Jean", surname="Dupont", sources=["Person-level source"]
    )
    family = Family(key="fam1", husband=key, sources=["Family-level source"])
    gedcom = generate_gedcom({str(key): individual}, {"fam1": family})
    assert "1 TITL Person-level source" in gedcom
    assert "1 TITL Family-level source" in gedcom


def test_generate_gedcom_divorce_event():
    key1 = PersonKey(p="jean", n="dupont", oc=0)
    key2 = PersonKey(p="marie", n="martin", oc=0)
    family = Family(key="fam1", husband=key1, wife=key2, divorce=Event(tag="DIV", date="1960"))
    gedcom = generate_gedcom({}, {"fam1": family})
    assert "1 DIV" in gedcom
    assert "2 DATE 1960" in gedcom


def test_generate_gedcom_witness_asso_only_when_witness_in_export():
    key = PersonKey(p="jean", n="dupont", oc=0)
    witness_key = PersonKey(p="marie", n="martin", oc=0)
    unexported_witness_key = PersonKey(p="ghost", n="nobody", oc=0)
    witness_individual = Individual(key=witness_key, given_name="Marie", surname="Martin")
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[
            Event(
                tag="BIRT",
                witnesses=[
                    Witness(person=witness_key, role="Godparent"),
                    Witness(person=unexported_witness_key, role="Witness"),
                ],
            )
        ],
    )
    gedcom = generate_gedcom({str(key): individual, str(witness_key): witness_individual}, {})
    assert f"2 ASSO @{witness_individual.gedcom_id}@" in gedcom
    assert "3 RELA Godparent" in gedcom
    # The unexported witness must not produce a dangling pointer or a
    # fabricated INDI record.
    assert "Ghost" not in gedcom
    assert gedcom.count("ASSO") == 1


def test_generate_gedcom_excludes_event_notes_and_witness_notes_when_disabled():
    key = PersonKey(p="jean", n="dupont", oc=0)
    witness_key = PersonKey(p="marie", n="martin", oc=0)
    witness_individual = Individual(key=witness_key, given_name="Marie", surname="Martin")
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        events=[
            Event(
                tag="BIRT",
                note=Note("event note"),
                witnesses=[Witness(person=witness_key, note="witness note")],
            )
        ],
    )
    gedcom = generate_gedcom(
        {str(key): individual, str(witness_key): witness_individual}, {}, include_notes=False
    )
    assert "event note" not in gedcom
    assert "witness note" not in gedcom
