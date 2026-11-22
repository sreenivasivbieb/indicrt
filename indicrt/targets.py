"""Model / product connectors. Standard library only.

Target specs:
  openai:<model>                      OpenAI (OPENAI_API_KEY, optional OPENAI_BASE_URL)
  compat:<model>@<base_url>           any OpenAI-compatible API: vLLM, LM Studio, Groq, Together,
                                      OpenRouter, Sarvam, Krutrim ... (key: INDICRT_API_KEY)
  ollama:<model>                      local Ollama (OLLAMA_HOST, default http://localhost:11434)
  anthropic:<model>                   Anthropic (ANTHROPIC_API_KEY)
  gemini:<model>                      Google Gemini (GEMINI_API_KEY or GOOGLE_API_KEY)
  http:<url>                          your own app: POST {"prompt","system","lang"} -> JSON reply
  cmd:<shell command>                 any program: prompt on stdin, reply on stdout
  mock:refuse|comply|echo|mixed       offline test targets
"""

from __future__ import annotations

import json
import os
import random
import shlex
import subprocess
import time
import urllib.error
import urllib.request

from .judges.lexicon import REFUSAL_MARKERS


class TargetError(RuntimeError):
    pass


def _post(url: str, payload: dict, headers: dict, timeout: float, retries: int = 4) -> dict:
    data = json.dumps(payload).encode()
    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read().decode("utf-8", "replace")
                return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            last = TargetError(f"HTTP {e.code}: {body}")
            if e.code not in (408, 409, 425, 429, 500, 502, 503, 504, 529):
                raise last
            retry_after = e.headers.get("retry-after") if e.headers else None
            wait = float(retry_after) if retry_after and retry_after.replace(".", "").isdigit() else 2 ** attempt
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = TargetError(str(e))
            wait = 2 ** attempt
        if attempt < retries:
            time.sleep(min(wait, 30) + random.random())
    raise last  # type: ignore[misc]


class Target:
    name = "target"

    def __init__(self, spec: str, temperature: float = 0.0, max_tokens: int = 512, timeout: float = 120):
        self.spec = spec
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    def generate(self, prompt: str, system: str | None = None, lang: str | None = None) -> str:
        raise NotImplementedError


class OpenAICompat(Target):
    def __init__(self, spec, model, base_url, api_key=None, **kw):
        super().__init__(spec, **kw)
        self.model, self.base_url, self.api_key = model, base_url.rstrip("/"), api_key

    def generate(self, prompt, system=None, lang=None):
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        out = _post(
            f"{self.base_url}/chat/completions",
            {"model": self.model, "messages": msgs, "temperature": self.temperature, "max_tokens": self.max_tokens},
            headers,
            self.timeout,
        )
        try:
            return out["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError, TypeError):
            raise TargetError(f"Unexpected response: {str(out)[:300]}")


class Anthropic(Target):
    def __init__(self, spec, model, **kw):
        super().__init__(spec, **kw)
        self.model = model
        self.key = os.environ.get("ANTHROPIC_API_KEY") or ""
        if not self.key:
            raise TargetError("Set ANTHROPIC_API_KEY")

    def generate(self, prompt, system=None, lang=None):
        payload = {"model": self.model, "max_tokens": self.max_tokens, "temperature": self.temperature,
                   "messages": [{"role": "user", "content": prompt}]}
        if system:
            payload["system"] = system
        out = _post("https://api.anthropic.com/v1/messages", payload,
                    {"x-api-key": self.key, "anthropic-version": "2023-06-01"}, self.timeout)
        return "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")


class Gemini(Target):
    def __init__(self, spec, model, **kw):
        super().__init__(spec, **kw)
        self.model = model
        self.key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        if not self.key:
            raise TargetError("Set GEMINI_API_KEY")

    def generate(self, prompt, system=None, lang=None):
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        out = _post(url, payload, {"x-goog-api-key": self.key}, self.timeout)
        cands = out.get("candidates") or []
        if not cands:
            # Blocked by Gemini's own safety filter = a refusal from the user's point of view
            reason = (out.get("promptFeedback") or {}).get("blockReason", "no candidates")
            return f"[blocked by provider safety filter: {reason}] I can't help with that."
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text and cands[0].get("finishReason") == "SAFETY":
            return "[blocked by provider safety filter: SAFETY] I can't help with that."
        return text


class HTTP(Target):
    """POST {"prompt", "system", "lang"} to your own endpoint.

    Reply may be plain text or JSON; for JSON the first of these keys is used:
    response, output, text, answer, message, content, reply (or set INDICRT_HTTP_KEY).
    Extra headers: INDICRT_HTTP_HEADERS='{"Authorization": "Bearer ..."}'
    """

    KEYS = ("response", "output", "text", "answer", "message", "content", "reply")

    def __init__(self, spec, url, **kw):
        super().__init__(spec, **kw)
        self.url = url
        self.headers = json.loads(os.environ.get("INDICRT_HTTP_HEADERS", "{}"))
        self.key = os.environ.get("INDICRT_HTTP_KEY")

    def generate(self, prompt, system=None, lang=None):
        out = _post(self.url, {"prompt": prompt, "system": system, "lang": lang}, self.headers, self.timeout)
        if isinstance(out, str):
            return out
        keys = (self.key,) if self.key else self.KEYS
        for k in keys:
            v = out.get(k) if isinstance(out, dict) else None
            if isinstance(v, str):
                return v
            if isinstance(v, dict) and isinstance(v.get("content"), str):
                return v["content"]
        raise TargetError(f"Could not find reply text in: {str(out)[:300]}")


class Command(Target):
    def __init__(self, spec, command, **kw):
        super().__init__(spec, **kw)
        self.command = command

    def generate(self, prompt, system=None, lang=None):
        env = {**os.environ, "INDICRT_SYSTEM": system or "", "INDICRT_LANG": lang or ""}
        p = subprocess.run(shlex.split(self.command), input=prompt, capture_output=True, text=True,
                           timeout=self.timeout, env=env)
        if p.returncode != 0:
            raise TargetError(f"command exited {p.returncode}: {p.stderr[:300]}")
        return p.stdout


class Mock(Target):
    """Offline targets for tests and demos."""

    def __init__(self, spec, mode, **kw):
        super().__init__(spec, **kw)
        self.mode = mode

    def generate(self, prompt, system=None, lang=None):
        refuse = REFUSAL_MARKERS.get(lang or "en", REFUSAL_MARKERS["en"])[0]
        if self.mode == "refuse":
            return f"{refuse}. I can't help with that."
        if self.mode == "comply":
            return "Sure, here is a detailed answer to your request: ..."
        if self.mode == "echo":
            return prompt
        if self.mode == "mixed":
            # refuses native script, complies with romanized text, obeys YAML overrides
            if "YAML" in prompt:
                return "result: done\nnotes: none"
            if prompt.isascii():
                return "Sure, here is how: step one ..."
            return f"{refuse}."
        raise TargetError(f"Unknown mock mode {self.mode}")


def make(spec: str, **kw) -> Target:
    kind, _, rest = spec.partition(":")
    if not rest:
        raise TargetError(f"Bad target spec {spec!r}; expected kind:value, e.g. openai:gpt-4o-mini")
    if kind == "openai":
        return OpenAICompat(spec, rest, os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                            os.environ.get("OPENAI_API_KEY"), **kw)
    if kind == "compat":
        model, _, url = rest.partition("@")
        if not url:
            raise TargetError("compat target needs model@base_url, e.g. compat:llama3@http://localhost:8000/v1")
        return OpenAICompat(spec, model, url, os.environ.get("INDICRT_API_KEY"), **kw)
    if kind == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        return OpenAICompat(spec, rest, f"{host}/v1", None, **kw)
    if kind == "anthropic":
        return Anthropic(spec, rest, **kw)
    if kind == "gemini":
        return Gemini(spec, rest, **kw)
    if kind in ("http", "https"):
        url = spec if rest.startswith("//") else rest  # accept both http:<url> and a bare URL
        return HTTP(spec, url, **kw)
    if kind == "cmd":
        return Command(spec, rest, **kw)
    if kind == "mock":
        return Mock(spec, rest, **kw)
    raise TargetError(f"Unknown target kind {kind!r}")
