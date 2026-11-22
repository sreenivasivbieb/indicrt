# Contributing to indicrt

## Most wanted: refusal phrases from native speakers

The keyword judge recognises refusals using short phrases in
[`indicrt/judges/lexicon.py`](indicrt/judges/lexicon.py). Every phrase a native
speaker adds makes results more accurate for that language.

A good marker:
- is how a model would say *sorry / I can't / I'm unable / not possible* in your language
- is short (2–5 words) and **unlikely to appear in a normal answer**
- includes common spelling variants (e.g. `माफ़` and `माफ`)

Please add a test in `tests/test_core.py` (`test_refusals_detected`) with a real
refusal sentence, and a normal sentence that must *not* match.

## Other useful contributions

- **Urdu romanization** (Perso-Arabic → Roman Urdu) for the `romanized` transform
- **More languages**: Assamese, Sindhi, Konkani, Maithili, Santali ...
- **New datasets** with permissive licenses: add a module in `indicrt/sources/`
  that yields `Probe` objects, pin it to a commit, and document the license
- **Judge validation**: hand-label a few hundred replies and report keyword vs LLM judge agreement

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

Test fixtures must be synthetic and harmless. Never commit benchmark prompts or model
outputs to this repository; datasets are fetched at runtime from their sources.
