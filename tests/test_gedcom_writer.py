from exportgeneanet.gedcom_writer import generate_gedcom
from exportgeneanet.models import Event, Family, Individual, Note, Place
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
