"""Tests for openapi-breakcheck diff detection."""

from breakcheck import diff_specs
from breakcheck.cli import main


def make_op(params=None, request_body=None, responses=None):
    op = {}
    if params is not None:
        op["parameters"] = params
    if request_body is not None:
        op["requestBody"] = request_body
    if responses is not None:
        op["responses"] = responses
    return op


def response(status="200", schema=None, media="application/json"):
    content = {}
    if schema is not None:
        content = {media: {"schema": schema}}
    return {status: {"description": "ok", "content": content}}


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


def test_request_body_type_changed():
    schema = lambda stype: {
        "type": stype,
        "properties": {"name": {"type": "string"}},
    }
    body = lambda stype: {
        "content": {"application/json": {"schema": schema(stype)}}
    }
    old = {"paths": {"/u": {"post": make_op(request_body=body("object"))}}}
    new = {"paths": {"/u": {"post": make_op(request_body=body("array"))}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["request-body-type-changed"]
    assert "object" in changes[0].detail and "array" in changes[0].detail


def test_request_body_prop_type_changed():
    schema = lambda ptype: {
        "type": "object",
        "properties": {"count": {"type": ptype}},
    }
    body = lambda ptype: {
        "content": {"application/json": {"schema": schema(ptype)}}
    }
    old = {"paths": {"/u": {"post": make_op(request_body=body("integer"))}}}
    new = {"paths": {"/u": {"post": make_op(request_body=body("string"))}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["request-body-prop-type-changed"]
    assert "'count'" in changes[0].location


def test_request_body_enum_values_removed():
    schema = lambda values: {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": values}},
    }
    body = lambda values: {
        "content": {"application/json": {"schema": schema(values)}}
    }
    old = {
        "paths": {
            "/u": {"post": make_op(request_body=body(["active", "archived"]))}
        }
    }
    new = {"paths": {"/u": {"post": make_op(request_body=body(["active"]))}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["request-body-enum-values-removed"]
    assert "archived" in changes[0].detail


def test_request_body_enum_widened_is_fine():
    schema = lambda values: {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": values}},
    }
    body = lambda values: {
        "content": {"application/json": {"schema": schema(values)}}
    }
    old = {"paths": {"/u": {"post": make_op(request_body=body(["active"]))}}}
    new = {
        "paths": {
            "/u": {"post": make_op(request_body=body(["active", "archived"]))}
        }
    }
    assert diff_specs(old, new) == []


def test_removed_optional_body_prop_is_fine():
    schema = lambda props: {"type": "object", "properties": props}
    body = lambda props: {
        "content": {"application/json": {"schema": schema(props)}}
    }
    old = {
        "paths": {
            "/u": {
                "post": make_op(
                    request_body=body(
                        {
                            "name": {"type": "string"},
                            "nick": {"type": "string"},
                        }
                    )
                )
            }
        }
    }
    new = {
        "paths": {
            "/u": {"post": make_op(request_body=body({"name": {"type": "string"}}))}
        }
    }
    assert diff_specs(old, new) == []


def test_identical_responses_no_changes():
    schema = {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "integer"}},
    }
    old = {"paths": {"/u": {"get": make_op(responses=response(schema=schema))}}}
    new = {"paths": {"/u": {"get": make_op(responses=response(schema=schema))}}}
    assert diff_specs(old, new) == []


def test_removed_response():
    old = {
        "paths": {
            "/u": {
                "get": make_op(
                    responses={**response("200"), **response("404")}
                )
            }
        }
    }
    new = {"paths": {"/u": {"get": make_op(responses=response("200"))}}}
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["removed-response"]
    assert "'404'" in changes[0].location


def test_added_response_is_fine():
    old = {"paths": {"/u": {"get": make_op(responses=response("200"))}}}
    new = {
        "paths": {
            "/u": {
                "get": make_op(
                    responses={**response("200"), **response("201")}
                )
            }
        }
    }
    assert diff_specs(old, new) == []


def test_response_type_changed():
    old = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema={"type": "object"}))}
        }
    }
    new = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema={"type": "array"}))}
        }
    }
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["response-type-changed"]
    assert "object" in changes[0].detail and "array" in changes[0].detail


def test_required_response_prop_removed():
    schema = lambda required: {
        "type": "object",
        "required": required,
        "properties": {"name": {"type": "string"}},
    }
    old = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema=schema(["name"])))}
        }
    }
    new = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema=schema([])))}
        }
    }
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["required-response-props-removed"]
    assert "name" in changes[0].detail


def test_removed_optional_response_prop_is_fine():
    schema = lambda required: {
        "type": "object",
        "required": required,
        "properties": {
            "name": {"type": "string"},
            "nick": {"type": "string"},
        },
    }
    old = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema=schema(["name"])))}
        }
    }
    new_schema = {
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"type": "string"}},
    }
    new = {
        "paths": {"/u": {"get": make_op(responses=response(schema=new_schema))}}
    }
    assert diff_specs(old, new) == []


def test_response_prop_type_changed():
    schema = lambda ptype: {
        "type": "object",
        "properties": {"count": {"type": ptype}},
    }
    old = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema=schema("integer")))}
        }
    }
    new = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema=schema("string")))}
        }
    }
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["response-prop-type-changed"]
    assert "'count'" in changes[0].location


def test_response_enum_values_removed():
    schema = lambda values: {
        "type": "object",
        "properties": {"status": {"type": "string", "enum": values}},
    }
    old = {
        "paths": {
            "/u": {
                "get": make_op(
                    responses=response(schema=schema(["active", "archived"]))
                )
            }
        }
    }
    new = {
        "paths": {
            "/u": {"get": make_op(responses=response(schema=schema(["active"])))}
        }
    }
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["response-enum-values-removed"]
    assert "archived" in changes[0].detail


def test_removed_response_media_type():
    old = {
        "paths": {
            "/u": {
                "get": make_op(
                    responses={
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {"schema": {"type": "object"}},
                                "text/plain": {"schema": {"type": "string"}},
                            },
                        }
                    }
                )
            }
        }
    }
    new = {
        "paths": {
            "/u": {
                "get": make_op(
                    responses={
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {"schema": {"type": "object"}},
                            },
                        }
                    }
                )
            }
        }
    }
    changes = diff_specs(old, new)
    assert [c.kind for c in changes] == ["removed-response-media-type"]
    assert "text/plain" in changes[0].detail


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


def test_breaking_change_to_dict():
    from breakcheck import BreakingChange

    change = BreakingChange("removed-path", "/gone", "entire path was removed")
    assert change.to_dict() == {
        "kind": "removed-path",
        "location": "/gone",
        "detail": "entire path was removed",
    }


def _write_specs(tmp_path, old, new):
    import json

    old_p = tmp_path / "old.json"
    new_p = tmp_path / "new.json"
    old_p.write_text(json.dumps(old))
    new_p.write_text(json.dumps(new))
    return str(old_p), str(new_p)


def test_cli_json_output_with_changes(tmp_path, capsys):
    import json

    old_p, new_p = _write_specs(
        tmp_path,
        {"paths": {"/u": {"get": {}, "delete": {}}}},
        {"paths": {"/u": {"get": {}}}},
    )
    assert main([old_p, new_p, "--output", "json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["changes"] == [
        {
            "kind": "removed-operation",
            "location": "DELETE /u",
            "detail": "operation was removed",
        }
    ]
    assert doc["summary"] == {"total": 1}
    assert "failing" not in doc["summary"]


def test_cli_json_output_no_changes(tmp_path, capsys):
    import json

    old_p, new_p = _write_specs(
        tmp_path,
        {"paths": {"/u": {"get": {}}}},
        {"paths": {"/u": {"get": {}}}},
    )
    assert main([old_p, new_p, "--output", "json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc == {"changes": [], "summary": {"total": 0}}


def test_cli_json_output_with_fail_on(tmp_path, capsys):
    import json

    old_p, new_p = _write_specs(
        tmp_path,
        {"paths": {"/u": {"get": {}, "delete": {}}}},
        {"paths": {"/u": {"get": {}}}},
    )
    assert main([old_p, new_p, "--output", "json", "--fail-on", "removed-operation"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["summary"] == {"total": 1, "failing": 1}
    assert main([old_p, new_p, "--output", "json", "--fail-on", "removed-path"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["summary"] == {"total": 1, "failing": 0}


def test_cli_json_output_invalid_choice(tmp_path):
    import pytest

    old_p, new_p = _write_specs(
        tmp_path,
        {"paths": {"/u": {"get": {}}}},
        {"paths": {"/u": {"get": {}}}},
    )
    with pytest.raises(SystemExit):
        main([old_p, new_p, "--output", "yaml"])
