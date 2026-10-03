import json
from pathlib import Path

import pytest

from jeflink.common.search import match, normalize

VECTORS = json.loads((Path(__file__).parent / "search_vectors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(("text", "expected"), VECTORS["normalize"])
def test_normalize(text, expected):
    assert normalize(text) == expected


@pytest.mark.parametrize("case", VECTORS["match"], ids=lambda c: c["query"])
def test_match(case):
    assert match(case["query"], case["terms"]) == case["rank"]
