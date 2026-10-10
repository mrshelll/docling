"""Detect VLM answers that cannot be a page's content.

A vision model can answer with nothing at all, or fall into a repetition loop and emit
the same line hundreds of times. Neither is an error the runtime reports: generation
finishes normally and the pipeline assembles an empty or nonsensical document.
"""

import re

__all__ = ["looks_degenerate"]

# Below this many words the answer is too short to judge: a heading or a table cell is
# legitimately short and repetitive.
_MIN_WORDS = 100

# A page of real text reuses words, but not to this extent. The loop measured on
# granite-docling emitted 2380 words with 7 distinct ones — a ratio of 0.003.
_MIN_DISTINCT_RATIO = 0.05


def looks_degenerate(text: str) -> bool:
    """Whether the answer is empty or so repetitive it cannot be a page's content."""
    if not text.strip():
        return True

    words = re.findall(r"\w+", text.lower())
    if len(words) < _MIN_WORDS:
        return False
    return len(set(words)) / len(words) < _MIN_DISTINCT_RATIO
