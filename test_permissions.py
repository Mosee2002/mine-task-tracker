import unittest
from extraction_helpers import extract_between, _read_app_source


class TestPermissions(unittest.TestCase):
    """can() is the single authorization entry point every role-gated
    feature in the app calls through. A bug here is the highest-stakes
    kind: either a role silently loses access it should have, or
    worse, silently gains access it shouldn't."""

    @classmethod
    def setUpClass(cls):
        src = _read_app_source()
        # ROLE_PERMISSIONS and can() sit right next to each other in
        # app.py, so one extract_between call grabs both together --
        # can() needs ROLE_PERMISSIONS to exist in the same namespace.
        block = extract_between("ROLE_PERMISSIONS = {", "\ndef require(", src)
        cls.ns = {}
        exec(block, cls.ns)
        cls.can = staticmethod(cls.ns["can"])
        cls.role_permissions = cls.ns["ROLE_PERMISSIONS"]

    def test_worker_lacks_admin_capabilities(self):
        self.assertFalse(self.can("worker", "audit.view"))

    def test_unknown_role_gets_nothing(self):
        """A typo'd or corrupted role value must fail closed, not open."""
        self.assertFalse(self.can("some_made_up_role", "audit.view"))

    def test_none_role_gets_nothing(self):
        self.assertFalse(self.can(None, "audit.view"))

    def test_empty_string_role_gets_nothing(self):
        self.assertFalse(self.can("", "audit.view"))

    def test_role_check_is_case_insensitive(self):
        """Roles get compared in different cases in different places
        historically -- this must not silently deny a legitimate
        'Worker' vs 'worker' mismatch."""
        caps = self.role_permissions.get("worker", set())
        if caps:
            some_cap = next(iter(caps))
            self.assertEqual(self.can("Worker", some_cap), self.can("worker", some_cap))
            self.assertEqual(self.can("WORKER", some_cap), self.can("worker", some_cap))

    def test_role_check_strips_whitespace(self):
        caps = self.role_permissions.get("worker", set())
        if caps:
            some_cap = next(iter(caps))
            self.assertEqual(self.can(" worker ", some_cap), self.can("worker", some_cap))

    def test_higher_roles_never_have_fewer_capabilities_than_worker(self):
        """Structural sanity check: whichever role sits above worker
        in the hierarchy should never have STRICTLY FEWER capabilities
        -- if this ever fails, the permission table itself has become
        inverted somewhere, which is worth catching immediately."""
        worker_caps = self.role_permissions.get("worker", set())
        for higher_role in ("supervisor", "superintendent", "owner"):
            higher_caps = self.role_permissions.get(higher_role, set())
            if worker_caps and higher_caps:
                with self.subTest(role=higher_role):
                    self.assertGreaterEqual(len(higher_caps), len(worker_caps))


if __name__ == "__main__":
    unittest.main()
