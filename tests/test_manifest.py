
import os
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch
from deliver.api import PackageLoader, PackageInstaller
from deliver.repository import DevPkgRepo
from deliver.lib import temp_env, override_config
from tests.util import TestBase, require_directives
from tests.ghostwriter import DeveloperRepository, early, late, building


class TestManifest(TestBase):

    def setUp(self):
        root = tempfile.mkdtemp(prefix="rez_deliver_test_")
        install_path = os.path.join(root, "install")
        release_path = os.path.join(root, "release")
        dev_repo_path = os.path.join(root, "developer")

        self.root = root
        self.install_path = install_path
        self.release_path = release_path
        self.dev_repo_path = dev_repo_path
        self.dev_repo = DeveloperRepository(dev_repo_path)
        self.settings = {
            "packages_path": [install_path, release_path],
            "local_packages_path": install_path,
            "release_packages_path": release_path,
            "plugins": {
                "command": {"deliver": {
                    "dev_repository_roots": [dev_repo_path]
                }}
            }
        }
        super(TestManifest, self).setUp()

        PackageLoader.clear_instance()
        self.installer = PackageInstaller(PackageLoader())

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

    def _run_install(self):
        # ensure module `deliver.install` can be accessed in subprocess.
        #
        import deliver
        PYTHONPATH = os.pathsep.join([
            os.path.dirname(deliver.__path__[0]),
            os.getenv("PYTHONPATH") or ""
        ])

        with temp_env("PYTHONPATH", PYTHONPATH), \
                self.dump_config_yaml(self.root):
            self.installer.run()

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

    def test_resolve_with_req_expansion(self):
        # need to install bar first so the wildcard request can be expanded.
        installed_repo = DeveloperRepository(self.install_path)
        installed_repo.add("bar", version="1.5")
        installed_repo.add("bar", version="2.0")

        self.dev_repo.add("foo", version="1", variants=[["bar-**"]])
        self.installer.resolve("foo")

        manifest = self.installer.manifest()
        self.assertTrue(manifest[0].name == "bar-2.0")
        self.assertEqual(("foo-1", 0), (manifest[1].name, manifest[1].index))

    @require_directives()
    def test_resolve_with_req_directive(self):
        # need to install bar first so the request can be expanded.
        installed_repo = DeveloperRepository(self.install_path)
        installed_repo.add("bar", version="1.5")
        installed_repo.add("bar", version="2.0")

        self.dev_repo.add("foo", version="1", variants=[["bar-1//harden"]])
        self.installer.resolve("foo")

        manifest = self.installer.manifest()
        self.assertTrue(manifest[0].name == "bar-1.5")
        self.assertEqual(("foo-1", 0), (manifest[1].name, manifest[1].index))

    @require_directives()
    def test_resolve_with_req_directive_but_no_pre_installed(self):
        self.dev_repo.add("bar", version="1.5")
        self.dev_repo.add("bar", version="2.0")
        self.dev_repo.add("foo", version="1", variants=[["bar-1//harden"]])
        self.installer.resolve("foo")

        manifest = self.installer.manifest()
        self.assertTrue(manifest[0].name == "bar-1.5")
        self.assertEqual(("foo-1", 0), (manifest[1].name, manifest[1].index))

    def test_resolve_with_variants(self):
        self.dev_repo.add("python", version="2.7")
        self.dev_repo.add("python", version="3.7")
        self.dev_repo.add("foo", variants=[["python-2"], ["python-3"]])
        self.installer.resolve("foo")

        manifest = self.installer.manifest()
        self.assertEqual(4, len(manifest))
        for req in manifest:
            self.assertEqual(self.installer.Ready, req.status)

    def test_resolve_early_build(self):

        @early()
        def bar_requires():
            if building:
                return []
            else:
                return ["!ehh"]

        self.dev_repo.add("foo", requires=["bar", "ehh"])
        self.dev_repo.add("bar", requires=bar_requires)
        self.dev_repo.add("ehh")

        self.installer.resolve("foo")
        manifest = self.installer.manifest()
        self.assertEqual(3, len(manifest))
        for req in manifest:
            self.assertEqual(self.installer.Ready, req.status)

    def test_resolve_early_build_variants(self):

        @early()
        def foo_requires():
            if building:
                if build_variant_index == 0:  # x
                    return ["a"]
                elif build_variant_index == 1:  # y
                    return ["b"]
            else:
                return []

        self.dev_repo.add("foo", requires=foo_requires, variants=[["x"], ["y"]])
        self.dev_repo.add("x")
        self.dev_repo.add("y")
        self.dev_repo.add("a")
        self.dev_repo.add("b")

        self.installer.resolve("foo")
        manifest = self.installer.manifest()

        a = next((q for q in manifest if q.name == "a"), None)
        self.assertIsNotNone(a)
        b = next((q for q in manifest if q.name == "b"), None)
        self.assertIsNotNone(b)

        self.assertEqual(6, len(manifest))
        for req in manifest:
            self.assertEqual(self.installer.Ready, req.status)

    def test_resolve_late_build_variants(self):
        # in this test, `build_requires` is used because `requires` won't be
        # visited by variant but package.
        @late()
        def foo_build_requires():
            if this.is_variant:
                if this.index == 0:  # x
                    return ["a"]
                elif this.index == 1:  # y
                    return ["b"]
            else:
                return []

        self.dev_repo.add("foo",
                          build_requires=foo_build_requires,
                          variants=[["x"], ["y"]])
        self.dev_repo.add("x")
        self.dev_repo.add("y")
        self.dev_repo.add("a")
        self.dev_repo.add("b")

        self.installer.resolve("foo")
        manifest = self.installer.manifest()

        a = next((q for q in manifest if q.name == "a"), None)
        self.assertIsNotNone(a)
        b = next((q for q in manifest if q.name == "b"), None)
        self.assertIsNotNone(b)

        self.assertEqual(6, len(manifest))
        for req in manifest:
            self.assertEqual(self.installer.Ready, req.status)

    def test_resolve_with_installed(self):
        installed_repo = DeveloperRepository(self.install_path)
        installed_repo.add("bar")
        installed_repo.add("foo", version="1", variants=[["bar"]])

        self.dev_repo.add("foo", version="2", variants=[["bar"]])

        self.installer.resolve("foo")
        manifest = self.installer.manifest()
        foo_request = next(r for r in manifest if r.name == "foo-2")
        self.assertEqual(self.installer.Ready, foo_request.status)

    def test_resolve_with_external(self):
        # the external one, not exists in developer package repository
        installed_repo = DeveloperRepository(self.install_path)
        installed_repo.add("ext", requires=["bar"])

        self.dev_repo.add("foo", requires=["ext"], variants=[["egg"], ["nut"]])
        self.dev_repo.add("bar")
        self.dev_repo.add("egg")
        self.dev_repo.add("nut")

        self.installer.resolve("foo")
        manifest = self.installer.manifest()

        self.assertEqual(6, len(manifest))
        for req in manifest:
            if req.name == "ext":
                self.assertEqual(self.installer.External, req.status)
            else:
                self.assertEqual(self.installer.Ready, req.status)

    def test_buildtime_variants(self):
        @early()
        def variants():
            from rez import packages
            bindings = ["pyqt", "pyside"]
            return [[binding] for binding in bindings
                    if packages.get_latest_package_from_string(binding)]

        self.dev_repo.add("shim", build_command=False, variants=variants)
        self.dev_repo.add("pyqt", build_command=False)
        self.dev_repo.add("pyside", build_command=False)

        self.installer.resolve("shim[1]")
        manifest = self.installer.manifest()
        self.assertEqual(manifest[0].name, "pyside")
        self.assertEqual(manifest[1].index, 1)

        self._run_install()

    def test_minimum_require(self):
        self.dev_repo.add("a", build_command=False)
        self.dev_repo.add("b", build_command=False)
        self.dev_repo.add("foo", variants=[["a"], ["b"]], build_command=False)
        self.dev_repo.add("bar", requires=["foo"], build_command=False)

        self.installer.resolve("bar")
        manifest = self.installer.manifest()
        self.assertEqual(3, len(manifest))
        self.assertEqual(["b", "foo", "bar"], [r.name for r in manifest])

        self.installer.resolve("foo[1]")
        self._run_install()

        self.installer.resolve("bar")
        manifest = self.installer.manifest()

        self.assertEqual(3, len(manifest))
        self.assertEqual(["b", "foo", "bar"], [r.name for r in manifest])

        self.assertEqual(self.installer.Installed, manifest[0].status)
        self.assertEqual(self.installer.Installed, manifest[1].status)
        self.assertEqual(self.installer.Ready, manifest[2].status)

    def test_skip_non_addition_requires_on_load(self):
        self.dev_repo.add("foo", version="1",
                          requires=["~bar==1"], build_command=False)
        self.dev_repo.add("bar", version="1",
                          requires=["foo-1"], build_command=False)

        self.installer.resolve("foo")
        manifest = self.installer.manifest()
        self.assertEqual(1, len(manifest))
        self.assertEqual(["foo-1"], [r.name for r in manifest])

        self.installer.resolve("bar")
        manifest = self.installer.manifest()
        self.assertEqual(2, len(manifest))
        self.assertEqual(["foo-1", "bar-1"], [r.name for r in manifest])

    @patch.object(DevPkgRepo, "_git_tags", return_value=["1.0.0"])
    def test_git_versioned_package(self, mock_git_tags):
        @early()
        def version():
            import os
            return os.getenv("REZ_DELIVER_PKG_PAYLOAD_VER", "unknown")
        git_url = ".../davidlatwe/bar.git"

        self.dev_repo.add("bar", version=version, git_url=git_url)

        self.installer.resolve("bar")
        manifest = self.installer.manifest()

        self.assertEqual(self.installer.Ready, manifest[0].status)
        self.assertEqual("bar-1.0.0", manifest[0].name)

    @patch.object(DevPkgRepo, "_git_tags", return_value=["1.0.0"])
    def test_expanding_git_versioned_package(self, mock_git_tags):
        @early()
        def version():
            import os
            return os.getenv("REZ_DELIVER_PKG_PAYLOAD_VER", "unknown")
        git_url = ".../davidlatwe/bar.git"

        self.dev_repo.add("bar", version=version, git_url=git_url)
        self.dev_repo.add("foo", requires=["bar-**"])

        self.installer.resolve("foo")
        manifest = self.installer.manifest()
        self.assertEqual(2, len(manifest))

        self.assertEqual("bar-1.0.0", manifest[0].name)

    def test_expanding_maker_package(self):
        self.dev_repo.add("a", requires=["platform-*"])

        self.installer.resolve("a")
        manifest = self.installer.manifest()
        self.assertEqual(2, len(manifest))

    def test_variants_installed_separately(self):
        self.dev_repo.add("foo", version="1", build_command=False)
        self.dev_repo.add("foo", version="2", build_command=False)
        self.dev_repo.add("bar", version="5", build_command=False,
                          variants=[["foo-1"], ["foo-2"]])

        self.installer.resolve("foo-1", "foo-2", "bar[0]")
        self._run_install()

        self.installer.resolve("bar")
        manifest = self.installer.manifest()

        self.assertEqual("bar-5", manifest[-1].name)
        self.assertEqual(self.installer.Ready, manifest[-1].status)

    def test_requiring_unversioned_dev_package(self):
        # foo is unversioned
        self.dev_repo.add("foo", build_command=False)
        self.dev_repo.add("bar", build_command=False,
                          version="1", requires=["foo"])

        # manifesting dev pkgs under env that forbids unversioned package
        with override_config({"allow_unversioned_packages": False}):
            self.installer.resolve("bar")
            manifest = self.installer.manifest()

        # despite production env forbids unversioned package, but the dev
        # package repo should not be limited
        self.assertEqual("bar-1", manifest[-1].name)
        self.assertEqual(self.installer.Ready, manifest[-1].status)


if __name__ == "__main__":
    unittest.main()
