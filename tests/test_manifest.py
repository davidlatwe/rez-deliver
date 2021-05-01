
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

        dev_repo = DevRepoManager()
        installer = PackageInstaller(dev_repo)
        installer.resolve("bar")

        manifest = installer.manifest()
        self.assertEqual("foo-1", manifest[0].name)
        self.assertEqual("bar-1", manifest[1].name)

    def test_resolve_2(self):
        self.dev_repo.add("foo", version="1")
        self.dev_repo.add("goo", version="1")
        self.dev_repo.add("bar", version="1", variants=[["foo"], ["goo"]])

        dev_repo = DevRepoManager()
        installer = PackageInstaller(dev_repo)
        installer.resolve("bar")

        manifest = installer.manifest()
        self.assertEqual("foo-1", manifest[0].name)
        self.assertEqual(("bar-1", 0), (manifest[1].name, manifest[1].index))
        self.assertEqual("goo-1", manifest[2].name)
        self.assertEqual(("bar-1", 1), (manifest[3].name, manifest[3].index))
