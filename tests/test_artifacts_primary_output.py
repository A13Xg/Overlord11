import unittest

from backend.api.artifacts import _select_primary_output


class ArtifactsPrimaryOutputTests(unittest.TestCase):
    def test_prefers_answer_file(self):
        items = [
            {"name": "final_output.md", "relative_path": "final_output.md", "category": "product", "ext": "md", "mtime": 10},
            {"name": "answer.html", "relative_path": "output/answer.html", "category": "output", "ext": "html", "mtime": 9, "is_html": True},
            {"name": "report.md", "relative_path": "output/report.md", "category": "output", "ext": "md", "mtime": 11},
        ]
        selected = _select_primary_output(items)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "answer.html")

    def test_prefers_product_html_when_no_answer(self):
        items = [
            {"name": "events.json", "relative_path": "artifacts/logs/events.json", "category": "logs", "ext": "json", "mtime": 20},
            {"name": "deliverable.html", "relative_path": "deliverable.html", "category": "product", "ext": "html", "mtime": 10, "is_html": True},
            {"name": "chart.png", "relative_path": "output/chart.png", "category": "output", "ext": "png", "mtime": 11, "is_image": True},
        ]
        selected = _select_primary_output(items)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "deliverable.html")

    def test_returns_none_for_empty_candidates(self):
        self.assertIsNone(_select_primary_output([]))

    def test_required_extension_wins_primary_selection(self):
        items = [
            {"name": "answer.md", "relative_path": "answer.md", "category": "product", "ext": "md", "mtime": 20},
            {"name": "report.pdf", "relative_path": "output/report.pdf", "category": "output", "ext": "pdf", "mtime": 10},
        ]
        selected = _select_primary_output(items, required_output_ext=".pdf")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "report.pdf")

    def test_required_extension_can_select_nonstandard_artifact(self):
        items = [
            {"name": "answer.md", "relative_path": "answer.md", "category": "product", "ext": "md", "mtime": 20},
            {"name": "deck.docx", "relative_path": "artifacts/deck.docx", "category": "artifacts", "ext": "docx", "mtime": 10},
        ]
        selected = _select_primary_output(items, required_output_ext=".docx")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["name"], "deck.docx")


if __name__ == "__main__":
    unittest.main()
