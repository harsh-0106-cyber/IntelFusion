import tempfile
import unittest
from pathlib import Path
from PIL import Image
import zlens.engine as zlens


class StarterRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = zlens.DB_PATH
        self.old_root = zlens.ROOT
        self.old_collection = zlens.COLLECTION_DIR
        self.old_uploads = zlens.UPLOAD_DIR
        root = Path(self.tmp.name).resolve()
        zlens.ROOT = root
        zlens.DATA_DIR = root / "data"
        zlens.COLLECTION_DIR = zlens.DATA_DIR / "collection"
        zlens.UPLOAD_DIR = zlens.DATA_DIR / "uploads"
        zlens.DB_PATH = zlens.DATA_DIR / "test.sqlite3"
        for folder in (zlens.DATA_DIR, zlens.COLLECTION_DIR, zlens.UPLOAD_DIR):
            folder.mkdir(parents=True, exist_ok=True)
        zlens.init_db()

    def tearDown(self):
        zlens.DB_PATH = self.old_db
        zlens.ROOT = self.old_root
        zlens.COLLECTION_DIR = self.old_collection
        zlens.UPLOAD_DIR = self.old_uploads
        self.tmp.cleanup()

    def make_image(self, path, color, size=(128, 128)):
        Image.new("RGB", size, color).save(path)
        return path

    def test_exact_match(self):
        p = self.make_image(zlens.COLLECTION_DIR / "test.png", (200, 20, 40))
        zlens.index_file(p)
        results, examined, qsha = zlens.search_image(p)
        self.assertEqual(len(results), 1)
        self.assertEqual(examined, 1)
        self.assertTrue(results[0]["exact_match"])
        self.assertEqual(results[0]["match_type"], "Exact duplicate")
        self.assertEqual(results[0]["phash_distance"], 0)
        self.assertEqual(results[0]["dhash_distance"], 0)

    def test_empty_collection(self):
        p = self.make_image(zlens.UPLOAD_DIR / "query.png", (10, 200, 40))
        results, examined, qsha = zlens.search_image(p)
        self.assertEqual(examined, 0)
        self.assertEqual(len(results), 0)

    def test_hamming_distance(self):
        self.assertEqual(zlens.hamming_hex("0f", "00"), 4)
        with self.assertRaises(ValueError):
            zlens.hamming_hex("xyz", "000")

    def test_index_updates_existing_path(self):
        p = self.make_image(zlens.COLLECTION_DIR / "same.png", (10, 20, 30))
        first = zlens.index_file(p)
        second = zlens.index_file(p)
        self.assertEqual(first["id"], second["id"])
        with zlens.connect_db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
