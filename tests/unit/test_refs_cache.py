"""The linker cache — the seam that makes fixtures possible (A-L.6).

Everything here runs offline. That is the point being tested: a read-only
cache over a fixture directory must serve recorded answers and **never** reach
for a process, which is what lets the linked goldens compare on a checkout
with no binary.
"""

from __future__ import annotations

import json

from lexml_nonstat.refs import DEFAULT_CONTEXT_URN, LinkerCache, Reference, cache_key

_REFS = (
    Reference(2, 23, "urn:lex:br:federal:lei:1988-12-22;7713", "Lei nº 7.713, de 1988"),
    Reference(28, 55, "urn:lex:br:federal:decreto.lei:1967;200", "Decreto-lei nº 200"),
)


def test_put_then_get_round_trips(tmp_path):
    """T-K1 — what was recorded is what comes back."""
    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "texto")
    cache.put(key, _REFS)

    assert cache.get(key) == _REFS


def test_a_miss_is_none_and_counts(tmp_path):
    """T-K1 — and a miss is `None`, which is not `()`."""
    cache = LinkerCache(tmp_path)
    assert cache.get(cache_key(DEFAULT_CONTEXT_URN, "nunca perguntado")) is None
    assert cache.misses == 1
    assert cache.hits == 0


def test_a_recorded_empty_answer_is_a_hit_not_a_miss(tmp_path):
    """`()` and `None` are different answers, deliberately.

    A recorded "this paragraph cites nothing" must be served from the cache —
    otherwise every uncited paragraph in the corpus would look like an unasked
    question and a fixtures-only run would appear to need a binary.
    """
    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "Sem citação.")
    cache.put(key, ())

    assert cache.get(key) == ()
    assert cache.hits == 1
    assert cache.misses == 0


def test_read_only_never_writes(tmp_path):
    """T-K2 — a fixture directory must not grow a file because a test asked.

    That would turn a missing fixture into a silent live subprocess on the next
    run, and the recorded corpus would stop being reviewable.
    """
    cache = LinkerCache(tmp_path, read_only=True)
    key = cache_key(DEFAULT_CONTEXT_URN, "texto")
    cache.put(key, _REFS)

    assert not cache.path_for(key).exists()
    assert list(tmp_path.iterdir()) == []


def test_a_corrupt_entry_is_a_miss_not_a_crash(tmp_path):
    """T-K3 — never a hard failure over a cache file."""
    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "texto")
    cache.directory.mkdir(parents=True, exist_ok=True)
    cache.path_for(key).write_text("{not json", encoding="utf-8")

    assert cache.get(key) is None
    assert cache.misses == 1


def test_a_malformed_references_field_is_empty_not_a_crash(tmp_path):
    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "texto")
    cache.directory.mkdir(parents=True, exist_ok=True)
    cache.path_for(key).write_text(
        json.dumps({"references": "not a list"}), encoding="utf-8"
    )

    assert cache.get(key) == ()


def test_the_key_covers_the_context_and_the_text(tmp_path):
    """T-K4 — everything that could change the answer is in the key."""
    a = cache_key(DEFAULT_CONTEXT_URN, "texto")
    b = cache_key(DEFAULT_CONTEXT_URN, "outro texto")
    c = cache_key("urn:lex:br:federal:decreto:2000-01-01;1", "texto")

    assert len({a, b, c}) == 3


def test_the_key_is_stable_and_filesystem_safe():
    """T-K4 — a key computed in another process must find the same file."""
    key = cache_key(DEFAULT_CONTEXT_URN, "A Lei nº 7.713, de 1988 — § 2º")
    assert key == cache_key(DEFAULT_CONTEXT_URN, "A Lei nº 7.713, de 1988 — § 2º")
    assert len(key) == 32
    assert key.isalnum() and key.islower()


def test_the_separator_prevents_a_split_collision():
    """`\\x1f` joins the parts, so two different splits cannot collide."""
    assert cache_key("ab", "c") != cache_key("a", "bc")


def test_meta_is_recorded_beside_the_answer(tmp_path):
    """The recorder stores the source text, which `--check` reads back."""
    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "texto")
    cache.put(key, _REFS, meta={"text": "texto", "sample": "x.docx"})

    payload = json.loads(cache.path_for(key).read_text(encoding="utf-8"))
    assert payload["meta"]["text"] == "texto"
    assert cache.entry_text(key) == "texto"


def test_entry_text_is_none_for_a_missing_or_metaless_entry(tmp_path):
    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "texto")
    assert cache.entry_text(key) is None

    cache.put(key, _REFS)
    assert cache.entry_text(key) is None


def test_fixtures_are_written_as_reviewable_json(tmp_path):
    """A fixture diff has to be readable — it is the reviewed artifact (§9.3)."""
    cache = LinkerCache(tmp_path)
    key = cache_key(DEFAULT_CONTEXT_URN, "texto")
    cache.put(key, _REFS)

    raw = cache.path_for(key).read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert "\n" in raw.strip(), "indent=2, so a diff shows one field per line"
    assert "Lei nº 7.713" in raw, "ensure_ascii=False keeps Portuguese readable"
