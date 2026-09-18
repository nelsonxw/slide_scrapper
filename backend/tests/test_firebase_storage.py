"""Test Firebase storage service and slide index operations."""
import tempfile
import unittest
from pathlib import Path
from app.config import settings
from app.firebase.storage import FirebaseStorageService


class TestFirebaseStorage(unittest.TestCase):
    def test_storage_upload_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            orig_data_dir = settings.data_dir
            settings.data_dir = tmp_path

            try:
                storage = FirebaseStorageService()

                # Create dummy pptx and preview png
                dummy_pptx = tmp_path / "test_slide_1.pptx"
                dummy_pptx.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
                dummy_png = tmp_path / "test_slide_1.png"
                dummy_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

                card = storage.upload_slide_file(
                    local_pptx_path=dummy_pptx,
                    local_preview_path=dummy_png,
                    original_source_url="https://example.com/slides",
                    original_presentation_name="Sample Deck",
                    slide_title="Sample Title",
                    slide_index=0,
                    total_slides=1,
                )

                self.assertEqual(card.slide_filename, "test_slide_1.pptx")
                self.assertEqual(card.title, "Sample Title")
                # In local fallback mode, public_pptx_url may be empty
                if storage.is_connected:
                    self.assertTrue(card.public_pptx_url)

                # List slides
                all_slides = storage.list_slides()
                self.assertGreaterEqual(len(all_slides), 1)
                found = [s for s in all_slides if s.id == card.id]
                self.assertEqual(len(found), 1)

                # Delete slide
                del_res = storage.delete_slides([card.id])
                self.assertGreaterEqual(del_res["deleted_count"], 1)

                # Verify removal
                remaining_slides = storage.list_slides()
                found_after = [s for s in remaining_slides if s.id == card.id]
                self.assertEqual(len(found_after), 0)
            finally:
                settings.data_dir = orig_data_dir


if __name__ == "__main__":
    unittest.main()

