from __future__ import annotations

import dataclasses
import functools
import subprocess
import tomllib
from collections.abc import (
    Iterable,
)
from pathlib import Path
from typing import (
    Optional,
    Self,
    TypeVar,
)

import dacite

from . import dataclasses_extra
from .debian import PackageRelationGroup


_dacite_config = dacite.Config(
    cast=[
        PackageRelationGroup,
        Path,
    ],
    strict=True,
)


@dataclasses.dataclass
class ConfigBuild:
    cflags: Optional[str] = None
    compiler: Optional[str] = None
    compiler_gnutype: Optional[str] = None
    compiler_gnutype_compat: Optional[str] = None
    config: list[Path] = dataclasses.field(default_factory=list)
    config_default: list[Path] = dataclasses.field(default_factory=list, repr=False)
    enable_signed: Optional[bool] = None
    enable_vdso: Optional[bool] = None
    kernel_file: Optional[str] = None
    kernel_stem: Optional[str] = None


@dataclasses.dataclass
class ConfigDescription:
    hardware: Optional[str] = None
    hardware_long: Optional[str] = None
    parts: list[str] = dataclasses.field(default_factory=list)
    short: dict[str, str] = dataclasses.field(default_factory=dict)
    long: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class ConfigPackages:
    docs: Optional[bool] = dataclasses.field(default=None, metadata={'default': True})
    installer: Optional[bool] = dataclasses.field(default=None, metadata={'default': False})
    libc_dev: Optional[bool] = dataclasses.field(default=None, metadata={'default': True})
    meta: Optional[bool] = dataclasses.field(default=None, metadata={'default': True})
    source: Optional[bool] = dataclasses.field(default=None, metadata={'default': True})
    tools_unversioned: Optional[bool] = dataclasses.field(default=None, metadata={'default': True})
    tools_versioned: Optional[bool] = dataclasses.field(default=None, metadata={'default': True})


@dataclasses.dataclass
class ConfigRelationsSingle:
    depends: list[PackageRelationGroup] = dataclasses.field(default_factory=list)
    recommends: list[PackageRelationGroup] = dataclasses.field(default_factory=list)
    suggests: list[PackageRelationGroup] = dataclasses.field(default_factory=list)
    breaks: list[PackageRelationGroup] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ConfigRelations:
    image: ConfigRelationsSingle = dataclasses.field(default_factory=ConfigRelationsSingle)


@dataclasses.dataclass
class ConfigDebianarchDefs:
    __arch: Optional[str] = dataclasses.field(default=None, init=False)

    def __post_init_defs__(self, parent: ConfigDebianarch) -> None:
        self.__arch = parent.name

    @staticmethod
    @functools.cache
    def __dpkg_architecture(arch: str, query: str) -> str:
        return subprocess.check_output(
            [
                'dpkg-architecture',
                '-f',
                '-a', arch,
                '-q', query,
            ],
            stderr=subprocess.DEVNULL,
            encoding='ascii',
        ).strip()

    @property
    def gnutype(self) -> str:
        assert self.__arch is not None
        return self.__dpkg_architecture(self.__arch, 'DEB_HOST_GNU_TYPE')

    @property
    def gnutype_package(self) -> str:
        return self.gnutype.replace("_", "-")

    @property
    def multiarch(self) -> str:
        assert self.__arch is not None
        return self.__dpkg_architecture(self.__arch, 'DEB_HOST_MULTIARCH')


@dataclasses.dataclass
class ConfigFlavourDefs:
    is_default: bool = False
    is_quick: bool = False


@dataclasses.dataclass
class ConfigBase:
    name: str
    enable: bool = True
    path: Optional[Path] = None

    build: ConfigBuild = dataclasses.field(default_factory=ConfigBuild)
    description: ConfigDescription = dataclasses.field(default_factory=ConfigDescription)
    packages: ConfigPackages = dataclasses.field(default_factory=ConfigPackages)
    relations: ConfigRelations = dataclasses.field(default_factory=ConfigRelations)

    def __post_init_hierarchy__(self, path: Path) -> None:
        '''
        Setup path and default config in the complete hierarchy
        '''
        self.path = path
        self.build.config_default = [path / 'config']

    def read_replace(self, bases: Iterable[Path], path: Path) -> Self:
        '''
        Read defines.toml at specified path in all bases and merged them
        '''
        config = self

        try:
            for base in bases:
                if (file := base / path / 'defines.toml').exists():
                    with file.open('rb') as f:
                        data = dataclasses.asdict(self) | tomllib.load(f)

                    config = dataclasses_extra.merge(config, dacite.from_dict(
                        data_class=self.__class__,
                        data=data,
                        config=_dacite_config,
                    ))
        except tomllib.TOMLDecodeError as e:
            raise RuntimeError(f'{file}: {e}') from None

        return config


ConfigT = TypeVar('ConfigT', bound=ConfigBase)


@dataclasses.dataclass
class Config(ConfigBase):
    # Disable basic fields
    name: str = dataclasses.field(init=False, repr=False, default='')
    enable: bool = dataclasses.field(init=False, repr=False, default=True)

    featureset: list[ConfigFeatureset] = dataclasses.field(
        default_factory=list, metadata={'merge': 'assoclist'},
    )
    kernelarch: list[ConfigKernelarch] = dataclasses.field(
        default_factory=list, metadata={'merge': 'assoclist'},
    )

    def __post_init_hierarchy__(self, path: Path) -> None:
        super().__post_init_hierarchy__(path)

        for featureset in self.featureset:
            featureset.__post_init_hierarchy_featureset__(
                Path(f'featureset-{featureset.name}'),
                None,
            )
        for kernelarch in self.kernelarch:
            kernelarch.__post_init_hierarchy__(
                Path(f'kernelarch-{kernelarch.name}'),
            )

    @property
    def merged(self) -> ConfigMerged:
        return ConfigMerged(root=self)

    @classmethod
    def read_orig(cls, bases: Iterable[Path]) -> Config:
        '''
        Read defines.toml at the root in all bases and merge them
        '''
        config = cls()
        found = False

        try:
            for base in bases:
                if (file := base / 'defines.toml').exists():
                    with file.open('rb') as f:
                        data = tomllib.load(f)
                    found = True

                    config = dataclasses_extra.merge(config, dacite.from_dict(
                        data_class=cls,
                        data=data,
                        config=_dacite_config,
                    ))
        except (tomllib.TOMLDecodeError, dacite.exceptions.UnexpectedDataError) as e:
            raise RuntimeError(f'{file}: {e}') from None
        if not found:
            raise FileNotFoundError('Did not find defines.toml in any directory')

        config.__post_init_hierarchy__(Path())

        config.featureset = list(cls._read_hierarchy(bases, config.featureset))
        config.kernelarch = list(cls._read_hierarchy(bases, config.kernelarch))
        for kernelarch in config.kernelarch:
            kernelarch.debianarch = list(cls._read_hierarchy(bases, kernelarch.debianarch))

        config.__post_init_hierarchy__(Path())

        return config

    @classmethod
    def _read_hierarchy(
        cls, bases: Iterable[Path], orig: Iterable[ConfigT],
    ) -> Iterable[ConfigT]:
        for i in orig:
            try:
                assert i.path is not None
                yield i.read_replace(bases, i.path)
            except FileNotFoundError:
                yield i


@dataclasses.dataclass
class ConfigKernelarch(ConfigBase):
    debianarch: list[ConfigDebianarch] = dataclasses.field(
        default_factory=list, metadata={'merge': 'assoclist'},
    )

    def __post_init_hierarchy__(self, path: Path) -> None:
        super().__post_init_hierarchy__(path)

        for debianarch in self.debianarch:
            debianarch.__post_init_hierarchy__(
                Path(debianarch.name),
            )


@dataclasses.dataclass
class ConfigDebianarch(ConfigBase):
    defs: ConfigDebianarchDefs = dataclasses.field(default_factory=ConfigDebianarchDefs)

    featureset: list[ConfigFeatureset] = dataclasses.field(
        default_factory=list, metadata={'merge': 'assoclist'},
    )
    flavour: list[ConfigFlavour] = dataclasses.field(
        default_factory=list, metadata={'merge': 'assoclist'},
    )

    def __post_init__(self) -> None:
        self.defs.__post_init_defs__(self)

    def __post_init_hierarchy__(self, path: Path) -> None:
        super().__post_init_hierarchy__(path)

        for featureset in self.featureset:
            featureset.__post_init_hierarchy_featureset__(
                Path(path / featureset.name),
                self,
            )

        for flavour in self.flavour:
            flavour.__post_init_hierarchy__(path)


@dataclasses.dataclass
class ConfigFeatureset(ConfigBase):
    flavour: list[ConfigFlavour] = dataclasses.field(default_factory=list)

    def __post_init_hierarchy__(self, path: Path) -> None:
        super().__post_init_hierarchy__(path)

        for flavour in self.flavour:
            flavour.__post_init_hierarchy__(path)

    def __post_init_hierarchy_featureset__(
        self,
        path: Path,
        debianarch: Optional[ConfigDebianarch],
    ) -> None:
        # If we have no flavours defined within a featureset, we copy it from debianarch
        if not self.flavour and debianarch:
            self.flavour = [
                ConfigFlavour(name=flavour.name, defs=flavour.defs)
                for flavour in debianarch.flavour
            ]

        if self.flavour:
            # XXX: Remove special case of name
            if self.name == 'none':
                flavour_default = [i for i in self.flavour if i.defs.is_default]
                flavour_quick = [i for i in self.flavour if i.defs.is_quick]

                if not flavour_quick:
                    flavour_quick = flavour_default or self.flavour[0:1]
                    flavour_quick[0].defs.is_quick = True

            # Flavours in other featuresets can never be default or quick
            else:
                for flavour in self.flavour:
                    flavour.defs.is_default = False
                    flavour.defs.is_quick = False

        self.__post_init_hierarchy__(path)


@dataclasses.dataclass
class ConfigFlavour(ConfigBase):
    defs: ConfigFlavourDefs = dataclasses.field(default_factory=ConfigFlavourDefs)

    def __post_init_hierarchy__(self, path: Path) -> None:
        self.path = path
        self.build.config_default = [path / f'config.{self.name}']


class ConfigMergedBase:
    _entries: list[ConfigBase]

    def __init__(self) -> None:
        self._entries = []

    @property
    def enable(self) -> bool:
        for entry in self._entries:
            if not entry.enable:
                return False
        return True

    @property
    def build(self) -> ConfigBuild:
        return dataclasses_extra.merge_default(
            ConfigBuild, *(i.build for i in self._entries)
        )

    @property
    def config(self) -> list[Path]:
        ret: list[Path] = []
        for entry in self._entries:
            ret += entry.build.config + entry.build.config_default
        return ret

    @property
    def description(self) -> ConfigDescription:
        return dataclasses_extra.merge_default(
            ConfigDescription, *(i.description for i in self._entries)
        )

    @property
    def packages(self) -> ConfigPackages:
        return dataclasses_extra.merge_default(
            ConfigPackages, *(i.packages for i in self._entries)
        )

    @property
    def relations(self) -> ConfigRelations:
        return dataclasses_extra.merge_default(
            ConfigRelations, *(i.relations for i in self._entries)
        )


class ConfigMerged(ConfigMergedBase):
    _root: Config

    def __init__(
        self, *,
        root: Optional[ConfigBase],
        **kw: Optional[ConfigBase],
    ) -> None:
        super().__init__(**kw)

        assert isinstance(root, Config)
        self._root = root
        self._entries.append(root)

    @property
    def root_featuresets(self) -> Iterable[ConfigMergedFeatureset]:
        for featureset in self._root.featureset:
            yield ConfigMergedFeatureset(
                root=self._root,
                root_featureset=None,
                kernelarch=None,
                debianarch=None,
                debianarch_flavour=None,
                featureset=featureset,
            )

    @property
    def kernelarchs(self) -> Iterable[ConfigMergedKernelarch]:
        for kernelarch in self._root.kernelarch:
            yield ConfigMergedKernelarch(
                root=self._root,
                kernelarch=kernelarch,
            )


class ConfigMergedKernelarch(ConfigMerged):
    _kernelarch: ConfigKernelarch

    def __init__(
        self, *,
        kernelarch: Optional[ConfigBase],
        **kw: Optional[ConfigBase],
    ) -> None:
        super().__init__(**kw)

        if kernelarch is not None:
            assert isinstance(kernelarch, ConfigKernelarch)
            self._kernelarch = kernelarch
            self._entries.append(kernelarch)

    @property
    def name(self) -> str:
        return self._kernelarch.name

    @property
    def name_kernelarch(self) -> str:
        return self._kernelarch.name

    @property
    def debianarchs(self) -> Iterable[ConfigMergedDebianarch]:
        for debianarch in self._kernelarch.debianarch:
            yield ConfigMergedDebianarch(
                root=self._root,
                kernelarch=self._kernelarch,
                debianarch=debianarch,
            )


class ConfigMergedDebianarch(ConfigMergedKernelarch):
    _debianarch: ConfigDebianarch

    def __init__(
        self, *,
        debianarch: Optional[ConfigBase],
        **kw: Optional[ConfigBase],
    ) -> None:
        super().__init__(**kw)

        if debianarch is not None:
            assert isinstance(debianarch, ConfigDebianarch)
            self._debianarch = debianarch
            self._entries.append(debianarch)

    @property
    def name(self) -> str:
        return self._debianarch.name

    @property
    def name_debianarch(self) -> str:
        return self._debianarch.name

    @property
    def defs_debianarch(self) -> ConfigDebianarchDefs:
        return self._debianarch.defs

    @property
    def featuresets(self) -> Iterable[ConfigMergedFeatureset]:
        root_featureset = {
            i.name: i
            for i in self._root.featureset
        }

        for featureset in self._debianarch.featureset:
            yield ConfigMergedFeatureset(
                root=self._root,
                root_featureset=root_featureset[featureset.name],
                kernelarch=self._kernelarch,
                debianarch=self._debianarch,
                debianarch_flavour=None,
                featureset=featureset,
            )


class ConfigMergedFeatureset(ConfigMergedDebianarch):
    _featureset: ConfigFeatureset
    _root_featureset: Optional[ConfigFeatureset] = None
    _debianarch_flavour: Optional[ConfigFlavour] = None

    def __init__(
        self, *,
        featureset: Optional[ConfigBase],
        root_featureset: Optional[ConfigBase],
        debianarch_flavour: Optional[ConfigBase],
        **kw: Optional[ConfigBase],
    ) -> None:
        super().__init__(**kw)

        if debianarch_flavour is not None:
            assert isinstance(debianarch_flavour, ConfigFlavour)
            self._debianarch_flavour = debianarch_flavour
            self._entries.append(debianarch_flavour)

        if root_featureset is not None:
            assert isinstance(root_featureset, ConfigFeatureset)
            self._root_featureset = root_featureset
            self._entries.append(root_featureset)

        if featureset is not None:
            assert isinstance(featureset, ConfigFeatureset)
            self._featureset = featureset
            self._entries.append(featureset)

    @property
    def name(self) -> str:
        return self._featureset.name

    @property
    def name_featureset(self) -> str:
        return self._featureset.name

    @property
    def flavours(self) -> Iterable[ConfigMergedFlavour]:
        debianarch_flavour = {
            i.name: i
            for i in self._debianarch.flavour
        }

        for flavour in self._featureset.flavour:
            yield ConfigMergedFlavour(
                root=self._root,
                root_featureset=self._root_featureset,
                kernelarch=self._kernelarch,
                debianarch=self._debianarch,
                debianarch_flavour=debianarch_flavour[flavour.name],
                featureset=self._featureset,
                flavour=flavour,
            )


class ConfigMergedFlavour(ConfigMergedFeatureset):
    _flavour: ConfigFlavour

    def __init__(
        self, *,
        flavour: Optional[ConfigBase],
        **kw: Optional[ConfigBase],
    ) -> None:
        super().__init__(**kw)

        if flavour is not None:
            assert isinstance(flavour, ConfigFlavour)
            self._flavour = flavour
            self._entries.append(flavour)

    @property
    def name(self) -> str:
        return self._flavour.name

    @property
    def name_flavour(self) -> str:
        return self._flavour.name

    @property
    def defs_flavour(self) -> ConfigFlavourDefs:
        return self._flavour.defs


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'dir',
        default=[Path('debian/config')],
        nargs='+',
        type=Path,
    )
    args = parser.parse_args()
    config = Config.read_orig(args.dir)
    merged = config.merged

#    from pprint import pprint
#    pprint(config)

    def print_indent(indent: int, s: str, *args: str) -> None:
        print(' ' * indent * 4 + s, *args)

    for kernelarch in merged.kernelarchs:
        print_indent(
            0,
            f'Kernelarch: {kernelarch.name}',
            f'enable={kernelarch.enable}',
        )

        for debianarch in kernelarch.debianarchs:
            print_indent(
                1,
                f'Debianarch: {debianarch.name}',
                f'enable={debianarch.enable}',
            )

            for featureset in debianarch.featuresets:
                print_indent(
                    2,
                    f'Featureset: {featureset.name}',
                    f'enable={featureset.enable}',
                )

                for flavour in featureset.flavours:
                    print_indent(
                        3,
                        f'Flavour: {flavour.name}',
                        f'enable={flavour.enable}',
                        f'is_default={flavour.defs_flavour.is_default}',
                    )
                    print_indent(4, f'Config: {" ".join(str(i) for i in flavour.config)}')

                else:
                    print()
