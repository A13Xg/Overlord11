import json
import unittest
from pathlib import Path

from engine.orchestrator_bridge import OrchestratorBridge


class OrchestratorBridgePromptModesTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent.parent
        self.config = json.loads((root / "config.json").read_text(encoding="utf-8"))
        self.bridge = OrchestratorBridge(config=self.config)

    def test_include_onboarding_true_contains_onboarding_text(self):
        prompt = self.bridge.build_system_prompt("OVR_DIR_01", include_onboarding=True)
        self.assertIn("What This Framework Is", prompt)

    def test_include_onboarding_false_excludes_onboarding_text(self):
        prompt = self.bridge.build_system_prompt("OVR_DIR_01", include_onboarding=False)
        self.assertNotIn("What This Framework Is", prompt)
        self.assertIn("Orchestrator", prompt)


if __name__ == "__main__":
    unittest.main()
