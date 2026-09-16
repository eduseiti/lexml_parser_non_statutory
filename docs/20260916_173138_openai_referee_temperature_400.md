# OpenAI referee: `400 Bad Request` on every call

## Symptom

With `.env` pointing the API referee at OpenAI

```
LEXML_REFEREE_BASE_URL=https://api.openai.com/v1
LEXML_REFEREE_MODEL=gpt-5.6-luna
```

every flagged decision was logged as

```
REFEREE ABSTAINED: HTTPStatusError: Client error '400 Bad Request' for url 'https://api.openai.com/v1/chat/completions'
```

so the referee never ran: every decision kept its rule verdict.

## Investigation

The abstention text came from `httpx.Response.raise_for_status()`, which
reports only the status and URL. The reason for the rejection is in the
response body, which was being dropped. Sending one request by hand with the
same payload `CachedAPIReferee` builds showed the body:

```json
{
  "error": {
    "message": "Unsupported value: 'temperature' does not support 0.0 with this model. Only the default (1) value is supported.",
    "type": "invalid_request_error",
    "param": "temperature",
    "code": "unsupported_value"
  }
}
```

The same request **without** `temperature` returned `200` and a well-formed
verdict (`{"verdict":"secao","confidence":0.99,…}`). `response_format:
json_object` and the prompts were fine.

**Root cause.** `referee/api.py` always sends `temperature: 0.0` (the
determinism requirement, invariant #4). OpenAI's reasoning models (`gpt-5.x`,
`o`-series) accept only the default temperature and reject any other value
with a 400. DeepSeek, Z.AI, Qwen and Kimi accept `0`, which is why the problem
only showed up with OpenAI.

## Fix

`src/lexml_nonstat/referee/api.py`:

1. **Error body in the abstention.** The default transport now raises
   `TransportHTTPError(status_code, body, url)` on any non-2xx response,
   instead of `httpx.HTTPStatusError`. Its message includes the first 300
   characters of the provider's body, so an abstention now states the cause.
   The class lives in `api.py` and is exported from `lexml_nonstat.referee`,
   so `httpx` is still imported only lazily (`test_httpx_is_not_imported`
   still passes).
2. **Automatic temperature fallback.** The first request still sends
   `temperature: 0`, so providers that accept it stay deterministic even on a
   cache miss. If the transport raises a `TransportHTTPError` with status 400
   and a body that mentions `temperature`, the referee:
   - sets `self.send_temperature = False`,
   - retries the same request once without `temperature`, and
   - leaves `temperature` out of every later request from that instance, so
     each later question costs one request instead of two.

   Any other 400 (bad model, bad key, …) still abstains as before, now with
   the provider's message.

The broad catch in `_call` is unchanged, so the fail-safe guarantee (§7.3
constraint 5) still holds: if the retry fails, the referee abstains.

### Determinism trade-off

For a model that rejects `temperature`, a cache **miss** is sampled at the
provider's default temperature, so two cold runs can differ. Invariant #4
("same input + same referee cache ⇒ byte-identical output") still holds: the
answer is cached on the first call and replayed after that. The cache key
already includes the model name, so answers from different models never mix.
For reproducible published results, record a cache once and reuse it, or use a
provider that accepts `temperature: 0`.

## Tests

`tests/unit/test_referee_api.py`:

- `test_a_model_that_rejects_temperature_is_retried_without_it` — a transport
  that returns OpenAI's exact 400 whenever `temperature` is present. Checks:
  the first request includes `temperature`; the retry and the next question
  omit it; the question is answered and not abstained; `calls` goes 2 → 3.
- `test_other_400s_still_abstain_and_name_the_provider_reason` — an unrelated
  400 abstains, the provider's message appears in the rationale, no retry is
  made, and `send_temperature` stays `True`.

The existing `test_payload_is_deterministic_and_json_constrained` is unchanged
and still passes: the default first request still carries `temperature: 0`.

Results: `tests/unit/test_referee_api.py` 83 passed. Full suite: 6186 passed,
4 skipped, 4 failed. All 4 failures also fail on the unmodified tree
(`git stash`), so this change did not cause them:

- `test_flatness_causes.py::test_the_corpus_flat_count`
- `test_flatness_causes.py::test_the_corpus_cause_partition`
- `test_flatness_causes.py::test_truncation_is_visible_in_span_coverage`
- `test_referee_economics.py::test_the_referee_now_moves_flatness_86_to_83`

**Live check** against `gpt-5.6-luna` through `CachedAPIReferee` with the real
`httpx` transport:

| call | verdict | cumulative requests |
|---|---|---|
| `is_heading("1. INTRODUÇÃO", …)` | `secao` (0.99) | 2 (rejected + retry) |
| `is_own_articulation("Art. 2º Fica instituído…", "Lei nº 7.713, de 1988 -")` | `own` (0.99) | 3 |

## Notes

- `.env.example` already lists OpenAI as a preset; no configuration change is
  needed.
- The recorded fixtures (`tests/referee_fixtures/`,
  `tests/corpus_referee_fixtures/`) are keyed by model and are unaffected.
