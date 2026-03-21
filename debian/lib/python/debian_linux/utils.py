import io
import os
import re
import textwrap
import typing

import jinja2

from .dataclasses_deb822 import read_deb822
from .debian import SourcePackage, BinaryPackage, TestsControl


class Templates(object):
    dirs: list[str]
    _cache: dict[str, str]
    _jinja2: jinja2.Environment

    def __init__(self, dirs: list[str] = ["debian/templates"]) -> None:
        self.dirs = dirs

        self._cache = {}
        self._jinja2 = jinja2.Environment(
            # autoescape uses HTML safe escaping, which does not help us
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            undefined=jinja2.StrictUndefined,
        )

    def _read(self, name: str) -> typing.Any:
        pkgid, name = name.rsplit('.', 1)

        for suffix in ['.j2', '.in', '']:
            for dir in self.dirs:
                filename = "%s/%s.%s%s" % (dir, pkgid, name, suffix)
                if os.path.exists(filename):
                    with open(filename, 'r', encoding='utf-8') as f:
                        return (f.read(), suffix)

        raise KeyError(name)

    def _get(self, key: str) -> typing.Any:
        try:
            return self._cache[key]
        except KeyError:
            self._cache[key] = value = self._read(key)
            return value

    def get(self, key: str, context: dict[str, str] = {}) -> str:
        value = self._get(key)
        suffix = value[1]

        if context:
            if suffix == '.in':
                try:
                    def subst(match):
                        return context[match.group(1)]
                    return re.sub(r'@([-_a-z0-9]+)@', subst, str(value[0]))
                except KeyError as e:
                    raise RuntimeError(f'templates/{key}.in: {e} is undefined') from None

            elif suffix == '.j2':
                try:
                    return self._jinja2.from_string(value[0]).render(context)
                except jinja2.exceptions.UndefinedError as e:
                    raise RuntimeError(f'templates/{key}.j2: {e}') from None

        return value[0]

    def get_control(
        self, key: str, context: dict[str, str] = {},
    ) -> typing.Iterable[BinaryPackage]:
        return read_deb822(BinaryPackage, io.StringIO(self.get(key, context)))

    def get_source_control(
        self, key: str, context: dict[str, str] = {},
    ) -> typing.Iterable[SourcePackage]:
        return read_deb822(SourcePackage, io.StringIO(self.get(key, context)))

    def get_tests_control(
        self, key: str, context: dict[str, str] = {},
    ) -> typing.Iterable[TestsControl]:
        return read_deb822(TestsControl, io.StringIO(self.get(key, context)))


class TextWrapper(textwrap.TextWrapper):
    wordsep_re = re.compile(
        r'(\s+|'                                  # any whitespace
        r'(?<=[\w\!\"\'\&\.\,\?])-{2,}(?=\w))')   # em-dash
