#!/usr/bin/env python
"""Convert a Gramps XML place-hierarchy file into the compact lookup table
gramps_writer.py ships and reads at runtime (src/exportgeneanet/data/
france_places.json).

The source file (not committed — same treatment as the raw `.proto`
schemas `scripts/generate_proto.py` fetches) is
https://www.histoiredeserignan.fr/downloads/genealogy/lieux.gramps: ~35,000
French communes + world countries, each Gramps `<placeobj>` carrying a
stable `handle` and at most one `<placeref>` to its parent place, forming a
City -> Department -> Region -> Country tree. This script keeps only the
`handle`/`id`/`type`/name/`code`/parent fields gramps_writer.py's place
matching actually needs — dropping coordinates, change timestamps, and
alternate-language names shrinks the ~10MB source XML down to well under
1MB.

Run this only when the reference file changes; the generated JSON is
committed, so normal installs/users never need to run it.

    pip install -e ".[dev]"
    python scripts/convert_places_reference.py /path/to/lieux.gramps
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent / "src" / "exportgeneanet" / "data" / "france_places.json"
)

_NS = {"g": "http://gramps-project.org/xml/1.7.1/"}


def _local_name(place: ET.Element, tag: str) -> str | None:
    el = place.find(f"g:{tag}", _NS)
    return el.text if el is not None else None


def convert(source_path: Path) -> dict[str, dict]:
    tree = ET.parse(source_path)
    root = tree.getroot()
    nodes: dict[str, dict] = {}

    for place in root.findall("./g:places/g:placeobj", _NS):
        handle = place.attrib["handle"]
        # The primary local name is the first <pname>, always present
        # (Gramps DTD: "pname+") and listed with no lang= before any
        # lang="fr"-style alternates in this file.
        pname = place.find("g:pname", _NS)
        name = pname.attrib["value"]
        code = _local_name(place, "code") or ""
        placeref = place.find("g:placeref", _NS)
        parent = placeref.attrib["hlink"] if placeref is not None else None

        nodes[handle] = {
            "id": place.attrib.get("id", ""),
            "type": place.attrib["type"],
            "name": name,
            "code": code,
            "parent": parent,
        }

    return nodes


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)

    source_path = Path(sys.argv[1])
    nodes = convert(source_path)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    init_file = OUTPUT_PATH.parent / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, separators=(",", ":"))

    print(f"done: {len(nodes)} places -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
