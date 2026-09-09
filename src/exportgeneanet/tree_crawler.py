"""Orchestrates crawling Geneanet's API into a full in-memory dataset.

Two crawl strategies, matching the CLI's `--scope` option:

- `crawl_ascendants`: one `graph_v2` call discovers every ancestor's index in
  a lineage in a single request (instead of walking one relation at a time),
  then one `get_person` call per discovered ancestor fetches full detail
  (events/notes/sources — `graph_v2` nodes are lightweight summaries only).
  Family records are synthesized from each person's own father/mother
  fields, deliberately ignoring their own spouse/children — ascendants scope
  stays exactly the lineage, not the extended family of each ancestor.
- `crawl_full`: BFS over the whole family graph (parents, spouses, children)
  starting from one seed individual, via the `related` set every
  `get_person` call already returns. There is no confirmed "list every
  individual" API action (unlike the old HTML `LIST_IND` listing this
  project used before the API pivot), so a seed is required — a tree is a
  single connected component in practice, so BFS from any one person reaches
  everyone connected to them.

Progress is checkpointed to a JSON file after every individual so a crawl
interrupted partway through (a large full-tree export can take a while once
rate-limited) can be resumed with `--resume` instead of starting over and
re-hitting people already fetched.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from . import mapping
from .api_client import GeneanetApiClient
from .identifiers import PersonKey
from .models import Event, Family, Individual, Media, Note, Place


@dataclass
class CrawlState:
    visited: set[str] = field(default_factory=set)
    queue: list[tuple[PersonKey, int]] = field(default_factory=list)
    individuals: dict[str, Individual] = field(default_factory=dict)
    families: dict[str, Family] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        payload = {
            "visited": sorted(self.visited),
            "queue": [{"key": asdict(k), "index": i} for k, i in self.queue],
            "individuals": {k: asdict(v) for k, v in self.individuals.items()},
            "families": {k: asdict(v) for k, v in self.families.items()},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> "CrawlState":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CrawlState(
            visited=set(payload["visited"]),
            queue=[(PersonKey(**e["key"]), e["index"]) for e in payload["queue"]],
            individuals={k: _individual_from_dict(v) for k, v in payload["individuals"].items()},
            families={k: _family_from_dict(v) for k, v in payload["families"].items()},
        )


def _event_from_dict(d: dict | None) -> Event | None:
    if d is None:
        return None
    return Event(
        tag=d["tag"],
        date=d.get("date"),
        place=Place(**d["place"]) if d.get("place") else None,
        note=Note(**d["note"]) if d.get("note") else None,
    )


def _individual_from_dict(d: dict) -> Individual:
    return Individual(
        key=PersonKey(**d["key"]),
        given_name=d["given_name"],
        surname=d["surname"],
        sex=d.get("sex", "U"),
        events=[_event_from_dict(e) for e in d.get("events", [])],
        occupation=d.get("occupation"),
        notes=[Note(**n) for n in d.get("notes", [])],
        media=[Media(**m) for m in d.get("media", [])],
        father=PersonKey(**d["father"]) if d.get("father") else None,
        mother=PersonKey(**d["mother"]) if d.get("mother") else None,
        family_keys=list(d.get("family_keys", [])),
        source_url=d.get("source_url"),
    )


def _family_from_dict(d: dict) -> Family:
    return Family(
        key=d["key"],
        husband=PersonKey(**d["husband"]) if d.get("husband") else None,
        wife=PersonKey(**d["wife"]) if d.get("wife") else None,
        children=[PersonKey(**c) for c in d.get("children", [])],
        marriage=_event_from_dict(d.get("marriage")),
        notes=[Note(**n) for n in d.get("notes", [])],
    )


def crawl_ascendants(
    client: GeneanetApiClient,
    root: PersonKey,
    nb_asc: int = 20,
    state: CrawlState | None = None,
    state_path: Path | None = None,
    on_progress=None,
) -> CrawlState:
    state = state or CrawlState()

    if not state.queue and not state.visited:
        graph = client.get_graph(p=root.p, n=root.n, oc=root.oc, nb_asc=nb_asc, nb_desc=0)
        graph_dict = MessageToDict(graph, preserving_proto_field_name=True)
        seen: set[str] = set()
        for node in graph_dict.get("nodes_asc", []):
            ref = mapping.person_ref_from_graph_node(node["person"])
            if ref and str(ref[0]) not in seen:
                seen.add(str(ref[0]))
                state.queue.append(ref)

    while state.queue:
        key, index = state.queue.pop(0)
        if str(key) in state.visited:
            continue
        person_dict = MessageToDict(client.get_person(index), preserving_proto_field_name=True)
        individual, _families, _related = mapping.individual_from_person(person_dict)
        state.individuals[str(key)] = individual
        state.visited.add(str(key))

        father, mother = individual.father, individual.mother
        if father or mother:
            fam_key = f"{father or 'UNK'}__{mother or 'UNK'}"
            fam = state.families.get(fam_key) or Family(key=fam_key, husband=father, wife=mother)
            if key not in fam.children:
                fam.children.append(key)
            state.families[fam_key] = fam

        if state_path is not None:
            state.save(state_path)
        if on_progress is not None:
            on_progress(individual)

    return state


def crawl_full(
    client: GeneanetApiClient,
    seed: PersonKey,
    state: CrawlState | None = None,
    state_path: Path | None = None,
    on_progress=None,
) -> CrawlState:
    state = state or CrawlState()

    if not state.queue and not state.visited:
        result = client.search_persons(lastname=seed.n, firstname=seed.p, limit=5)
        result_dict = MessageToDict(result, preserving_proto_field_name=True)
        seed_index = next(
            (
                int(p["index"])
                for p in result_dict.get("persons", [])
                if (ref := p.get("reference", {}))
                and ref.get("p", "").lower() == seed.p.lower()
                and ref.get("n", "").lower() == seed.n.lower()
                and int(ref.get("oc", 0)) == seed.oc
            ),
            None,
        )
        if seed_index is None:
            raise ValueError(f"could not resolve seed individual {seed} via search")
        state.queue.append((seed, seed_index))

    queue: deque[tuple[PersonKey, int]] = deque(state.queue)
    while queue:
        key, index = queue.popleft()
        if str(key) in state.visited:
            continue
        person_dict = MessageToDict(client.get_person(index), preserving_proto_field_name=True)
        individual, families, related = mapping.individual_from_person(person_dict)
        state.individuals[str(key)] = individual
        state.visited.add(str(key))
        for fam in families:
            state.families[fam.key] = fam
        for related_key, related_index in related:
            if str(related_key) not in state.visited:
                queue.append((related_key, related_index))

        state.queue = list(queue)
        if state_path is not None:
            state.save(state_path)
        if on_progress is not None:
            on_progress(individual)

    return state
