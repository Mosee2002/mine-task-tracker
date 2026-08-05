import unittest
import re
from extraction_helpers import load_functions


class TestFriendlyDbError(unittest.TestCase):
    """friendly_db_error() classifies raw Supabase errors into
    actionable messages -- connectivity failures, missing-column
    schema-cache errors, or passed through unchanged. This is the
    function that grew out of a real production bug (a broken QR
    code traced back to a schema-cache mismatch) and later a
    genuinely serious near-miss (a connectivity error being
    misread as a data problem). Both classes of mistake are worth
    permanently guarding against, not just fixing once."""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions("friendly_db_error", extra_globals={"re": re})
        cls.friendly_db_error = staticmethod(cls.ns["friendly_db_error"])

    def test_connection_refused_is_classified_as_connectivity(self):
        err = ("HTTPSConnectionPool(host='xxx.supabase.co', port=443): "
              "Max retries exceeded with url: /rest/v1/tasks (Caused by "
              "NewConnectionError('Failed to establish a new connection: "
              "[Errno -2] Name or service not known'))")
        result = self.friendly_db_error(err)
        self.assertIn("📶", result, "Connectivity errors should get the network icon")
        self.assertIn("connection", result.lower())

    def test_read_timeout_is_classified_as_connectivity(self):
        err = "HTTPSConnectionPool(host='xxx.supabase.co', port=443): Read timed out."
        result = self.friendly_db_error(err)
        self.assertIn("📶", result)

    def test_schema_cache_error_gets_actionable_guidance(self):
        err = ('{"code":"PGRST204","message":"Could not find the \'department\' '
              'column of \'facility_users\' in the schema cache"}')
        result = self.friendly_db_error(err)
        self.assertIn("department", result)
        self.assertIn("schema_additions.sql", result)

    def test_unrelated_errors_pass_through_unchanged(self):
        """The most important test in this file: a genuine data
        problem (duplicate key, permission denied) must NEVER be
        misclassified as a connectivity issue or a schema issue --
        someone needs to see the real error to actually fix it."""
        for err in [
            '{"code":"23505","message":"duplicate key value violates unique constraint"}',
            '{"code":"42501","message":"permission denied for table tasks"}',
            "ValueError: invalid literal for int()",
        ]:
            with self.subTest(err=err):
                result = self.friendly_db_error(err)
                self.assertEqual(result, err,
                    "Unrelated errors must pass through completely unchanged")


if __name__ == "__main__":
    unittest.main()
