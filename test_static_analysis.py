import unittest
import ast
import re
from extraction_helpers import _read_app_source


class TestStaticAnalysis(unittest.TestCase):
    """Codifies the manual verification sweep that's been run by hand
    after nearly every change throughout this project's development --
    undefined names and duplicate function definitions. Several real
    bugs were caught this exact way during development (a function
    definition accidentally deleted during an edit, its body left
    dangling as unreachable or, worse, actively executing code in the
    wrong function). Making this a real, permanent test means that
    check happens automatically going forward, not only when someone
    remembers to run it by hand."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_app_source()
        cls.tree = ast.parse(cls.src)

    def test_file_compiles(self):
        """The most basic possible check, and the one that would have
        caught the Python-3.11 f-string bug this project actually
        shipped once -- compiling here uses whatever Python version
        runs the tests, which won't catch every version-specific
        issue, but catches a genuine syntax error regardless of
        version."""
        compile(self.src, "app.py", "exec")

    def test_no_undefined_names_at_module_level_analysis(self):
        tree = self.tree

        def add_target(node, s):
            if isinstance(node, ast.Name):
                s.add(node.id)
            elif isinstance(node, (ast.Tuple, ast.List)):
                for e in node.elts:
                    add_target(e, s)
            elif isinstance(node, ast.Starred):
                add_target(node.value, s)

        defined = set(__builtins__.keys()) if isinstance(__builtins__, dict) else set(dir(__builtins__))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    add_target(t, defined)
            if isinstance(node, ast.AugAssign):
                add_target(node.target, defined)
            if isinstance(node, ast.AnnAssign):
                add_target(node.target, defined)
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    defined.add((alias.asname or alias.name).split(".")[0])
            if isinstance(node, (ast.For, ast.AsyncFor)):
                add_target(node.target, defined)
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars:
                        add_target(item.optional_vars, defined)
            if isinstance(node, ast.comprehension):
                add_target(node.target, defined)
            if isinstance(node, ast.arg):
                defined.add(node.arg)
            if isinstance(node, ast.ExceptHandler) and node.name:
                defined.add(node.name)
            if isinstance(node, ast.Lambda):
                for a in (node.args.args + node.args.posonlyargs + node.args.kwonlyargs):
                    defined.add(a.arg)
                if node.args.vararg:
                    defined.add(node.args.vararg.arg)
                if node.args.kwarg:
                    defined.add(node.args.kwarg.arg)
            if isinstance(node, ast.NamedExpr):
                add_target(node.target, defined)

        suspects = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in defined:
                    suspects.setdefault(node.id, node.lineno)

        self.assertEqual(suspects, {},
            f"Undefined names found (often means a function definition "
            f"was accidentally deleted during an edit): {suspects}")

    def test_no_duplicate_top_level_function_definitions(self):
        fn_defs = re.findall(r"^def (\w+)\(", self.src, re.MULTILINE)
        from collections import Counter
        dupes = {k: v for k, v in Counter(fn_defs).items() if v > 1}
        self.assertEqual(dupes, {},
            f"Duplicate function definitions found: {dupes}")

    def test_no_backslash_in_fstring_expressions(self):
        """Python 3.11 and earlier forbid ANY backslash inside an
        f-string's {...} expression part -- this restriction was only
        lifted in Python 3.12 (PEP 701). This is the exact bug that
        shipped once and crashed the entire app with a SyntaxError on
        a live Python 3.11 deployment (an f-string embedding an HTML
        attribute with an escaped quote), while every compile check
        run during this project's own Python 3.12 development sandbox
        passed silently -- test_file_compiles() above could not have
        caught it, which is precisely why a dedicated check exists
        here rather than relying on compile() alone."""
        suspects = []
        for m in re.finditer(r'''f'{3}.*?'{3}|f"{3}.*?"{3}|f'[^'\n]*'|f"[^"\n]*"''',
                             self.src, re.DOTALL):
            content = m.group(0)
            depth = 0
            for i, ch in enumerate(content):
                if ch == '{' and (i + 1 >= len(content) or content[i + 1] != '{'):
                    depth += 1
                elif ch == '}' and depth > 0:
                    depth -= 1
                elif ch == '\\' and depth > 0:
                    line_no = self.src[:m.start()].count('\n') + 1
                    suspects.append((line_no, content[:80].replace('\n', '\\n')))
                    break
        self.assertEqual(suspects, [],
            f"Backslash inside f-string expression part(s) -- crashes "
            f"on Python 3.11 and earlier even when this passes here: {suspects}")

    def test_every_nav_section_has_exactly_one_routing_guard(self):
        """Each nav section needs exactly one 'if/elif selected_section
        == "X":' guard -- zero means that section is unreachable, more
        than one means an accidental duplicate block exists (both real
        mistakes that happened during this project's development).
        Owner Console is included even though it's a conditionally-
        inserted item (owner accounts only, not in the base nav_options
        list) -- it still needs its own real routing guard in the
        elif chain regardless of how it got added to the menu."""
        sections = ["Task Dashboard", "Assets", "Permits", "Inventory", "Incidents",
                   "Handover", "Contractors", "Analytics", "Chat", "Feedback",
                   "Admin", "Profile", "Timeline", "About", "Owner Console"]
        for section in sections:
            with self.subTest(section=section):
                count = (
                    len(re.findall(rf'elif selected_section == "{re.escape(section)}":', self.src))
                    + len(re.findall(rf'^if selected_section == "{re.escape(section)}":', self.src, re.MULTILINE))
                )
                self.assertEqual(count, 1,
                    f"'{section}' has {count} routing guards, expected exactly 1")


if __name__ == "__main__":
    unittest.main()
