"""Pure-function tests for common.identifier_template (spec §3, §12 rows 3-18, 32-33)."""

from __future__ import annotations

from common.identifier_template import (
    IDENTIFIER_MAX_BASE_LENGTH,
    format_seq,
    has_seq_token,
    next_suffixed,
    parse_tokens,
    prefix_context,
    render_identifier,
)


class TestParseTokens:
    def test_basic(self):
        assert parse_tokens("{{first_name}}-{{last_name}}") == ["first_name", "last_name"]

    def test_whitespace_and_case_normalized(self):
        assert parse_tokens("{{ First_Name }}") == ["first_name"]

    def test_malformed_braces_not_tokens(self):
        assert parse_tokens("{{first_name}") == []

    def test_duplicates_preserved(self):
        assert parse_tokens("{{a}}-{{a}}") == ["a", "a"]

    def test_seq_detection(self):
        assert has_seq_token("INV-{{seq}}") is True
        assert has_seq_token("INV-{{ SEQ }}") is True
        assert has_seq_token("{{sequence}}") is False


class TestRender:
    def test_simple(self):
        assert render_identifier(
            "{{first_name}}-{{last_name}}",
            {"first_name": "John", "last_name": "Smith"},
        ) == "John-Smith"

    def test_value_preserved_verbatim(self):
        assert (
            render_identifier(
                "{{client_name}}-499Q-{{seq}}",
                {"client_name": "Delta Telecom USA Inc"},
                seq_value="0001",
            )
            == "Delta Telecom USA Inc-499Q-0001"
        )

    def test_blank_segment_skipped_and_collapsed(self):
        assert render_identifier(
            "{{first_name}}-{{employee_number}}",
            {"first_name": "John", "employee_number": ""},
        ) == "John"

    def test_literals_pass_verbatim(self):
        assert render_identifier("PRJ-{{dept}}", {"dept": "Sales"}) == "PRJ-Sales"

    def test_all_blank_with_literals(self):
        assert render_identifier("CAND-{{x}}", {"x": ""}) == "CAND"

    def test_all_blank_no_literals_empty(self):
        assert render_identifier("{{x}}-{{y}}", {}) == ""

    def test_lists_and_dicts_blank(self):
        assert render_identifier("{{x}}", {"x": ["a", "b"]}) == ""
        assert render_identifier("{{x}}", {"x": {"a": 1}}) == ""

    def test_seq_substitution_all_occurrences_same(self):
        assert render_identifier("{{seq}}-x-{{seq}}", {}, seq_value="0007") == "0007-x-0007"

    def test_value_containing_token_syntax_not_reinterpreted(self):
        out = render_identifier("{{name}}-{{seq}}", {"name": "a{{seq}}b"}, seq_value="0001")
        assert out == "a{{seq}}b-0001"

    def test_missing_field_blank(self):
        assert render_identifier("{{ghost}}-{{name}}", {"name": "Ann"}) == "Ann"

    def test_truncation_at_120(self):
        out = render_identifier("{{a}}", {"a": "x" * 300})
        assert len(out) == IDENTIFIER_MAX_BASE_LENGTH

    def test_malformed_braces_kept_literal(self):
        assert render_identifier("{{first_name}", {"first_name": "John"}) == "{{first_name}"


class TestPrefixContext:
    def test_seq_slot_removed(self):
        assert prefix_context("{{client_name}}-{{seq}}", {"client_name": "Acme"}) == "Acme"

    def test_constant_prefix(self):
        assert prefix_context("INV-{{seq}}", {}) == "INV"

    def test_no_seq_equals_render(self):
        assert prefix_context("{{a}}-{{b}}", {"a": "x", "b": "y"}) == "x-y"


class TestSeqAndSuffix:
    def test_format_seq_pads_and_overflows(self):
        assert format_seq(7) == "0007"
        assert format_seq(10000) == "10000"

    def test_no_collision_returns_base(self):
        assert next_suffixed("john-smith", set()) == "john-smith"

    def test_collision_suffixes(self):
        assert next_suffixed("john-smith", {"john-smith"}) == "john-smith_2"
        assert next_suffixed("john-smith", {"john-smith", "john-smith_2"}) == "john-smith_3"

    def test_manual_gap_skips_to_max_plus_one(self):
        assert next_suffixed("j", {"j", "j_2", "j_7"}) == "j_8"

    def test_unrelated_suffixes_ignored(self):
        assert next_suffixed("j", {"j", "jx_2", "j_x"}) == "j_2"
