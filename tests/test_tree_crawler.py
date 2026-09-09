from pathlib import Path

from exportgeneanet.identifiers import PersonKey
from exportgeneanet.models import Event, Family, Individual, Note, Place
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
