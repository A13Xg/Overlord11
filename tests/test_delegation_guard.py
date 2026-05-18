import unittest

from engine.delegation_guard import validate_retry_strategy


class DelegationGuardTests(unittest.TestCase):
    def test_agent_change_is_blocked(self):
        ok, diag = validate_retry_strategy(
            {"agent_id": "OVR_COD_03", "task": "a"},
            {"agent_id": "OVR_PUB_07", "task": "b"},
            ["engine/"],
            {"OVR_COD_03", "OVR_PUB_07"},
        )
        self.assertFalse(ok)
        self.assertEqual(diag.get("retry_block_reason"), "agent_id_change_disallowed")

    def test_strategy_delta_allowed(self):
        ok, diag = validate_retry_strategy(
            {"agent_id": "OVR_COD_03", "task": "a", "timeout_s": 100},
            {"agent_id": "OVR_COD_03", "task": "b", "timeout_s": 120},
            ["engine/"],
            {"OVR_COD_03"},
        )
        self.assertTrue(ok)
        self.assertIsNone(diag.get("retry_block_reason"))

    def test_immutable_reference_blocked(self):
        ok, diag = validate_retry_strategy(
            {"agent_id": "OVR_COD_03", "task": "a"},
            {"agent_id": "OVR_COD_03", "task": "edit engine/runner.py"},
            ["engine/"],
            {"OVR_COD_03"},
        )
        self.assertFalse(ok)
        self.assertEqual(diag.get("retry_block_reason"), "immutable_core_reference_detected")


if __name__ == "__main__":
    unittest.main()
