"""Test FastAPI endpoints."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "online")
        self.assertIn("slide-preview.firebasestorage.app", data["storage_bucket"])

    def test_storage_status_endpoint(self):
        res = self.client.get("/api/slides/storage-status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("slide-preview.firebasestorage.app", data["bucket_name"])

    def test_list_and_delete_slides_api(self):
        # List slides
        res = self.client.get("/api/slides")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

        # Delete empty list
        del_res = self.client.request("DELETE", "/api/slides", json={"slide_ids": []})
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()["deleted_count"], 0)

    def test_previously_scraped_target_is_skipped(self):
        with patch("app.routes.scrape._was_scraped", return_value=True):
            res = self.client.post("/api/scrape/start", json={"url": "https://example.com/already-scraped"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "completed")
        self.assertIn("already scraped", res.json()["current_step"])

    def test_scrape_start_and_status(self):
        res = self.client.post("/api/scrape/start", json={"url": "https://example.com/test", "max_pages": 1, "max_depth": 1})
        self.assertEqual(res.status_code, 200)
        task_data = res.json()
        self.assertIn("task_id", task_data)
        self.assertIn(task_data["status"], ["queued", "running", "completed"])

        task_id = task_data["task_id"]
        status_res = self.client.get(f"/api/scrape/status/{task_id}")
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.json()["task_id"], task_id)


if __name__ == "__main__":
    unittest.main()

