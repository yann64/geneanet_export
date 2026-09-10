"""Anonymous client for Geneanet's internal protobuf API.

`gw.geneanet.org`'s HTML pages sit behind a Cloudflare "managed challenge"
that blocks both headless and (per manual testing) even real browser
automation reliably. `https://gw.geneanet.org/setup/api/` — the same API
Geneanet's own Angular frontend calls after a page's shell loads — has no
such protection: confirmed in this project's development by fetching
`.proto` schema files and making real anonymous calls with plain `requests`,
no browser, no cookies. This client never authenticates: every call is made
exactly as an anonymous visitor's browser would make it, so it only ever
sees what's publicly displayed on the site.

Approach (including the response-decoding quirk) is modeled on the
`Api` class in jmichault/gramps-kromprogramoj's PersonGN Gramps addon
(GPL-3.0), which documents fetching these same `.proto` files directly from
Geneanet's server (see `scripts/generate_proto.py`).
"""

from __future__ import annotations

import json
from urllib.parse import quote

import requests
from google.protobuf.message import DecodeError, Message

from .config import API_BASE_URL, USER_AGENT
from .proto import api_saisie_read_pb2, api_saisie_write_pb2
from .rate_limiter import RateLimiter

_HEADERS = {
    "user-agent": USER_AGENT,
    "content-Type": "application/json;charset=UTF-8",
    "DNT": "1",
}


class GeneanetApiClient:
    """Anonymous, rate-limited client for one tree's `/setup/api/` endpoint."""

    def __init__(self, tree: str, rate_limiter: RateLimiter, lang: str = "en") -> None:
        self.tree = tree
        self.rate_limiter = rate_limiter
        self.lang = lang
        self.session = requests.Session()

    def _call(self, arbre: str, params: Message, response_cls: type[Message]) -> Message:
        self.rate_limiter.wait()
        body = json.dumps({"data": quote(params.SerializeToString())})
        url = f"{API_BASE_URL}/?arbre={arbre}&sourcename={self.tree}&lang={self.lang}&type="
        response = self.session.post(url, data=body, headers=_HEADERS, timeout=15)
        response.raise_for_status()
        result = response_cls()
        try:
            result.ParseFromString(response.content)
        except DecodeError:
            # Geneanet's own frontend round-trips the payload through this
            # odd re-encoding; matches the addon's handling exactly.
            result.ParseFromString(response.content.decode("utf-8").encode("raw_unicode_escape"))
        return result

    def search_persons(
        self, lastname: str | None = None, firstname: str | None = None, limit: int = 50
    ) -> api_saisie_write_pb2.PersonSearchList:
        """Search individuals by (partial) name. Each result embeds its
        father/mother/spouse(s), useful for both lookup and graph discovery."""
        params = api_saisie_write_pb2.PersonSearchListParams(
            lastname=lastname, firstname=firstname, limit=limit
        )
        return self._call("person_search_list", params, api_saisie_write_pb2.PersonSearchList)

    def get_graph(
        self,
        index: int | None = None,
        p: str | None = None,
        n: str | None = None,
        oc: int = 0,
        nb_asc: int = 0,
        nb_desc: int = 0,
    ) -> api_saisie_read_pb2.GraphTree:
        """Ascendants/descendants graph rooted at one person, `nb_asc`/`nb_desc`
        generations in each direction — several generations in a single call."""
        if index is not None:
            identifier = api_saisie_read_pb2.IdentifierPerson(index=index)
        else:
            identifier = api_saisie_read_pb2.IdentifierPerson(n=n, p=p, oc=oc)
        params = api_saisie_read_pb2.GraphTreeParams(
            identifier_person=identifier, nb_asc=nb_asc, nb_desc=nb_desc
        )
        return self._call("graph_v2", params, api_saisie_read_pb2.GraphTree)

    def get_person(self, index: int) -> api_saisie_read_pb2.Person:
        """Full detail for one individual: events, notes, sources, families."""
        params = api_saisie_read_pb2.IndexPerson(index=index)
        return self._call("person", params, api_saisie_read_pb2.Person)
