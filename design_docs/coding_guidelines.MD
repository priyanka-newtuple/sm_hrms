# Coding Guidelines

**Last Updated:** 31 December 2025  
**Based on:** Clean Code principles by Robert C. Martin

---

## General Principles

- **Readable code is paramount**  
  Prioritize clarity. Write code so that someone else (or your future self) can understand it quickly.

- **Write code for humans, not just computers**  
  Choose names, structure, and comments with readers in mind.

- **Avoid duplication**  
  DRY (Don't Repeat Yourself) keeps code concise and maintainable.

---

## Functions

- **Use descriptive, intention-revealing names**  
  E.g., `get_entity_by_id()`, `send_notification()`

- **Functions should do one thing, and do it well**  
  Split complex logic into smaller helper functions if necessary.

- **Favor short functions**  
  Most functions should comfortably fit on one screen (ideally 10–20 lines).

- **Limit parameters per function**  
  Prefer 1–2 parameters. If more are needed, consider using a data class or dictionary for clarity.

- **Document function purpose**  
  Every public function should have a docstring explaining _what_ it does and _why_ if not obvious.

- **Handle errors explicitly**  
  Use clear error handling and meaningful exception messages.

---

## Comments & Docstrings

- **Prefer self-explanatory code**  
  Use comments to explain _why_ something is done, not _what_ is done (which should be clear from the code).

- **Use docstrings for all modules, classes, and public functions**

- **Update comments and docstrings when code changes**  
  Outdated comments are worse than none.

---

## Code Structure

- **Separation of Concerns**  
  Keep data models, business logic, and I/O (e.g., API routes, DB access) in separate modules.

- **Single Responsibility Principle**  
  Each class and function should have one, and only one, reason to change.

- **Organize imports and dependencies cleanly**  
  Group standard library, third-party, and local imports separately.

---

## Style

- **Follow [PEP 8](https://peps.python.org/pep-0008/) for Python code**  
  Consistent formatting improves readability and reduces noise in code reviews.

- **Use type hints for all function signatures**  
  Improves code comprehension and helps with static analysis.

- **Avoid magic numbers and strings**  
  Use named constants.

---

## Testing

- **Write tests for all business logic**  
  Test both expected and edge cases.

- **Write clear, intention-revealing test names**  
  E.g., `test_invalid_transition_returns_400()`

- **Keep tests small and independent**  
  Each test should verify one thing.

---

## Example

```python
def update_entity_state(entity_id: int, new_state: str) -> bool:
    """
    Update the state of an entity.

    Args:
        entity_id: Unique identifier for the entity.
        new_state: The state to transition the entity to.

    Returns:
        True if update was successful, False otherwise.
    """
    # Fetch entity, validate state, and update in DB
    ...

```

---

Following these guidelines will help keep our codebase clean, maintainable, and welcoming for all contributors.

