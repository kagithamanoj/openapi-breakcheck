"""Core diff logic: compare two OpenAPI 3.x specs and report breaking changes.

A breaking change is anything that can break an existing API client:
removed paths or operations, removed or newly-required parameters,
narrowed enums, changed types, removed or newly-required request bodies, or
removed or narrowed responses.
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

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "location": self.location,
            "detail": self.detail,
        }


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


def _params_by_key(container: dict) -> dict:
    params = {}
    for p in container.get("parameters") or []:
        params[(p.get("name"), p.get("in"))] = p
    return params


def _effective_params(item: dict, operation: dict) -> dict:
    """Merge path-item parameters with operation parameters.

    Parameters defined on the path item apply to every operation on that
    path; an operation parameter with the same name and location overrides
    the path-item one, per the OpenAPI spec.
    """
    params = _params_by_key(item)
    params.update(_params_by_key(operation))
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
            changes.extend(
                _diff_parameters(
                    label,
                    _effective_params(old_item, old_op),
                    _effective_params(new_item, new_op),
                )
            )
            changes.extend(_diff_request_body(label, old_op, new_op))
            changes.extend(_diff_responses(label, old_op, new_op))
    return changes


def _diff_parameters(
    label: str, old_params: dict, new_params: dict
) -> list[BreakingChange]:
    changes: list[BreakingChange] = []
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
        changes.extend(
            _diff_param_items(loc, old_p.get("schema"), new_p.get("schema"))
        )
    for key, new_p in new_params.items():
        if key in old_params:
            continue
        if new_p.get("required"):
            name, where = key
            changes.append(
                BreakingChange(
                    "added-required-param",
                    f"{label} param '{name}' in {where}",
                    "new required parameter was added",
                )
            )
    return changes


def _diff_param_items(loc: str, old_schema: dict, new_schema: dict) -> list:
    """Flag type changes and enum narrowing inside array `items` schemas.

    A parameter declared as an array of strings becoming an array of
    integers breaks clients the same way a plain type change does, so
    items are diffed recursively, including nested arrays. When either
    side has no items schema there is nothing to compare.
    """
    changes: list[BreakingChange] = []
    old_items = (old_schema or {}).get("items") or {}
    new_items = (new_schema or {}).get("items") or {}
    if not old_items or not new_items:
        return changes
    items_loc = f"{loc} items"
    old_type = _schema_type(old_items)
    new_type = _schema_type(new_items)
    if old_type != new_type:
        changes.append(
            BreakingChange(
                "param-type-changed",
                items_loc,
                f"type changed from {old_type} to {new_type}",
            )
        )
    old_enum = set(old_items.get("enum") or [])
    new_enum = set(new_items.get("enum") or [])
    removed_values = sorted(old_enum - new_enum)
    if old_enum and removed_values:
        changes.append(
            BreakingChange(
                "enum-values-removed",
                items_loc,
                f"enum values removed: {', '.join(map(str, removed_values))}",
            )
        )
    if old_type == new_type:
        changes.extend(_diff_param_items(items_loc, old_items, new_items))
    return changes


def _required_props(schema: dict) -> set[str]:
    return set((schema or {}).get("required") or [])


# Kind names and detail wording for the schema diff, per side. The
# request-body and response checks share the same recursion, but keep their
# own kind names so existing output is unchanged.
_SCHEMA_KINDS = {
    "request-body": {
        "type_changed": "request-body-type-changed",
        "type_detail": "request body type changed from {} to {}",
        "prop_type_changed": "request-body-prop-type-changed",
        "enum_removed": "request-body-enum-values-removed",
        "required_removed": "required-body-props-removed",
        "required_removed_detail": "required body properties removed: {}",
        "became_required": "request-body-prop-became-required",
        "became_required_detail": "request body properties became required: {}",
        "prop_word": "body property",
    },
    "response": {
        "type_changed": "response-type-changed",
        "type_detail": "response type changed from {} to {}",
        "prop_type_changed": "response-prop-type-changed",
        "enum_removed": "response-enum-values-removed",
        "required_removed": "required-response-props-removed",
        "required_removed_detail": "required response properties removed: {}",
        "became_required": None,
        "became_required_detail": None,
        "prop_word": "property",
    },
}


def _check_enum_narrowing(
    changes: list, loc: str, old_schema: dict, new_schema: dict, kinds: dict
) -> None:
    """Flag enum values present in the old schema but missing in the new."""
    old_enum = set((old_schema or {}).get("enum") or [])
    new_enum = set((new_schema or {}).get("enum") or [])
    removed_values = sorted(old_enum - new_enum)
    if old_enum and removed_values:
        changes.append(
            BreakingChange(
                kinds["enum_removed"],
                loc,
                f"enum values removed: {', '.join(map(str, removed_values))}",
            )
        )


def _diff_schema(
    loc: str, old_schema: dict, new_schema: dict, kinds: dict, nested: bool = False
) -> list[BreakingChange]:
    """Diff two object schemas, recursing into nested object properties.

    At the top level this is the schema itself (a request body or a
    response); deeper levels are properties of that schema. Type changes,
    narrowed enums, and required-property changes are flagged at every
    level. Removed optional properties are fine at every level, and a
    property whose type changed is not recursed into.
    """
    changes: list[BreakingChange] = []
    old_type = _schema_type(old_schema)
    new_type = _schema_type(new_schema)
    if old_type != new_type:
        kind = kinds["prop_type_changed"] if nested else kinds["type_changed"]
        detail = (
            "type changed from {} to {}".format(old_type, new_type)
            if nested
            else kinds["type_detail"].format(old_type, new_type)
        )
        changes.append(BreakingChange(kind, loc, detail))
        if not nested:
            return changes
        # A property whose type changed is not recursed into, but its enum
        # is still checked, matching the old top-level behaviour.
        _check_enum_narrowing(changes, loc, old_schema, new_schema, kinds)
        return changes
    if nested:
        _check_enum_narrowing(changes, loc, old_schema, new_schema, kinds)
    removed = sorted(_required_props(old_schema) - _required_props(new_schema))
    if removed:
        changes.append(
            BreakingChange(
                kinds["required_removed"],
                loc,
                kinds["required_removed_detail"].format(", ".join(removed)),
            )
        )
    if kinds["became_required"] is not None:
        newly_required = sorted(
            _required_props(new_schema) - _required_props(old_schema)
        )
        if newly_required:
            changes.append(
                BreakingChange(
                    kinds["became_required"],
                    loc,
                    kinds["became_required_detail"].format(
                        ", ".join(newly_required)
                    ),
                )
            )
    old_items = (old_schema or {}).get("items") or {}
    new_items = (new_schema or {}).get("items") or {}
    if old_items and new_items:
        changes.extend(
            _diff_schema(f"{loc} items", old_items, new_items, kinds, nested=True)
        )
    old_props = (old_schema or {}).get("properties") or {}
    new_props = (new_schema or {}).get("properties") or {}
    prop_word = kinds["prop_word"] if not nested else "property"
    for name, old_prop in old_props.items():
        new_prop = new_props.get(name)
        if new_prop is None:
            continue
        prop_loc = f"{loc} {prop_word} '{name}'"
        changes.extend(
            _diff_schema(prop_loc, old_prop, new_prop, kinds, nested=True)
        )
        # The recursive call above already reports the property's own type
        # change and enum narrowing; nothing else to check here.
    return changes


def _diff_request_body(
    label: str, old_op: dict, new_op: dict
) -> list[BreakingChange]:
    changes: list[BreakingChange] = []
    old_body = old_op.get("requestBody") or {}
    new_body = new_op.get("requestBody") or {}
    if old_body and not new_body:
        changes.append(
            BreakingChange(
                "removed-request-body",
                label,
                "request body was removed",
            )
        )
        return changes
    if not old_body.get("required") and new_body.get("required"):
        changes.append(
            BreakingChange(
                "request-body-became-required",
                label,
                "request body became required",
            )
        )
    old_content = old_body.get("content") or {}
    new_content = new_body.get("content") or {}
    for media in old_content:
        if media not in new_content:
            changes.append(
                BreakingChange(
                    "removed-request-body-media-type",
                    f"{label} request body content '{media}'",
                    f"request body content type '{media}' was removed",
                )
            )
    if old_body and new_body:
        old_schema = _first_schema(old_body)
        new_schema = _first_schema(new_body)
        changes.extend(_diff_request_body_schema(label, old_schema, new_schema))
    return changes


def _diff_request_body_schema(
    loc: str, old_schema: dict, new_schema: dict
) -> list[BreakingChange]:
    return _diff_schema(loc, old_schema, new_schema, _SCHEMA_KINDS["request-body"])


def _first_schema(body: dict) -> dict:
    content = body.get("content") or {}
    for media in content.values():
        schema = (media or {}).get("schema")
        if schema:
            return schema
    return {}


def _diff_responses(
    label: str, old_op: dict, new_op: dict
) -> list[BreakingChange]:
    changes: list[BreakingChange] = []
    old_responses = old_op.get("responses") or {}
    new_responses = new_op.get("responses") or {}
    for status, old_resp in old_responses.items():
        loc = f"{label} response '{status}'"
        new_resp = new_responses.get(status)
        if new_resp is None:
            changes.append(
                BreakingChange("removed-response", loc, "response was removed")
            )
            continue
        old_content = (old_resp or {}).get("content") or {}
        new_content = (new_resp or {}).get("content") or {}
        for media, old_media in old_content.items():
            media_loc = f"{loc} content '{media}'"
            new_media = new_content.get(media)
            if new_media is None:
                changes.append(
                    BreakingChange(
                        "removed-response-media-type",
                        media_loc,
                        f"response content type '{media}' was removed",
                    )
                )
                continue
            changes.extend(
                _diff_response_schema(
                    media_loc,
                    (old_media or {}).get("schema") or {},
                    (new_media or {}).get("schema") or {},
                )
            )
    return changes


def _diff_response_schema(
    loc: str, old_schema: dict, new_schema: dict
) -> list[BreakingChange]:
    return _diff_schema(loc, old_schema, new_schema, _SCHEMA_KINDS["response"])
