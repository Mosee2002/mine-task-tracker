import unittest
from datetime import datetime, timedelta
from extraction_helpers import load_functions


class TestMTTR(unittest.TestCase):
    """compute_mttr_hours_v2 -- drives both the on-screen Reliability
    tab and the PDF report, so a bug here would silently produce a
    wrong number in two places at once, possibly reported upward
    before anyone notices."""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions("compute_mttr_hours_v2", "_parse_dt", extra_globals={"datetime": datetime})
        cls.mttr = staticmethod(cls.ns["compute_mttr_hours_v2"])

    def test_computes_average_repair_time(self):
        tasks = [
            {"status": "Complete", "created_at": "2026-08-01T08:00:00", "completed_at": "2026-08-01T12:00:00"},
            {"status": "Complete", "created_at": "2026-08-02T08:00:00", "completed_at": "2026-08-02T14:00:00"},
        ]
        mttr, n = self.mttr(tasks)
        self.assertEqual(n, 2)
        self.assertEqual(mttr, 5.0)

    def test_ignores_incomplete_tasks(self):
        tasks = [
            {"status": "In Progress", "created_at": "2026-08-01T08:00:00"},
            {"status": "Complete", "created_at": "2026-08-01T08:00:00", "completed_at": "2026-08-01T10:00:00"},
        ]
        mttr, n = self.mttr(tasks)
        self.assertEqual(n, 1)

    def test_no_data_returns_none_not_zero(self):
        """None vs 0 matters -- 0 would falsely imply instant repairs;
        None correctly says 'nothing to measure yet'."""
        mttr, n = self.mttr([])
        self.assertIsNone(mttr)
        self.assertEqual(n, 0)

    def test_prefers_failure_start_over_created_at(self):
        tasks = [{
            "status": "Complete",
            "created_at": "2026-08-01T00:00:00",     # would give 12h if used
            "failure_start": "2026-08-01T08:00:00",  # should give 4h
            "completed_at": "2026-08-01T12:00:00",
        }]
        mttr, n = self.mttr(tasks)
        self.assertEqual(mttr, 4.0)


class TestPMCompliance(unittest.TestCase):
    """compute_pm_compliance_v2 -- the headline preventive-maintenance
    metric shown on both the Analytics dashboard and leadership's
    Overview tab."""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions("compute_pm_compliance_v2", "_parse_dt", extra_globals={"datetime": datetime})
        cls.pm = staticmethod(cls.ns["compute_pm_compliance_v2"])

    def test_all_completed_on_time(self):
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        two_days_ago = (datetime.now() - timedelta(days=2)).isoformat()
        tasks = [{"is_recurring": True, "due_date": yesterday, "completed_at": two_days_ago}]
        pct, n = self.pm(tasks)
        self.assertEqual(pct, 100.0)
        self.assertEqual(n, 1)

    def test_late_completion_counts_against_compliance(self):
        two_days_ago = (datetime.now() - timedelta(days=2)).isoformat()
        yesterday = (datetime.now() - timedelta(days=1)).isoformat()
        tasks = [{"is_recurring": True, "due_date": two_days_ago, "completed_at": yesterday}]
        pct, n = self.pm(tasks)
        self.assertEqual(pct, 0.0)

    def test_ignores_non_recurring_tasks(self):
        tasks = [{"is_recurring": False, "due_date": "2026-01-01T00:00:00"}]
        pct, n = self.pm(tasks)
        self.assertEqual(n, 0)

    def test_ignores_tasks_not_yet_due(self):
        future = (datetime.now() + timedelta(days=30)).isoformat()
        tasks = [{"is_recurring": True, "due_date": future}]
        pct, n = self.pm(tasks)
        self.assertEqual(n, 0)


class TestPlannedVsReactive(unittest.TestCase):
    """planned_vs_reactive -- the standard 80/20 maintenance benchmark."""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions("planned_vs_reactive")
        cls.split = staticmethod(cls.ns["planned_vs_reactive"])

    def test_splits_correctly(self):
        tasks = ([{"work_type": "Preventive"}] * 4) + ([{"work_type": "Reactive"}] * 1)
        planned_pct, reactive_pct, total = self.split(tasks)
        self.assertEqual(total, 5)
        self.assertEqual(planned_pct, 80.0)
        self.assertEqual(reactive_pct, 20.0)

    def test_empty_returns_none_not_zero(self):
        planned_pct, reactive_pct, total = self.split([])
        self.assertIsNone(planned_pct)
        self.assertIsNone(reactive_pct)
        self.assertEqual(total, 0)


class TestSafetyLeadingIndicators(unittest.TestCase):
    """safety_leading_indicators -- feeds the Safety analytics tab,
    the leadership Overview, and the PDF report simultaneously."""

    @classmethod
    def setUpClass(cls):
        cls.ns = load_functions("safety_leading_indicators", "_parse_dt",
                                extra_globals={"datetime": datetime, "timedelta": timedelta})
        cls.si = staticmethod(cls.ns["safety_leading_indicators"])

    def test_categorizes_incident_types_correctly(self):
        now = datetime.now().isoformat()
        incidents = [
            {"incident_type": "Near Miss", "status": "Closed", "corrective_action": "Fixed", "created_at": now},
            {"incident_type": "Hazard Observation", "status": "Open", "corrective_action": "", "created_at": now},
            {"incident_type": "Injury", "status": "Closed", "corrective_action": "Treated", "created_at": now},
        ]
        result = self.si(incidents, [])
        self.assertEqual(result["total_incidents"], 3)
        self.assertEqual(result["proactive_reports"], 2)
        self.assertEqual(result["injuries"], 1)

    def test_flags_open_incidents_without_corrective_action(self):
        now = datetime.now().isoformat()
        incidents = [
            {"incident_type": "Near Miss", "status": "Open", "corrective_action": "", "created_at": now},
            {"incident_type": "Near Miss", "status": "Open", "corrective_action": "Handled", "created_at": now},
        ]
        result = self.si(incidents, [])
        self.assertEqual(result["open_without_action"], 1)

    def test_no_incidents_gives_none_ratio_not_zero_division(self):
        result = self.si([], [])
        self.assertEqual(result["total_incidents"], 0)
        self.assertIsNone(result["near_miss_ratio"])


if __name__ == "__main__":
    unittest.main()
