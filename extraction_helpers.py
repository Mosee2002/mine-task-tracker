"""
Shared infrastructure for testing functions extracted from app.py.

Streamlit apps don't naturally separate into importable modules --
app.py is a single script that runs top-to-bottom, and importing it
directly would try to execute the whole app (hit Supabase, render
UI, the works). Rather than restructure a large, working file into a
"proper" package -- a much bigger and riskier undertaking on its own
-- these tests extract specific function definitions as source text
and exec() them in an isolated namespace with minimal mocks. This is
the same technique used throughout this project's own development
process to verify individual changes before shipping them; this file
formalizes it into something that can be run repeatedly, instead of
one-off scripts that get thrown away after each check.

This means these tests exercise REAL logic copied directly from the
real file (not hand-written approximations of what it should do) --
if app.py's actual function body changes, the extracted text changes
with it, so a real behavior change gets tested, not a stale copy.
"""
import ast
import os
import re

APP_PY_PATH = os.path.join(os.path.dirname(__file__), "..", "app.py")


def _read_app_source():
    with open(APP_PY_PATH, "r", encoding="utf-8") as f:
        return f.read()


def extract_function(func_name, source=None):
    """Extracts a single top-level `def func_name(...):` block from
    app.py using Python's ast module to find its exact start and end.

    This used to find the end by searching for the next top-level
    `def `/`class ` line, which works for a function immediately
    followed by another function -- but breaks when a function is
    followed by ordinary top-level code instead (like the session-
    state initialization block that happens to sit right after
    safety_leading_indicators): the regex-based search would skip
    straight past that code looking for the next def/class, silently
    swallowing dozens of unrelated lines into the "extracted
    function" and causing confusing NameErrors when it eventually
    got exec'd. AST parsing knows a function's real end
    (node.end_lineno) regardless of what follows it, which is the
    actually-correct way to answer "where does this function stop."
    """
    src = source if source is not None else _read_app_source()
    tree = ast.parse(src)
    lines = src.split("\n")

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            start = node.lineno - 1
            end = node.end_lineno
            return "\n".join(lines[start:end])

    raise ValueError(f"Could not find 'def {func_name}(' in app.py")


def extract_between(start_marker, end_marker, source=None):
    """Extracts a raw text range between two exact substrings --
    used for things that aren't a single function, like the
    TRANSLATIONS dict definition or a block of module-level constants."""
    src = source if source is not None else _read_app_source()
    start = src.index(start_marker)
    end = src.index(end_marker, start)
    return src[start:end]


def load_functions(*func_names, extra_globals=None):
    """Extracts and exec()s one or more functions together in a
    shared namespace, so functions that call each other (e.g. a
    function that calls esc() or _parse_dt()) can be tested as a
    genuine group rather than needing every dependency stubbed out
    individually. Returns the namespace dict; access functions via
    ns['function_name']."""
    src = _read_app_source()
    combined = "\n\n".join(extract_function(name, src) for name in func_names)
    ns = dict(extra_globals or {})
    exec(combined, ns)
    return ns
