"""Generate ``schemas.json`` by AST-parsing ``mcp/server.py``.

One-shot helper. Run after any tool-signature change in ``mcp/server.py``::

    python -m bregsurv_agent._gen_schemas

Writes ``bregsurv_agent/schemas.json`` containing one OpenAI-format
function-tool schema per ``@mcp.tool()``-decorated function. The agent
loads this JSON at startup so the runtime path does NOT depend on the
``mcp`` library or any Python >= 3.10 syntax features.

What gets parsed:
  * Function name → ``function.name``.
  * Docstring (text up to the first ``Args:`` line or the first blank
    line preceded by content) → ``function.description``.
  * Parameter annotation + default → JSON Schema entry in
    ``function.parameters.properties``.
  * Per-parameter ``Args:`` body line (e.g. ``data_path: Path to a ...``)
    → ``properties[name].description``.
  * Parameters without a default → added to ``required``.

What does NOT get parsed:
  * ``@mcp.prompt()``-decorated functions (e.g. ``bregsurv_start_prompt``).
  * Bare top-level helpers like ``_run_r``, ``_attach_*``.
  * Return-type annotations (OpenAI schema only describes inputs).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PY = REPO_ROOT / "mcp" / "server.py"
SCHEMAS_JSON = Path(__file__).resolve().parent / "schemas.json"


# -- annotation -> JSON Schema -----------------------------------------------

def _ann_to_schema(node: Optional[ast.AST]) -> dict:
    """Convert a Python type-annotation AST node to JSON Schema fragment."""
    if node is None:
        return {}
    # Bare names: str / int / float / bool / dict / list
    if isinstance(node, ast.Name):
        name = node.id
        return {
            "str": {"type": "string"},
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "dict": {"type": "object"},
            "list": {"type": "array"},
        }.get(name, {})
    # Subscripted: Optional[X], list[X], List[X], Union[...], tuple[...], dict[K,V]
    if isinstance(node, ast.Subscript):
        value = node.value
        slc = node.slice
        # In Python 3.9+ the slice is the inner node; in 3.8 it's an Index wrapper.
        if isinstance(slc, ast.Index):  # py3.8 compat
            slc = slc.value
        base_name = None
        if isinstance(value, ast.Name):
            base_name = value.id
        elif isinstance(value, ast.Attribute):
            base_name = value.attr
        if base_name == "Optional":
            return _ann_to_schema(slc)
        if base_name in ("list", "List", "Sequence", "Iterable"):
            return {"type": "array", "items": _ann_to_schema(slc) or {}}
        if base_name in ("dict", "Dict"):
            return {"type": "object"}
        if base_name == "Union":
            # Strip None and recurse on first non-None.
            if isinstance(slc, ast.Tuple):
                non_none = [e for e in slc.elts
                            if not (isinstance(e, ast.Constant) and e.value is None)]
                if non_none:
                    return _ann_to_schema(non_none[0])
            return {}
        if base_name == "Tuple":
            return {"type": "array"}
    return {}


# -- default-value extraction ------------------------------------------------

def _default_value(node: ast.AST):
    """Extract Python value from a default-value AST node, if it's a literal."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _default_value(node.operand)
        if isinstance(inner, (int, float)):
            return -inner
    if isinstance(node, ast.List):
        return [_default_value(e) for e in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_default_value(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return {
            _default_value(k): _default_value(v)
            for k, v in zip(node.keys, node.values)
        }
    return None


# -- docstring parsing -------------------------------------------------------

_ARGS_HEADER = re.compile(r"^\s*Args:\s*$", re.MULTILINE)
_RETURNS_HEADER = re.compile(r"^\s*Returns:\s*$", re.MULTILINE)


def _split_docstring(doc: str) -> tuple[str, dict[str, str]]:
    """Return (description, per-arg-description-map).

    Description is everything up to the first ``Args:`` line, with
    leading/trailing whitespace trimmed. Per-arg map parses the
    ``Args:`` block; each entry can span multiple lines until the next
    parameter (a name followed by ``:``) or end-of-block.
    """
    if not doc:
        return "", {}

    args_match = _ARGS_HEADER.search(doc)
    if args_match:
        description = doc[: args_match.start()].rstrip()
        rest = doc[args_match.end():]
    else:
        description = doc.rstrip()
        rest = ""

    # Stop at the next "Returns:" header inside the args block.
    returns_match = _RETURNS_HEADER.search(rest)
    args_block = rest[: returns_match.start()] if returns_match else rest

    # Parse per-arg lines. A parameter starts with whitespace + name + colon.
    arg_descs: dict[str, str] = {}
    current_name: Optional[str] = None
    current_buf: list[str] = []
    param_line = re.compile(r"^\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")

    for line in args_block.splitlines():
        if not line.strip():
            if current_name:
                current_buf.append("")
            continue
        m = param_line.match(line)
        if m:
            if current_name is not None:
                arg_descs[current_name] = " ".join(
                    s.strip() for s in current_buf if s.strip()
                )
            current_name = m.group(1)
            current_buf = [m.group(2)]
        else:
            if current_name is not None:
                current_buf.append(line.strip())

    if current_name is not None:
        arg_descs[current_name] = " ".join(
            s.strip() for s in current_buf if s.strip()
        )

    return description.strip(), arg_descs


# -- decorator detection -----------------------------------------------------

def _is_mcp_tool(decorator_list) -> bool:
    """True if the function has an ``@mcp.tool()`` decorator (call form)."""
    for deco in decorator_list:
        # @mcp.tool()  ->  ast.Call(func=ast.Attribute(value=Name('mcp'), attr='tool'))
        if (isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and isinstance(deco.func.value, ast.Name)
                and deco.func.value.id == "mcp"
                and deco.func.attr == "tool"):
            return True
    return False


# -- main --------------------------------------------------------------------

def generate() -> list[dict]:
    """Parse server.py, return the OpenAI tool-schema list."""
    src = SERVER_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)

    schemas: list[dict] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if not _is_mcp_tool(node.decorator_list):
            continue

        doc = ast.get_docstring(node) or ""
        desc, arg_descs = _split_docstring(doc)

        properties: dict[str, dict] = {}
        required: list[str] = []

        args = node.args.args
        defaults = node.args.defaults
        # Match defaults to the trailing positional args.
        n_args = len(args)
        n_defaults = len(defaults)
        default_for: dict[int, ast.AST] = {}
        for i, d in enumerate(defaults):
            default_for[n_args - n_defaults + i] = d

        for i, arg in enumerate(args):
            name = arg.arg
            schema = _ann_to_schema(arg.annotation)
            description = arg_descs.get(name, "").strip()
            if description:
                schema["description"] = description

            if i in default_for:
                default_node = default_for[i]
                value = _default_value(default_node)
                # Optional[X] = None: keep schema as-is, do NOT add to required.
                if value is None and _is_optional_default(default_node):
                    pass
                else:
                    schema["default"] = value
            else:
                required.append(name)

            properties[name] = schema

        function_schema = {
            "type": "function",
            "function": {
                "name": node.name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        }
        schemas.append(function_schema)

    return schemas


def _is_optional_default(node: ast.AST) -> bool:
    """True if the default-value AST is the literal ``None``."""
    return isinstance(node, ast.Constant) and node.value is None


def main() -> None:
    schemas = generate()
    SCHEMAS_JSON.write_text(
        json.dumps(schemas, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(schemas)} tool schemas to {SCHEMAS_JSON}")


if __name__ == "__main__":
    main()
