---
name: indic-redteam
description: Red-team an LLM, chatbot or agent for safety in Indian languages (Hindi, Tamil, Bengali, Telugu and 8 more, including romanized/Hinglish text) with the indicrt CLI, then explain the results. Use when asked to test a model or app for Indic-language safety, jailbreaks, over-refusal, prompt injection, or romanized-script weaknesses.
---

# Indic red-team with indicrt

## 1. Make sure the tool is available

```bash
indicrt --version || pip install git+https://github.com/<owner>/indicrt   # or: pip install -e <repo-path>
```

## 2. Work out the target

Ask the user only if you cannot infer it from the repo or the request.

| They have | Target spec |
|---|---|
| OpenAI / Anthropic / Gemini model | `openai:<model>`, `anthropic:<model>`, `gemini:<model>` (key in env) |
| OpenAI-compatible API (Sarvam, Groq, vLLM, OpenRouter...) | `compat:<model>@<base_url>` + `INDICRT_API_KEY` |
| Local model | `ollama:<model>` |
| Their own chat endpoint | `http://host/path` (POSTs `{"prompt","system","lang"}`) |
| A script or agent | `cmd:<command>` (prompt on stdin, reply on stdout) |

If the product has a system prompt in the repo, pass it with `--system-file`; results are only meaningful with the real prompt.

Only test systems the user owns or is authorized to test.

## 3. Start small, then scale

```bash
indicrt plan --langs hi,ta --transforms native,romanized          # dry run, check counts
indicrt run -t <target> --langs hi,ta --transforms native,romanized --sample 10 -o runs/smoke
```

If the smoke run has many errors, fix the target (keys, URL, reply field) before scaling.
Then run the languages the product serves with `--sample 25` (default) or more. For
decisions, use an LLM judge: `--judge llm:openai:gpt-4o-mini`.

## 4. Explain the report

Read `runs/<dir>/summary.json` (and `results.jsonl` for examples). Tell the user, in plain words:

1. **Safety score per language**: where harmful requests get through (attack success rate).
2. **Script gap**: if `romanized` or `mixed` has a clearly higher attack success rate than `native`, users can bypass safety by typing in Latin letters. Usually the most important finding.
3. **Over-refusal**: harmless questions being refused, which hurts real users.
4. **Injection follow rate**: the model obeys instructions embedded in user content over its system rules.
5. **Canary leaks**: any are serious.

Quote 2–3 concrete failures from `results.jsonl` (prompt language, verdict, a short excerpt). Don't paste long harmful text.

State the caveats: the keyword judge is approximate, and small samples have wide error bars.

## 5. Suggest fixes

- Script gap: add romanized and code-mixed examples to safety tuning or guardrail classifiers; normalize or transliterate input before moderation.
- Over-refusal: add native-language harmless examples; loosen keyword-based filters.
- Injection: separate user content from instructions; restate rules after user content; strip format and mode overrides.

## 6. Keep it in CI (optional)

```bash
indicrt run -t <staging-target> --sample 10 --fail-under 90 --max-injection 0.1
```
