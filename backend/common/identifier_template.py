"""Identifier-template rendering (spec: design_docs/configurable_entity_identifier_spec_15Jul2026.MD §3).

Pure functions only — no DB, no I/O. The DB-side orchestration lives in
entities/db_models.py.
"""

from __future__ import annotations

import re

IDENTIFIER_MAX_BASE_LENGTH = 120
SEQ_TOKEN = "seq"
SEQ_COUNTER_KEY_PREFIX = "__idseq__:"
SEQ_PAD_WIDTH = 4

TOKEN_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
_SEPARATOR_RUN_RE = re.compile(r"[-_]{2,}")
_SUFFIX_RE_TEMPLATE = r"_(\d+)$"


def parse_tokens(template: str) -> list[str]:
    """Lowercased token ids in template order, duplicates preserved."""
    return [m.group(1).lower() for m in TOKEN_RE.finditer(template or "")]


def has_seq_token(template: str) -> bool:
    return SEQ_TOKEN in parse_tokens(template)


def _raw_value(value: object) -> str:
    """Verbatim string value for a token; blank for None/list/dict/set/tuple."""
    if value is None or isinstance(value, (list, dict, set, tuple)):
        return ""
    return str(value)


def _substitute(template: str, values: dict, seq_value: str | None) -> str:
    def _one(match: re.Match) -> str:
        token = match.group(1).lower()
        if token == SEQ_TOKEN:
            return seq_value if seq_value is not None else ""
        return _raw_value(values.get(token))

    return TOKEN_RE.sub(_one, template or "")


def _collapse(rendered: str) -> str:
    collapsed = _SEPARATOR_RUN_RE.sub(lambda m: m.group(0)[0], rendered)
    return collapsed.strip("-_")


def render_identifier(template: str, values: dict, seq_value: str | None = None) -> str:
    """Full assembly: substitute → collapse separators → trim → truncate.

    Returns "" when everything renders blank — the DB layer applies the
    counter fallback (spec §3 assembly step 5)."""
    base = _collapse(_substitute(template, values, seq_value))
    return base[:IDENTIFIER_MAX_BASE_LENGTH]


def prefix_context(template: str, values: dict) -> str:
    """Rendered base with seq slots removed — the counter scope key (spec §3)."""
    return render_identifier(template, values, seq_value="")


def format_seq(counter: int) -> str:
    return str(counter).zfill(SEQ_PAD_WIDTH)


def next_suffixed(base: str, existing: set[str]) -> str:
    """Smallest free `base`/`base_<n>` given the set of taken identifiers."""
    if base not in existing:
        return base
    suffix_re = re.compile(re.escape(base) + _SUFFIX_RE_TEMPLATE)
    taken = [int(m.group(1)) for value in existing for m in [suffix_re.fullmatch(value)] if m]
    return f"{base}_{max(taken, default=1) + 1}"
