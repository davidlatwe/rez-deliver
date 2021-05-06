
from rezplugins.package_repository.memory import MemoryPackageRepository


def patch_rez():
    from rez.packages import Variant, Package

    def iter_variants(self):
        is_vmem = self.repository.name() == "vmemory"
        parent = None if is_vmem else self

        for variant in self.repository.iter_variants(self.resource):
            yield Variant(variant, context=self.context, parent=parent)

    Package.iter_variants = iter_variants


patch_rez()


class VMemoryPackageRepository(MemoryPackageRepository):

    @classmethod
    def name(cls):
        return "vmemory"

    def iter_variants(self, package_resource):
        data = package_resource.validated_data()
        variants = (data.get("re_evaluated_variants")
                    or package_resource.iter_variants())
        for variant in variants:
            yield variant


def register_plugin():
    return VMemoryPackageRepository
