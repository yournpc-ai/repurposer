"""Schema-directed wire tolerance and error locations; no business writes."""
from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any

_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


def _ref(node: dict, root: dict) -> dict:
    if not isinstance(node, dict):
        return {}
    seen = set()
    while isinstance(node.get("$ref"), str) and node["$ref"].startswith("#/"):
        reference = node["$ref"]
        if reference in seen:
            break
        seen.add(reference)
        resolved: Any = root
        for part in reference[2:].split("/"):
            resolved = resolved.get(part.replace("~1", "/").replace("~0", "~"), {})
        node = resolved
    return node


def _branch(node: dict, value: Any, root: dict) -> dict:
    node = _ref(node, root)
    discriminator = node.get("discriminator", {})
    if isinstance(value, dict) and discriminator:
        reference = discriminator.get("mapping", {}).get(str(value.get(discriminator.get("propertyName"))))
        if reference:
            return _ref({"$ref": reference}, root)
    branches = [_ref(branch, root) for branch in node.get("anyOf", node.get("oneOf", []))]
    if not branches:
        return node
    expected = "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "string" if isinstance(value, str) else "null" if value is None else None
    matches = [branch for branch in branches if branch.get("type") == expected]
    if len(matches) == 1:
        return _branch(matches[0], value, root)
    if isinstance(value, str) and not matches:
        numeric = [branch for branch in branches if branch.get("type") in ("integer", "number")]
        if len(numeric) == 1:
            return numeric[0]
    return node  # Ambiguous unions are left to the existing validator.


def normalize_numeric_arguments(value: Any, schema: dict) -> tuple[Any, list[dict]]:
    """Convert finite numeric strings only at explicitly numeric schema nodes.

    String branches win when a union accepts strings. No rounding, clamping,
    bool conversion, source-copy rewriting or missing-field synthesis.
    """
    changes = []
    def visit(item, node, path):
        node = _branch(node, item, schema)
        if isinstance(item, dict):
            properties = node.get("properties", {})
            extra = node.get("additionalProperties")
            return {key: visit(child, properties.get(key, extra if isinstance(extra, dict) else {}), [*path, key]) for key, child in item.items()}
        if isinstance(item, list):
            prefix = node.get("prefixItems", [])
            return [visit(child, prefix[index] if index < len(prefix) else node.get("items", {}), [*path, index]) for index, child in enumerate(item)]
        if isinstance(item, str) and node.get("type") in ("integer", "number"):
            text = item.strip()
            if len(text) > 128 or not _NUMBER.fullmatch(text):
                return item
            try:
                number = Decimal(text)
                if not number.is_finite() or abs(number.adjusted()) > 308:
                    return item
                if node["type"] == "integer":
                    if number != number.to_integral_value():
                        return item
                    converted = int(number)
                else:
                    converted = float(number)
                    if not math.isfinite(converted):
                        return item
            except (InvalidOperation, ValueError, OverflowError):
                return item
            changes.append({"path": path, "before": item, "after": converted})
            return converted
        return item
    return visit(value, schema, []), changes


def resolve_error_path(value: Any, location: list | tuple, schema: dict | None = None) -> tuple:
    """Consume discriminator tags as schema branches, never as JSON fields."""
    root = schema or {}
    node = root
    cursor = value
    path = []
    skipped = set()
    for index, key in enumerate(location):
        node = _ref(node, root)
        discriminator = node.get("discriminator", {})
        mapping = discriminator.get("mapping", {})
        if key in mapping:
            node = _ref({"$ref": mapping[key]}, root)
            continue
        # Legacy callers without schema can still recognize an explicit
        # op/kind tag once at a node, including a same-named real text field.
        marker = (tuple(path), key)
        if not schema and isinstance(cursor, dict) and index < len(location) - 1 and key in (cursor.get("op"), cursor.get("kind")) and marker not in skipped:
            skipped.add(marker)
            continue
        node = _branch(node, cursor, root)
        if isinstance(cursor, dict) and key in cursor:
            node = node.get("properties", {}).get(key, {})
            cursor = cursor[key]
            path.append(key)
        elif isinstance(cursor, list) and isinstance(key, int) and 0 <= key < len(cursor):
            prefix = node.get("prefixItems", [])
            node = prefix[key] if key < len(prefix) else node.get("items", {})
            cursor = cursor[key]
            path.append(key)
        elif index == len(location) - 1:
            path.append(key)  # A missing/extra leaf belongs to this object.
        elif schema:
            break  # Unknown union branch: repair this subtree, never guess.
    return tuple(path)


def schema_at_path(value: Any, path: list | tuple, schema: dict | None = None) -> dict:
    """Resolve a real JSON path to its schema, consuming union branches.

    Unlike a Pydantic ``loc``, ``path`` never contains discriminator labels.
    Missing leaf fields still resolve from their parent's declared properties.
    """
    root = schema or {}
    node = root
    cursor = value
    for key in path:
        node = _branch(_ref(node, root), cursor, root)
        if isinstance(cursor, dict):
            node = node.get("properties", {}).get(key, {})
            cursor = cursor.get(key)
        elif isinstance(cursor, list) and isinstance(key, int) and 0 <= key < len(cursor):
            prefix = node.get("prefixItems", [])
            node = prefix[key] if key < len(prefix) else node.get("items", {})
            cursor = cursor[key]
        else:
            return {}
    return _branch(_ref(node, root), cursor, root)


def numeric_string_changes(before: Any, after: Any, path=()) -> list[dict]:
    """Audit numeric casts made by property-aware typed model validators."""
    if isinstance(before, dict) and isinstance(after, dict):
        return [change for key in before.keys() & after.keys()
                for change in numeric_string_changes(before[key], after[key], (*path, key))]
    if isinstance(before, list) and isinstance(after, (list, tuple)) and len(before) == len(after):
        return [change for index, (a, b) in enumerate(zip(before, after))
                for change in numeric_string_changes(a, b, (*path, index))]
    if isinstance(before, str) and type(after) in (int, float):
        return [{"path": list(path), "before": before, "after": after}]
    return []
