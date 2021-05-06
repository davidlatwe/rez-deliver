"""A memory repository for storing build-time variants
"""
from rezplugins.package_repository.memory import MemoryPackageRepository


class BuildTimePackageRepository(MemoryPackageRepository):
    """
    """

    def __init__(self, *args, **kwargs):
        super(BuildTimePackageRepository, self).__init__(*args, **kwargs)
        self.patch_rez()

    @classmethod
    def name(cls):
        return "buildtime"

    @classmethod
    def patch_rez(cls):
        """"""
        from rez.packages import Variant, Package

        def iter_variants(self):
            is_buildtime_mem = self.repository.name() == "buildtime"
            parent = None if is_buildtime_mem else self

            for variant in self.repository.iter_variants(self.resource):
                yield Variant(variant, context=self.context, parent=parent)

        Package.iter_variants = iter_variants

    def iter_variants(self, package_resource):
        data = package_resource.validated_data()
        variants = (data.get("_build_time_variant_resources")
                    or package_resource.iter_variants())
        for variant in variants:
            yield variant

    # for keeping my linter quiet
    _imp_method_ = (lambda self, *args, **kwargs: None)
    ignore_package = _imp_method_
    unignore_package = _imp_method_
    remove_package = _imp_method_
    remove_ignored_since = _imp_method_
    install_variant = _imp_method_
    get_package_payload_path = _imp_method_


def register_plugin():
    return BuildTimePackageRepository
