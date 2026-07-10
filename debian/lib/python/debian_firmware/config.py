import dataclasses
import pathlib
import re
import tomllib
from typing import Optional, Self

import dacite

from debian_linux.debian import PackageRelation


_dacite_config = dacite.Config(
    cast=[PackageRelation],
    strict=True,
)


@dataclasses.dataclass
class ConfigBase:
    uri: str
    links_excluded: list[str]
    files_unpackaged: list[str]


@dataclasses.dataclass
class ConfigEula:
    title: str
    text: str


@dataclasses.dataclass
class ConfigScripts:
    # Verbatim maintainer-script snippets, inserted between the shebang
    # and the #DEBHELPER# token by gencontrol.py.
    preinst: Optional[str] = None
    postinst: Optional[str] = None
    prerm: Optional[str] = None
    postrm: Optional[str] = None


@dataclasses.dataclass
class ConfigExtraFile:
    # A non-firmware file to install into the binary package.  source is
    # relative to the source tree; dest is relative to the package root.
    source: str
    dest: str


@dataclasses.dataclass
class ConfigPackage:
    name: str
    desc: str
    longdesc: str
    support: list[str] = dataclasses.field(default_factory=list)
    suggests: PackageRelation = dataclasses.field(default_factory=PackageRelation)
    recommends: PackageRelation = dataclasses.field(default_factory=PackageRelation)
    depends: PackageRelation = dataclasses.field(default_factory=PackageRelation)
    conflicts: PackageRelation = dataclasses.field(default_factory=PackageRelation)
    breaks: PackageRelation = dataclasses.field(default_factory=PackageRelation)
    replaces: PackageRelation = dataclasses.field(default_factory=PackageRelation)
    provides: PackageRelation = dataclasses.field(default_factory=PackageRelation)
    eula: Optional[ConfigEula] = None
    scripts: Optional[ConfigScripts] = None
    uri: Optional[str] = None
    files: list[str] = dataclasses.field(default_factory=list)
    files_excluded: list[str] = dataclasses.field(default_factory=list)
    extra_files: list[ConfigExtraFile] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class Config:
    # Disable basic fields
    name: str = dataclasses.field(init=False, repr=False, default='')
    enable: bool = dataclasses.field(init=False, repr=False, default=True)

    base: ConfigBase
    package: list[ConfigPackage]

    @classmethod
    def read(cls) -> Self:
        with open('debian/config/defines.toml', 'rb') as f:
            data = tomllib.load(f)

        return dacite.from_dict(
            data_class=cls,
            data=data,
            config=_dacite_config,
        )


_wildcard_re = re.compile(r'\*\*/?|[*?.^$+{}\\\[\]|()]')
_wildcard_map = {
    '**/': r'(?:.+/)?',
    '**':  r'.*',
    '*':   r'[^/]*',
    '?':   r'[^/]',
}

# pathlib.Path.match() does *not* support '**', so do our own
# pattern-to-regexp conversion
def pattern_to_re(pattern):
    return re.compile(
        _wildcard_re.sub(
            lambda match: _wildcard_map.get(match.group(0),
                                            '\\' + match.group(0)),
            pattern))
