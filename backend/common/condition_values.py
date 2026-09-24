"""Value semantics shared by role-filter validation and evaluation."""

from decimal import Decimal, InvalidOperation

from common.logger import logger

# PostgreSQL NUMERIC precision limits (see PostgreSQL documentation, section 8.1)
PG_NUMERIC_MIN_ADJUSTED_EXPONENT = -16383
PG_NUMERIC_MAX_ADJUSTED_EXPONENT = 131071


def parse_membership_values(raw: str | None) -> frozenset[str]:
    """Comma-separated, case-sensitive values; whitespace and empty entries are ignored."""
    return frozenset(value for part in (raw or "").split(",") if (value := part.strip()))


def parse_membership_numbers(values: frozenset[str]) -> frozenset[Decimal]:
    """Numeric fields compare numerically; text fields still compare exact strings.

    PostgreSQL expands exponent notation in JSONB, so comparing number text would
    disagree with Python for values such as 1e-7. Ignore non-finite/out-of-range
    literals which cannot represent a PostgreSQL JSONB number.
    """
    numbers = set()
    for value in values:
        try:
            number = Decimal(value)
        except InvalidOperation as e:
            logger.debug(
                "Non-numeric value in membership list skipped for numeric parsing: %s (error: %s)",
                value,
                e,
            )
            continue
        if (
            number.is_finite()
            and PG_NUMERIC_MIN_ADJUSTED_EXPONENT <= number.adjusted() <= PG_NUMERIC_MAX_ADJUSTED_EXPONENT
        ):
            numbers.add(number)
    return frozenset(numbers)
