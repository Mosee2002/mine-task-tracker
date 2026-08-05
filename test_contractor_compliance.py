import unittest
from datetime import datetime, timedelta
from extraction_helpers import load_functions


class TestContractorCompliance(unittest.TestCase):
    """contractor_compliance_status() gates physical site access for
    third parties. The fail-closed design -- missing or unreadable
    data blocks access, never silently passes -- is the single most
    important property to verify and keep verified here."""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions("contractor_compliance_status", extra_globals={"datetime": datetime})
        cls.status = staticmethod(cls.ns["contractor_compliance_status"])

    def test_fully_compliant_contractor(self):
        future = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
        label, is_blocking = self.status({"induction_expiry": future, "insurance_expiry": future})
        self.assertEqual(label, "Compliant")
        self.assertFalse(is_blocking)

    def test_expired_induction_blocks_access(self):
        past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        future = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
        label, is_blocking = self.status({"induction_expiry": past, "insurance_expiry": future})
        self.assertTrue(is_blocking)
        self.assertIn("EXPIRED", label)

    def test_missing_dates_fail_closed_not_open(self):
        """The critical property: a contractor with NO data on file
        must be BLOCKED, not silently treated as compliant. An absent
        record is not a passing record."""
        label, is_blocking = self.status({})
        self.assertTrue(is_blocking)
        self.assertIn("missing", label.lower())

    def test_unreadable_date_fails_closed(self):
        """Garbage data -- a corrupt entry, a typo'd date format --
        must also block access rather than be silently ignored."""
        future = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
        label, is_blocking = self.status({"induction_expiry": "not-a-real-date", "insurance_expiry": future})
        self.assertTrue(is_blocking)

    def test_expiring_soon_warns_but_does_not_yet_block(self):
        """Within 30 days should warn but not block -- distinguishing
        'expiring soon' from 'already expired' gives someone time to
        renew before being locked out."""
        soon = (datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d")
        label, is_blocking = self.status({"induction_expiry": soon, "insurance_expiry": soon})
        self.assertFalse(is_blocking)
        self.assertIn("expires in", label)


if __name__ == "__main__":
    unittest.main()
