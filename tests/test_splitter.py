import os
import sys
import tempfile
import unittest
import zipfile

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


class FlattenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = self.tmp.name
        make(self.src, "top.jpg", 5)
        for d in ("a", os.path.join("a", "deep"), "b"):
            os.makedirs(os.path.join(self.src, d), exist_ok=True)
        make(os.path.join(self.src, "a"), "same.jpg", 10)
        make(os.path.join(self.src, "b"), "same.jpg", 20)
        make(os.path.join(self.src, "a", "deep"), "x.png", 30)
        make(os.path.join(self.src, "b"), "memo.txt", 1)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_skips_top_level_and_non_images(self):
        names = sorted(os.path.basename(i.path) for i in splitter.scan_subfolders(self.src))
        self.assertEqual(names, ["same.jpg", "same.jpg", "x.png"])

    def test_move_flatten_renames_duplicates_and_cleans(self):
        items = splitter.scan_subfolders(self.src)
        self.assertEqual(splitter.flatten(items, self.src, move=True), 3)
        top = sorted(os.listdir(self.src))
        self.assertIn("same.jpg", top)
        self.assertIn("same (1).jpg", top)
        self.assertIn("x.png", top)
        # b에는 memo.txt가 남아 있으므로 b는 남고, a와 a/deep은 지워진다
        self.assertEqual(splitter.remove_empty_dirs(self.src), 2)
        self.assertTrue(os.path.isdir(os.path.join(self.src, "b")))
        self.assertFalse(os.path.exists(os.path.join(self.src, "a")))

    def test_copy_flatten_keeps_originals(self):
        items = splitter.scan_subfolders(self.src)
        splitter.flatten(items, self.src, move=False)
        self.assertEqual(len(splitter.scan_subfolders(self.src)), 3)


class ZipTests(unittest.TestCase):
    def test_zip_groups_stay_under_limit(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
            for i in range(20):
                make(src, f"사진_{i:02d}.jpg", 1000 + i * 37)
            items = splitter.sort_files(splitter.scan_folder(src))
            limit = 6000
            groups = splitter.plan_groups(items, limit, for_zip=True)
            done = splitter.execute_zip(groups, out, "p")
            self.assertEqual(done, 20)
            zips = sorted(os.listdir(out))
            self.assertEqual(len(zips), len(groups))
            count = 0
            for z in zips:
                path = os.path.join(out, z)
                self.assertLessEqual(os.path.getsize(path), limit)
                with zipfile.ZipFile(path) as zf:
                    self.assertIsNone(zf.testzip())
                    count += len(zf.namelist())
            self.assertEqual(count, 20)
            self.assertEqual(len(os.listdir(src)), 20)  # 원본 유지

    def test_zip_stop_removes_partial(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
            for i in range(4):
                make(src, f"{i}.jpg", 100)
            groups = splitter.plan_groups(splitter.scan_folder(src), 10 ** 6, for_zip=True)
            calls = []

            def stop():
                calls.append(1)
                return len(calls) > 2

            done = splitter.execute_zip(groups, out, "p", should_stop=stop)
            self.assertEqual(done, 0)
            self.assertEqual(os.listdir(out), [])


if __name__ == "__main__":
    unittest.main()
