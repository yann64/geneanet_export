"""Person identifiers within a Geneanet tree.

GeneWeb identifies an individual by given name (`p`), surname (`n`) and an
`oc` occurrence number that disambiguates same-name individuals. Geneanet's
API also has an internal integer `index` per person, but that's an
implementation detail of a given API response (see `api_client.py`/
`mapping.py`) — `PersonKey` stays the stable, human-meaningful identifier
used everywhere else (models, GEDCOM ids, the CLI's `--individual` flag).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonKey:
    """Identifies one individual within a tree: given name + surname + occurrence."""

    p: str
    n: str
    oc: int = 0

    def __str__(self) -> str:
        return f"{self.p}.{self.n}.{self.oc}"

    @staticmethod
    def parse(text: str) -> PersonKey:
        """Parse the `--individual` CLI value, formatted as `given.surname.oc`."""
        parts = text.split(".")
        if len(parts) < 2:
            raise ValueError(f"invalid person key {text!r}, expected 'given.surname[.oc]'")
        if len(parts) >= 3 and parts[-1].isdigit():
            oc = int(parts[-1])
            name_parts = parts[:-1]
        else:
            oc = 0
            name_parts = parts
        p, n = name_parts[0], ".".join(name_parts[1:])
        return PersonKey(p=p, n=n, oc=oc)
