"""Core diff logic: compare two OpenAPI 3.x specs and report breaking changes.

A breaking change is anything that can break an existing API client:
removed paths or operations, removed or newly-required parameters,
narrowed enums, changed types, or newly-required request bodies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class BreakingChange:
    kind: str
    location: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.kind}] {self.location}: {self.detail}"


def load_spec(path: str) -> dict:
    """Load an OpenAPI spec from a JSON or YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if path.endswith(".json"):
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to read YAML specs (pip install pyyaml)"
        ) from exc
    return yaml.safe_load(text)


_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")


def _params_by_key(operation: dict) -> dict:
    params = {}
    for p in operation.get("parameters") or []:
        params[(p.get("name"), p.get("in"))] = p
    return params


def _schema_type(schema: dict) -> str:
    return (schema or {}).get("type", "any")


def diff_specs(old: dict, new: dict) -> list[BreakingChange]:
    """Return the list of breaking changes going from old spec to new spec."""
    changes: list[BreakingChange] = []
    old_paths = old.get("paths") or {}
    new_paths = new.get("paths") or {}
    for path, old_item in old_paths.items():
        new_item = new_paths.get(path)
        if new_item is None:
            changes.append(
                BreakingChange("removed-path", path, "entire path was removed")
            )
            continue
        for method in _METHODS:
            old_op = (old_item or {}).get(method)
            if old_op is None:
                continue
            new_op = (new_item or {}).get(method)
            label = f"{method.upper()} {path}"
            if new_op is None:
                changes.append(
                    BreakingChange("removed-operation", label, "operation was removed")
                )
                continue
            changes.extend(_diff_parameters(label, old_op, new_op))
            changes.extend(_diff_request_body(label, old_op, new_op))
    return changes


def _diff_parameters(
    label: str, old_op: dict, new_op: dict
) -> list[BreakingChange]:
    changes: list[BreakingChange] = []
    old_params = _params_by_key(old_op)
    new_params = _params_by_key(new_op)
    for key, old_p in old_params.items():
        name, where = key
        loc = f"{label} param '{name}' in {where}"
        new_p = new_params.get(key)
        if new_p is None:
            if old_p.get("required"):
                changes.append(
                    BreakingChange(
                        "removed-required-param", loc, "required parameter was removed"
                    )
                )
            continue
        if new_p.get("required") and not old_p.get("required"):
            changes.append(
                BreakingChange(
                    "param-became-required",
                    loc,
                    "optional parameter became required",
                )
            )
        old_type = _schema_type(old_p.get("schema"))
        new_type = _schema_type(new_p.get("schema"))
        if old_type != new_type:
            changes.append(
                BreakingChange(
                    "param-type-changed",
                    loc,
                    f"type changed from {old_type} to {new_type}",
                )
            )
        old_enum = set((old_p.get("schema") or {}).get("enum") or [])
        new_enum = set((new_p.get("schema") or {}).get("enum") or [])
        removed_values = sorted(old_enum - new_enum)
        if old_enum and removed_values:
            changes.append(
                BreakingChange(
                    "enum-values-removed",
                    loc,
                    f"enum values removed: {', '.join(map(str, removed_values))}",
                )
            )
    return changes


def _required_props(schema: dict) -> set[str]:
    return set((schema or {}).get("required") or [])


def _diff_request_body(
    label: str, old_op: dict, new_op: dict
) -> list[BreakingChange]:
    changes: list[BreakingChange] = []
    old_body = old_op.get("requestBody") or {}
    new_body = new_op.get("requestBody") or {}
    if not old_body.get("required") and new_body.get("required"):
        changes.append(
            BreakingChange(
                "request-body-became-required",
                label,
                "request body became required",
            )
        )
    if old_body and new_body:
        old_schema = _first_schema(old_body)
        new_schema = _first_schema(new_body)
        removed = sorted(_required_props(old_schema) - _required_props(new_schema))
        if removed:
            changes.append(
                BreakingChange(
                    "required-body-props-removed",
                    label,
                    f"required body properties removed: {', '.join(removed)}",
                )
            )
    return changes


def _first_schema(body: dict) -> dict:
    content = body.get("content") or {}
    for media in content.values():
        schema = (media or {}).get("schema")
        if schema:
            return schema
    return {}
