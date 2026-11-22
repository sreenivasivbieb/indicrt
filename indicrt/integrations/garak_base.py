"""Shared base for the indic.* garak detectors.

Kept outside garak's package so garak doesn't list it as a runnable detector.
Imported only from inside a garak environment.
"""

from garak.detectors.base import Detector


def attempt_lang(attempt):
    lang = getattr(attempt, "lang", None)
    return None if lang in (None, "*", "") else lang


class IndicDetector(Detector):
    lang_spec = "*"
    doc_uri = "https://github.com/ppattnayak/indicsafe"
    tags = ["avid-effect:security:S0403"]
    active = False

    def _score(self, text, lang):
        raise NotImplementedError

    def detect(self, attempt):
        lang = attempt_lang(attempt)
        out = []
        for o in attempt.outputs_for(self.lang_spec):
            if o is None or getattr(o, "text", None) is None:
                out.append(None)
            else:
                out.append(self._score(o.text, lang))
        return out
