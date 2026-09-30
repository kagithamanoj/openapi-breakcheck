"""Tests for openapi-breakcheck diff detection."""

from breakcheck import diff_specs
from breakcheck.cli import main


def make_op(params=None, request_body=None):
    op = {}
    if params is not None:
        op["parameters"] = params
    if request_body is not None:
        op["requestBody"] = request_body
    return op


def param(name, where="query", required=False, ptype="string", enum=None):
    schema = {"type": ptype}
    if enum is not None:
        schema["enum"] = enum
    return {"name": name, "in": where, "required": required, "schema": schema}


def test_no_changes():
    old = {"paths": {"/users": {"get": make_op([param("limit")])}}}
    new = {"paths": {"/users": {"get": make_op([param("limit")])}}}
    assert diff_specs(old, new) == []


def test_removed_path():
    old = {"paths": {"/users": {"get": {}}, "/gone": {"get": {}}}}
    new = {"paths": {"/users": {"get": {}}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["removed-path"]
    assert changes[0].location == "/gone"


def test_removed_operation():
    old = {"paths": {"/users": {"get": {}, "delete": {}}}}
    new = {"paths": {"/users": {"get": {}}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["removed-operation"]


def test_added_path_is_not_breaking():
    old = {"paths": {"/users": {"get": {}}}}
    new = {"paths": {"/users": {"get": {}}, "/new": {"get": {}}}}
    assert diff_specs(old, new) == []


def test_removed_required_param():
    old = {"paths": {"/u": {"get": make_op([param("id", required=True)])}}}
    new = {"paths": {"/u": {"get": make_op([])}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["removed-required-param"]


def test_removed_optional_param_is_fine():
    old = {"paths": {"/u": {"get": make_op([param("verbose")])}}}
    new = {"paths": {"/u": {"get": make_op([])}}}
    assert diff_specs(old, new) == []


def test_param_became_required():
    old = {"paths": {"/u": {"get": make_op([param("filter")])}}}
    new = {"paths": {"/u": {"get": make_op([param("filter", required=True)])}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["param-became-required"]


def test_param_type_changed():
    old = {"paths": {"/u": {"get": make_op([param("id", ptype="string")])}}}
    new = {"paths": {"/u": {"get": make_op([param("id", ptype="integer")])}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["param-type-changed"]


def test_enum_values_removed():
    old = {"paths": {"/u": {"get": make_op([param("sort", enum=["a", "b"])])}}}
    new = {"paths": {"/u": {"get": make_op([param("sort", enum=["a"])])}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["enum-values-removed"]
    assert "b" in changes[0].detail


def test_request_body_became_required():
    body = lambda required: {
        "required": required,
        "content": {"application/json": {"schema": {"type": "object"}}},
    }
    old = {"paths": {"/u": {"post": make_op(request_body=body(False))}}}
    new = {"paths": {"/u": {"post": make_op(request_body=body(True))}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["request-body-became-required"]


def test_required_body_prop_removed():
    schema = lambda required: {
        "type": "object",
        "required": required,
        "properties": {"name": {"type": "string"}},
    }
    body = lambda required: {
        "content": {"application/json": {"schema": schema(required)}}
    }
    old = {"paths": {"/u": {"post": make_op(request_body=body(["name"]))}}}
    new = {"paths": {"/u": {"post": make_op(request_body=body([]))}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["required-body-props-removed"]


def test_cli_exit_codes(tmp_path):
    import json

    old = {"openapi": "3.0.0", "paths": {"/u": {"get": {}}}}
    same = {"openapi": "3.0.0", "paths": {"/u": {"get": {}}}}
    broken = {"openapi": "3.0.0", "paths": {}}
    old_p = tmp_path / "old.json"
    same_p = tmp_path / "same.json"
    broken_p = tmp_path / "broken.json"
    old_p.write_text(json.dumps(old))
    same_p.write_text(json.dumps(same))
    broken_p.write_text(json.dumps(broken))
    assert main([str(old_p), str(same_p)]) == 0
    assert main([str(old_p), str(broken_p)]) == 1
