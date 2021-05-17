"""A module that meant to find/resolve/install developer packages

Example:
    # setup rez-deliver config so it could find developer package
    >>> installer = PackageInstaller()
    >>> installer.resolve("foo")
    >>> installer.manifest()
    >>> installer.run()

"""
import os
import re
import subprocess
from functools import partial
from contextlib import contextmanager

from rez.config import config as rezconfig
from rez.utils.formatting import PackageRequest
from rez.resolved_context import ResolvedContext
from rez.developer_package import DeveloperPackage
from rez.packages import Package, get_latest_package
from rez.exceptions import PackageFamilyNotFoundError, PackageNotFoundError

from deliver.repository import PackageLoader
from deliver.exceptions import RezDeliverRequestError, RezDeliverFatalError
from deliver.lib import (
    os_chdir,
    expand_path,
    override_config,
    clear_repo_cache,
)


class Required(object):
    __slots__ = ("name", "index", "source", "status", "depended")

    def __init__(self, name, index):
        self.name = name
        self.index = index
        self.source = None
        self.status = None
        self.depended = []

    @classmethod
    def get(cls, name, index=-1, from_=None):
        from_ = from_ or []
        try:
            req_id = from_.index((name, index))
        except ValueError:
            return cls(name, index)
        else:
            return from_[req_id]

    def __eq__(self, other):
        return other == (self.name, self.index)

    def __repr__(self):
        return "Required(name='%s', index=%r, status=%s)" \
               % (self.name,
                  self.index,
                  PackageInstaller.StatusMapStr[self.status])


variant_index_regex = re.compile(r"(.+)\[([0-9]+)]")


class RequestSolver(object):
    """Package installation manifest resolver"""

    Ready = 1
    Installed = 2
    External = 3
    ResolveFailed = 4
    PackageNotFound = 5

    StatusMapStr = {
        Ready: "ready",
        Installed: "installed",
        External: "external",
        ResolveFailed: "failed",
        PackageNotFound: "missing",
    }

    def __init__(self, loader=None):
        self.loader = loader or PackageLoader()
        self._requirements = list()
        self._conflicts = list()
        self.__depended = None

    @property
    def installed_packages_path(self):
        return rezconfig.packages_path

    def reset(self):
        """Reset resolved manifest"""
        self._requirements = []
        self.__depended = None

    def resolve(self, *requests):
        """Resolve multiple requests and their dependencies recursively

        Different from `resolve_one`, this method can take multiple requests,
        and the request string can have variant index syntax, and conflict or
        weak request, for example:

            >>> solver = RequestSolver()
            >>> solver.resolve("foo", "bar[0]", "egg-1.5[1]", "~ehh-0.5")

        And, unlike `resolve_one` will continue adding resolved requires into
        manifest list until `reset` is called, this method will reset the
        manifest on each call.

        Call `manifest()` to show resolved requirements.

        Args:
            *requests (str): Package request string, conflict or weak request
                is also acceptable here.

        Returns:
            None

        """
        self.reset()
        requests_ = []
        conflicts = []

        for request in requests:
            # parse variant index
            result = variant_index_regex.split(request)
            index = None
            if not result[0]:
                request, index = result[1:3]
                index = int(index)
            # filtering requests
            _request = PackageRequest(request)
            if _request.conflict:
                conflicts.append(request)
            else:
                requests_.append((_request, index))
        # resolve
        with self.conflicts(*conflicts):
            for _request, index in requests_:
                self._resolve_one(_request, variant_index=index)

    def resolve_one(self, request, index=None):
        """Resolve one request and it's dependencies recursively

        Unlike `resolve`, this method can only accept one request, and cannot
        take conflict or weak request. But will continue appending result to
        manifest list until `reset` is called.

        For adding conflict or weak request, use `conflicts` context method,
        for example:
            >>> solver = RequestSolver()
            >>> with solver.conflicts("~ehh-0.5", "!bar"):
            ...     solver.resolve_one("foo")
            ...     solver.resolve_one("egg-1.5", index=1)

        Call `manifest()` to show resolved requirements.

        Args:
            request (str): Package request string
            index (int): Variant index, optional.

        Returns:
            None

        """
        _request = PackageRequest(request)
        if _request.conflict:
            raise RezDeliverRequestError(
                "Should not pass conflict or weak requirement here, "
                "use `with conflicts()` instead."
            )
        else:
            self._resolve_one(_request, variant_index=index)

    @contextmanager
    def conflicts(self, *requests):
        """A context for adding conflict or weak requirements before resolve

        The given conflict or weak requests will join each resolve in context,
        and will be dropped on exit.

        Args:
            *requests (str): Package conflict or weak request string

        Returns:
            None

        """
        conflicts = []

        for request in requests:
            request = PackageRequest(request)
            if not request.conflict:
                raise RezDeliverRequestError(
                    "Only conflict or weak requirement is acceptable here, "
                    "use `resolve() or resolve_one()` for regular request."
                )
            else:
                conflicts.append(request)

        self._conflicts = conflicts
        yield

        self._conflicts = []

    def manifest(self):
        """Return requested result

        Returns:
            list: A list of `Required` object

        """
        return self._requirements[:]

    def _find_installed(self, request):
        paths = self.installed_packages_path
        return get_latest_package(name=request.name,
                                  range_=request.range_,
                                  paths=paths)

    def _zip_longest_variants(self, this, that):
        """Iterate two packages variants via `variant_requires`

        Like `itertools.zip_longest` that will zip multiple iterables, this
        is iterating package variants and zip with `variant_requires` that
        matched.

        Args:
            this: developer package, or None
            that: installed package, or None

        Yields: `Variant` or None, `Variant` or None

        """
        r = (lambda requires: " ".join(str(_) for _ in requires))

        this_vans_ = list(this.iter_variants()) if this else []
        that_vans_ = {
            r(v.variant_requires): v for v in that.iter_variants()
        } if that else dict()

        longest = max(len(this_vans_), len(that_vans_))
        for i in range(longest):
            if this_vans_ and that_vans_:
                this_van = this_vans_.pop(0)
                that_van = that_vans_.pop(r(this_van.variant_requires), None)

            elif this_vans_ and not that_vans_:
                this_van = this_vans_.pop(0)
                that_van = None

            elif not this_vans_ and that_vans_:
                this_van = None
                _, that_van = that_vans_.popitem()

            else:
                return

            yield this_van, that_van

    def _resolve_one(self, request, variant_index=None):
        """Resolve one request and it's dependencies recursively

        Args:
            request (PackageRequest): Package request object
            variant_index (int): Variant index, optional.

        Returns:
            None

        """
        # find latest package in requested range
        developer = self.loader.find(request, load_dependency=True)
        installed = self._find_installed(request)

        if developer is None and installed is None:
            # package not found
            requested = Required.get(request, from_=self._requirements)
            requested.status = self.PackageNotFound
            self._append(requested)

            return

        status = None

        if developer and installed:
            # prefer dev package if version is different
            if developer.version > installed.version:
                installed = None
                status = self.Ready
            elif developer.version < installed.version:
                developer = None
                status = self.Installed
            else:
                # same version, keep both
                status = self.Ready

        if developer:
            name = developer.qualified_name
            source = developer.data["__source__"]
            status = status or self.Ready
        else:
            name = installed.qualified_name
            source = installed.uri
            status = status or self.External

        # Only if developer and installed package have same version, they
        #   both get kept and iterated together. The reason for this is
        #   because installed package may have different variant sets than
        #   the developer one, even they are same version. Not likely, but
        #   could happen.
        for d_van, i_van in self._zip_longest_variants(developer, installed):
            variant = i_van or d_van
            if variant_index is not None and variant_index != variant.index:
                continue

            if status == self.Ready and variant is i_van:
                status = self.Installed

            requested = Required.get(name, variant.index)
            requested.source = source
            requested.status = status

            if self.__depended:
                requested.depended.append(self.__depended)

            # resolve variant's requirement
            #
            if status == self.Ready:
                # re-evaluate
                if developer is None or variant is i_van:
                    raise RezDeliverFatalError(
                        "Fatal Error: Request status is 'Ready' but developer "
                        "package is not used, this is a bug."
                    )
                if source != self.loader.maker_root:
                    variant = self._re_evaluate_variant(variant) or variant
                else:
                    # no need to re-evaluate maker package in build.
                    pass
            else:
                # resolving requirements for installed variant which is not
                #   from a developer package, so cannot be re-evaluated.
                pass

            variant_requires = variant.get_requires(
                build_requires=True,
                private_build_requires=True
            )
            try:
                context = self._build_context(variant_requires)
            except (PackageFamilyNotFoundError, PackageNotFoundError) as e:
                print(e)
                requested.status = self.ResolveFailed

            else:
                if not context.success:
                    context.print_info()
                    requested.status = self.ResolveFailed
                else:
                    for pkg in context.resolved_packages:
                        request_id = (pkg.qualified_package_name, pkg.index)
                        if request_id in self._requirements:
                            continue
                        _request = PackageRequest(pkg.qualified_package_name)
                        self.__depended = requested
                        self._resolve_one(request=_request,
                                          variant_index=pkg.index)
            self._append(requested)
        self.__depended = None  # reset

    def _build_context(self, variant_requires):
        paths = self.installed_packages_path + self.loader.paths
        requests = variant_requires + self._conflicts

        return ResolvedContext(
            requests,
            building=True,
            package_paths=paths,
            package_load_callback=self._re_evaluate_variant_callback
        )

    def _re_evaluate_variant_callback(self, package):
        """Package load callback in context resolving time

        When resolving context for building package which may have dependency
        that is another developer package which must be re-evaluated as in
        build so to get the correct build-requires.

        """
        def iter_variants(_self):
            for variant in Package.iter_variants(_self):
                yield (
                    self._re_evaluate_variant(variant, context=_self.context)
                    or variant
                )
        # patch
        package.iter_variants = partial(iter_variants, package)

    def _re_evaluate_variant(self, variant, context=None):
        """Re-evaluate package variant as in build-time
        """
        filepath = variant.parent.data.get("__source__")
        if not filepath or not os.path.isfile(filepath):
            return

        package = DeveloperPackage(variant.parent.resource)
        package.filepath = filepath

        pkg_path = os.path.dirname(filepath)
        with override_config(self.loader.settings), os_chdir(pkg_path):
            re_evaluated_package = package.get_reevaluated({
                "building": True,
                "build_variant_index": variant.index or 0,
                "build_variant_requires": variant.variant_requires
            })

        re_evaluated_package.set_context(context)
        re_evaluated_variant = re_evaluated_package.get_variant(variant.index)

        # Ensure all requires are loaded after re-evaluated
        for request in re_evaluated_variant.get_requires(
            build_requires=True, private_build_requires=True
        ):
            if isinstance(request, PackageRequest):
                request = request.name
            self.loader.load(request, dependency=True)

        return re_evaluated_variant

    def _append(self, requested):
        if requested not in self._requirements:
            self._requirements.append(requested)


class PackageInstaller(RequestSolver):
    """Extended from `RequestSolver` to execute installation"""

    def __init__(self, loader=None):
        super(PackageInstaller, self).__init__(loader=loader)
        self.release = False

    @property
    def installed_packages_path(self):
        c, r = rezconfig, self.release
        return c.nonlocal_packages_path if r else c.packages_path

    @property
    def deploy_path(self):
        c, r = rezconfig, self.release
        return c.release_packages_path if r else c.local_packages_path

    def target(self, path):
        """
        Only set to 'release' when the `path` is release_packages_path.
        """
        path = expand_path(path)
        release = path == expand_path(rezconfig.release_packages_path)

        print("Mode: %s" % ("release" if release else "install"))
        self.release = release
        self.loader.release = release
        self.reset()

    def run(self):
        for _ in self.run_iter():
            pass

    def run_iter(self):
        for requested in self._requirements:
            if requested.status != self.Ready:
                # TODO: prompt warning if the status is `ResolveFailed`
                continue

            if requested.source == self.loader.maker_root:
                self._make(requested.name,
                           variant=requested.index)
            else:
                self._build(os.path.dirname(requested.source),
                            variant=requested.index)

            yield requested

    def _make(self, name, variant=None):
        deploy_path = self.deploy_path
        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        made_pkg = self.loader.get_maker_made_package(name)
        made_pkg.__install__(deploy_path, variant)

        clear_repo_cache(deploy_path)

    def _build(self, src_dir, variant=None):
        variant_cmd = [] if variant is None else ["--variants", str(variant)]
        deploy_path = self.deploy_path
        env = os.environ.copy()

        if not os.path.isdir(deploy_path):
            os.makedirs(deploy_path)

        if self.release:
            env["REZ_RELEASE_PACKAGES_PATH"] = deploy_path
            args = ["rez-release"] + variant_cmd
            self._run_command(args, cwd=src_dir, env=env)
        else:
            env["REZ_LOCAL_PACKAGES_PATH"] = deploy_path
            args = ["rez-build", "--install"] + variant_cmd
            self._run_command(args, cwd=src_dir)

        clear_repo_cache(deploy_path)

    def _run_command(self, cmd_args, **kwargs):
        print("Running command:\n    %s\n" % cmd_args)
        subprocess.check_call(cmd_args, **kwargs)
