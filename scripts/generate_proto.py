#!/usr/bin/env python
"""Fetch Geneanet's own protobuf schemas and compile them into
src/exportgeneanet/proto/.

Geneanet publishes the `.proto` files its internal API
(https://gw.geneanet.org/setup/api/) uses right at that same path — this is
how the reference Gramps addon (jmichault/gramps-kromprogramoj, GPL-3.0)
builds its Python bindings too. Uses `grpc_tools.protoc` (pure pip package)
rather than a system `protoc` binary, so no elevated/system install is
needed.

Run this only when Geneanet changes its API schema; the generated files are
committed to the repo, so normal installs/users never need to run it.

    pip install -e ".[dev]"
    python scripts/generate_proto.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

PROTO_BASE_URL = "https://gw.geneanet.org/setup/api"
PROTO_NAMES = ["api", "api_app", "api_stats", "api_saisie_read", "api_saisie_write"]
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "src" / "exportgeneanet" / "proto"

# Only api_saisie_read.proto imports api.proto in a way that needs a relative
# import fixup for the generated Python module to work as part of our package.
_IMPORT_FIX = [
    (re.compile(r"^import api_pb2 as api__pb2$", re.MULTILINE), "from . import api_pb2 as api__pb2"),
    (re.compile(r"^from api_pb2 import ", re.MULTILINE), "from .api_pb2 import "),
]


def fetch_proto(name: str, dest_dir: Path) -> Path:
    url = f"{PROTO_BASE_URL}/{name}.proto"
    request = Request(url, headers={"User-Agent": USER_AGENT, "DNT": "1"})
    with urlopen(request, timeout=15) as response:
        content = response.read()
    dest = dest_dir / f"{name}.proto"
    dest.write_bytes(content)
    print(f"fetched {url} -> {dest} ({len(content)} bytes)")
    return dest


def compile_proto(proto_path: Path, src_dir: Path, out_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"--proto_path={src_dir}",
            f"--python_out={out_dir}",
            proto_path.name,
        ],
        cwd=src_dir,
        check=True,
    )


def fix_imports(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for pattern, replacement in _IMPORT_FIX:
        text = pattern.sub(replacement, text)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    init_file = OUTPUT_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        src_dir = Path(tmp)
        for name in PROTO_NAMES:
            proto_path = fetch_proto(name, src_dir)
            compile_proto(proto_path, src_dir, OUTPUT_DIR)

    for generated in OUTPUT_DIR.glob("*_pb2.py"):
        fix_imports(generated)
    print(f"done: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
