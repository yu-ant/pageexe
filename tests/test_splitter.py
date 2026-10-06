import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import splitter  # noqa: E402


def make(folder, name, size):
    with open(os.path.join(folder, name), "wb") as f:
        f.write(b"x" * size)


class PlanTests(unittest.TestCase):
    def items(self, sizes):
        return [splitter.FileItem(f"f{i}.jpg", s, i) for i, s in enumerate(sizes)]

    def test_groups_stay_under_limit(self):
        groups = splitter.plan_groups(self.items([40, 40, 30, 50, 60, 10]), 100)
        self.assertEqual([g.total for g in groups], [80, 80, 70])
        self.assertTrue(all(g.total <= 100 for g in groups))

    def test_exact_limit_fits(self):
        groups = splitter.plan_groups(self.items([50, 50, 1]), 100)
        self.assertEqual([g.total for g in groups], [100, 1])

    def test_oversized_file_gets_own_group(self):
        groups = splitter.plan_groups(self.items([10, 150, 10]), 100)
        self.assertEqual([len(g.files) for g in groups], [1, 1, 1])

    def test_empty(self):
        self.assertEqual(splitter.plan_groups([], 100), [])

    def test_folder_names(self):
        self.assertEqual(splitter.group_folder_names("a", 3), ["a_01", "a_02", "a_03"])
        self.assertEqual(splitter.group_folder_names("a", 120)[0], "a_001")


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = self.tmp.name
        for i in range(5):
            make(self.src, f"img{i}.JPG", 30)
        make(self.src, "notes.txt", 10)
        os.mkdir(os.path.join(self.src, "sub"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_filters_images(self):
        self.assertEqual(len(splitter.scan_folder(self.src)), 5)
        self.assertEqual(len(splitter.scan_folder(self.src, include_all=True)), 6)

    def test_copy_and_move(self):
        for move in (False, True):
            with tempfile.TemporaryDirectory() as out:
                items = splitter.sort_files(splitter.scan_folder(self.src))
                groups = splitter.plan_groups(items, 70)
                done = splitter.execute(groups, out, "p", move=move)
                self.assertEqual(done, 5)
                self.assertEqual(sorted(os.listdir(out)), ["p_01", "p_02", "p_03"])
                self.assertEqual(sorted(os.listdir(os.path.join(out, "p_01"))),
                                 ["img0.JPG", "img1.JPG"])
                remaining = len(splitter.scan_folder(self.src))
                self.assertEqual(remaining, 0 if move else 5)


if __name__ == "__main__":
    unittest.main()
