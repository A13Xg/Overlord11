import unittest

from engine.loop_governor import LoopGovernor


class LoopGovernorTests(unittest.TestCase):
    def test_budget_accounting_and_credit(self):
        gov = LoopGovernor(
            {
                "enabled": True,
                "max_parent_loops": 5,
                "max_subagent_loops_total": 10,
                "max_subagent_loops_per_agent": 5,
                "max_retry_loops": 5,
                "max_effective_loops": 10,
                "progress_credit_enabled": True,
                "max_credit_per_epoch": 1,
                "progress_threshold": 2.0,
                "stall_threshold": 2.0,
                "stall_consecutive_limit": 3,
            },
            fallback_max_parent_loops=5,
        )
        self.assertTrue(gov.before_parent_loop().allow)
        post = gov.after_parent_loop(
            {
                "effectful_tool_success_count": 1,
                "artifact_created_count": 1,
                "delegation_completed_count": 0,
                "new_state_transition_count": 1,
                "error_reduction_count": 0,
                "repeated_tool_pattern": False,
                "repeated_error_pattern": False,
                "prose_only_non_trivial": False,
                "empty_or_invalid_response": False,
            }
        )
        self.assertTrue(post.allow)
        snap = gov.snapshot()
        self.assertGreaterEqual(snap["credits_applied_total"], 1)

    def test_stall_termination(self):
        gov = LoopGovernor({"enabled": True, "max_parent_loops": 10, "stall_consecutive_limit": 2}, fallback_max_parent_loops=10)
        self.assertTrue(gov.before_parent_loop().allow)
        gov.after_parent_loop({"repeated_error_pattern": True, "empty_or_invalid_response": True})
        self.assertTrue(gov.before_parent_loop().allow)
        dec = gov.after_parent_loop({"repeated_error_pattern": True, "empty_or_invalid_response": True})
        self.assertFalse(dec.allow)
        self.assertEqual(dec.reason, "stall_detected_no_progress")

    def test_subagent_caps(self):
        gov = LoopGovernor({"enabled": True, "max_parent_loops": 10, "max_subagent_loops_total": 2, "max_subagent_loops_per_agent": 1}, fallback_max_parent_loops=10)
        self.assertTrue(gov.before_subagent("OVR_COD_03").allow)
        gov.after_subagent("OVR_COD_03", {"child_loops_used": 1})
        self.assertFalse(gov.before_subagent("OVR_COD_03").allow)


if __name__ == "__main__":
    unittest.main()
