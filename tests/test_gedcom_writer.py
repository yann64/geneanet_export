from exportgeneanet.gedcom_writer import generate_gedcom
from exportgeneanet.models import AlternateName, Event, Family, Individual, Note, Place, SourceCitation, Witness
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
        events=[Event(tag="BIRT", date="1950", sources=[SourceCitation(title=same_text)])],
    )
    ind2 = Individual(
        key=key2,
        given_name="Paul",
        surname="Dupont",
        events=[Event(tag="BIRT", date="1952", sources=[SourceCitation(title=same_text)])],
    )
    gedcom = generate_gedcom({str(key1): ind1, str(key2): ind2}, {})
    assert gedcom.count("0 @S1@ SOUR") == 1
    assert gedcom.count("@S1@") == 3  # one record + two citation pointers
    assert "1 TITL Registre des naissances, acte 12" in gedcom
    # A plain archival citation (not flagged as the Geneanet-tree source)
    # must not fabricate a REPO record or link.
    assert "REPO" not in gedcom


def test_generate_gedcom_individual_and_family_level_sources():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        sources=[SourceCitation(title="Person-level source")],
    )
    family = Family(key="fam1", husband=key, sources=[SourceCitation(title="Family-level source")])
    gedcom = generate_gedcom({str(key): individual}, {"fam1": family})
    assert "1 TITL Person-level source" in gedcom
    assert "1 TITL Family-level source" in gedcom


def test_generate_gedcom_geneanet_source_gets_repo_link_and_page():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        sources=[
            SourceCitation(
                title="Geneanet — tree owner",
                page="https://gw.geneanet.org/yann64?p=jean&n=dupont&oc=0",
                is_geneanet_source=True,
            )
        ],
    )
    gedcom = generate_gedcom({str(key): individual}, {})
    lines = gedcom.splitlines()

    assert "0 @R1@ REPO" in gedcom
    assert "1 NAME Geneanet" in gedcom
    assert "1 WWW https://www.geneanet.org/" in gedcom

    sour_idx = lines.index("0 @S1@ SOUR")
    assert lines[sour_idx + 1] == "1 TITL Geneanet — tree owner"
    assert "1 REPO @R1@" in lines[sour_idx : sour_idx + 3]

    # The citation under the INDI carries the PAGE (specific person URL).
    page_idx = lines.index("1 SOUR @S1@")
    assert lines[page_idx + 1] == "2 PAGE https://gw.geneanet.org/yann64?p=jean&n=dupont&oc=0"


def test_generate_gedcom_no_repo_when_no_geneanet_source():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        sources=[SourceCitation(title="Some archival citation")],
    )
    gedcom = generate_gedcom({str(key): individual}, {})
    assert "REPO" not in gedcom


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


def test_generate_gedcom_nickname_and_titles():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        nickname="Cyr",
        titles=["Comte de Something"],
    )
    gedcom = generate_gedcom({str(key): individual}, {})
    lines = gedcom.splitlines()
    assert "2 NICK Cyr" in lines
    name_idx = lines.index("1 NAME Jean /Dupont/")
    assert lines[name_idx + 1 : name_idx + 4] == ["2 GIVN Jean", "2 SURN Dupont", "2 NICK Cyr"]
    assert "1 TITL Comte de Something" in gedcom


def test_generate_gedcom_alternate_names():
    key = PersonKey(p="jean", n="dupont", oc=0)
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        names=[
            AlternateName(given="Marguerite Chauzy", surname=None),
            AlternateName(given="Bobby", surname="Dupont"),
        ],
    )
    gedcom = generate_gedcom({str(key): individual}, {})
    lines = gedcom.splitlines()
    unslashed_idx = lines.index("1 NAME Marguerite Chauzy")
    assert lines[unslashed_idx + 1] == "2 TYPE aka"
    slashed_idx = lines.index("1 NAME Bobby /Dupont/")
    assert lines[slashed_idx + 1] == "2 TYPE aka"


def test_generate_gedcom_individual_level_association():
    key = PersonKey(p="jean", n="dupont", oc=0)
    godparent_key = PersonKey(p="marie", n="martin", oc=0)
    godparent = Individual(key=godparent_key, given_name="Marie", surname="Martin")
    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        associations=[Witness(person=godparent_key, role="Godparent")],
    )
    gedcom = generate_gedcom({str(key): individual, str(godparent_key): godparent}, {})
    lines = gedcom.splitlines()
    asso_idx = lines.index(f"1 ASSO @{godparent.gedcom_id}@")
    assert lines[asso_idx + 1] == "2 TYPE INDI"
    assert lines[asso_idx + 2] == "2 RELA Godparent"
