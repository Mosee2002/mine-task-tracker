import unittest
from datetime import datetime
from extraction_helpers import load_functions


class TestDateTime(unittest.TestCase):
    """_parse_dt and _fmt_log_time are the foundation every analytics
    calculation and timestamp display in the app depends on. A silent
    bug here doesn't crash anything visibly -- it just quietly
    produces wrong numbers everywhere downstream, which is exactly
    the kind of failure worth locking down permanently."""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions("_parse_dt", "_fmt_log_time", extra_globals={"datetime": datetime})
        cls.parse_dt = staticmethod(cls.ns["_parse_dt"])
        cls.fmt_log_time = staticmethod(cls.ns["_fmt_log_time"])

    def test_parses_valid_iso_string(self):
        result = self.parse_dt("2026-08-01T22:32:00")
        self.assertIsNotNone(result)
        self.assertEqual((result.year, result.month, result.day), (2026, 8, 1))

    def test_handles_utc_z_suffix(self):
        """Supabase timestamps often come back with a trailing Z for
        UTC -- this must not break parsing."""
        result = self.parse_dt("2026-08-01T22:32:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 22)

    def test_handles_timezone_offset(self):
        result = self.parse_dt("2026-08-01T22:32:00+03:00")
        self.assertIsNotNone(result)

    def test_none_input_returns_none(self):
        self.assertIsNone(self.parse_dt(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(self.parse_dt(""))

    def test_garbage_input_returns_none_not_exception(self):
        """Malformed data reaching this function -- a corrupt DB row,
        a manual entry error -- must degrade to None, never raise.
        Every caller in the app assumes this function can't throw."""
        for bad_value in ["not a date at all", 12345, {"not": "a date"}, ["nope"]]:
            with self.subTest(value=bad_value):
                self.assertIsNone(self.parse_dt(bad_value))

    def test_fmt_log_time_produces_readable_format(self):
        result = self.fmt_log_time("2026-08-01T22:32:00")
        self.assertEqual(result, "Aug 01, 22:32")

    def test_fmt_log_time_falls_back_on_unparseable_input(self):
        """Documented fallback: if parsing fails, show something
        readable-ish rather than crash or show nothing."""
        result = self.fmt_log_time("garbage")
        self.assertEqual(result, "garbage"[:16])

    def test_fmt_log_time_none_does_not_crash(self):
        self.assertEqual(self.fmt_log_time(None), "")


if __name__ == "__main__":
    unittest.main()
