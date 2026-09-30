# openapi-breakcheck

Catch breaking API changes before they ship. Compare two OpenAPI 3.x specs
and get a plain list of everything that can break an existing client.

## What it detects

- Removed paths and operations
- Removed required parameters
- Parameters that changed from optional to required
- Parameter type changes
- Removed enum values
- Request bodies that became required
- Removed required request-body properties

Added endpoints and new optional parameters are not breaking, so they pass.

## Install

```bash
pip install openapi-breakcheck
```

## Use

```bash
openapi-breakcheck old-spec.yaml new-spec.yaml
```

Exit code 0 means no breaking changes. Exit code 1 means at least one was
found. The output lists each change with its kind and location:

```
[removed-operation] DELETE /users: operation was removed
[param-became-required] GET /users param 'filter' in query: optional parameter became required
```

Use `--fail-on` in CI to fail only on specific kinds:

```bash
openapi-breakcheck old.yaml new.yaml --fail-on removed-path,removed-operation
```

## CI example

```yaml
- run: openapi-breakcheck specs/v1.yaml specs/v2.yaml
```

## License

MIT
