
import os
import time
import shutil
import tempfile
from deliver.pkgs import DevRepoManager, PackageInstaller
from .util import TestBase, DeveloperPkgRepo


class TestManifest(TestBase):

    def setUp(self):
        root = tempfile.mkdtemp(prefix="rez_deliver_test_")
        install_path = tempfile.mkdtemp(prefix="rez_deliver_test_install_")
        release_path = tempfile.mkdtemp(prefix="rez_deliver_test_release_")

        self.root = root
        self.dev_repo = DeveloperPkgRepo(root)
        self.settings = {
            "packages_path": [install_path, release_path],
            "local_packages_path": install_path,
            "release_packages_path": release_path,
            "plugins": {
                "command": {"deliver": {"dev_repository_roots": [root]}}
            }
        }
        super(TestManifest, self).setUp()

        self.installer = PackageInstaller(DevRepoManager())

    def tearDown(self):
        # from rez.serialise import clear_file_caches
        retries = 5
        if os.path.exists(self.root):
            for i in range(retries):
                try:
                    shutil.rmtree(self.root)
                    break
                except Exception:
                    if i < (retries - 1):
                        time.sleep(0.2)

    def test_resolve_1(self):
        self.dev_repo.add("foo", version="1")
        self.dev_repo.add("bar", version="1", requires=["foo"])

        self.installer.resolve("bar")

        manifest = self.installer.manifest()
        self.assertEqual("foo-1", manifest[0].name)
        self.assertEqual("bar-1", manifest[1].name)

    def test_resolve_2(self):
        self.dev_repo.add("foo", version="1")
        self.dev_repo.add("goo", version="1")
        self.dev_repo.add("bar", version="1", variants=[["foo"], ["goo"]])

        self.installer.resolve("bar")

        manifest = self.installer.manifest()
        self.assertEqual("foo-1", manifest[0].name)
        self.assertEqual(("bar-1", 0), (manifest[1].name, manifest[1].index))
        self.assertEqual("goo-1", manifest[2].name)
        self.assertEqual(("bar-1", 1), (manifest[3].name, manifest[3].index))

    def test_resolve_with_os(self):
        # this test requires REP-002: requirement late expansion feature
        self.dev_repo.add("foo", version="1", variants=[["os-*"]])
        self.installer.resolve("foo")

        manifest = self.installer.manifest()
        self.assertTrue(manifest[-2].name.startswith("os-"))
        self.assertEqual(("foo-1", 0), (manifest[-1].name, manifest[-1].index))

    def test_resolve_with_variants(self):
        self.dev_repo.add("python", version="2.7")
        self.dev_repo.add("python", version="3.7")
        self.dev_repo.add("foo", variants=[["python-2"], ["python-3"]])
        self.installer.resolve("foo")

        manifest = self.installer.manifest()
        self.assertEqual(4, len(manifest))
        for req in manifest:
            self.assertEqual(self.installer.NotInstalled, req.status)
