from pathlib import Path

from exportgeneanet.identifiers import PersonKey
from exportgeneanet.models import Event, Family, Individual, Note, Place, SourceCitation, Witness
from exportgeneanet.tree_crawler import CrawlState


def test_crawl_state_save_and_load_roundtrip(tmp_path: Path):
    key = PersonKey(p="jean", n="dupont", oc=0)
    father_key = PersonKey(p="pierre", n="dupont", oc=0)

    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        sex="M",
        father=father_key,
        events=[Event(tag="BIRT", date="1 JAN 1950", place=Place("Paris"), note=Note("approx."))],
        notes=[Note("Some note")],
    )
    family = Family(key=f"{father_key}__UNK", husband=father_key, children=[key])

    state = CrawlState(
        visited={str(key)},
        queue=[(father_key, 11)],
        individuals={str(key): individual},
        families={family.key: family},
    )

    path = tmp_path / "state.json"
    state.save(path)
    loaded = CrawlState.load(path)

    assert loaded.visited == state.visited
    assert loaded.queue == state.queue
    assert loaded.individuals[str(key)].given_name == "Jean"
    assert loaded.individuals[str(key)].father == father_key
    assert loaded.individuals[str(key)].events[0].place.name == "Paris"
    assert loaded.families[family.key].husband == father_key
    assert loaded.families[family.key].children == [key]


def test_crawl_state_roundtrip_preserves_type_sources_witnesses_and_divorce(tmp_path: Path):
    key = PersonKey(p="jean", n="dupont", oc=0)
    witness_key = PersonKey(p="marie", n="martin", oc=0)

    individual = Individual(
        key=key,
        given_name="Jean",
        surname="Dupont",
        sources=[SourceCitation(title="Geneanet cite", page="https://x", is_geneanet_source=True)],
        events=[
            Event(
                tag="EVEN",
                type="Correspondance",
                sources=[SourceCitation(title="Some source")],
                witnesses=[Witness(person=witness_key, role="Godparent", note="oncle")],
            )
        ],
    )
    family = Family(
        key="fam1",
        husband=key,
        divorce=Event(tag="DIV", date="1960"),
        sources=[SourceCitation(title="Family source")],
    )

    state = CrawlState(
        visited={str(key)},
        individuals={str(key): individual},
        families={family.key: family},
    )

    path = tmp_path / "state.json"
    state.save(path)
    loaded = CrawlState.load(path)

    loaded_individual = loaded.individuals[str(key)]
    assert loaded_individual.sources[0].title == "Geneanet cite"
    assert loaded_individual.sources[0].is_geneanet_source is True
    loaded_event = loaded_individual.events[0]
    assert loaded_event.type == "Correspondance"
    assert loaded_event.sources[0].title == "Some source"
    assert loaded_event.witnesses[0].person == witness_key
    assert loaded_event.witnesses[0].role == "Godparent"

    loaded_family = loaded.families["fam1"]
    assert loaded_family.divorce.tag == "DIV"
    assert loaded_family.sources[0].title == "Family source"
