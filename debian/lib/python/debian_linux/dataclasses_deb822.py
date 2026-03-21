from __future__ import annotations

import dataclasses
import re
from typing import (
    Any,
    Callable,
    Generic,
    IO,
    Iterable,
    Optional,
    overload,
    TypeVar,
    TYPE_CHECKING,
)

_T = TypeVar('_T')

if TYPE_CHECKING:
    from dataclasses import _DataclassT
else:
    # We can only get to _DataclassT during type checking, use a generic type during runtime
    _DataclassT = _T

__all__ = [
    'field_deb822',
    'read_deb822',
    'write_deb822',
    'Deb822DecodeError',
]


class Deb822Field(Generic[_T]):
    key: str
    load: Optional[Callable[[str], _T]]
    dump: Optional[Callable[[_T], str]]

    def __init__(
        self, *,
        key: str,
        load: Optional[Callable[[str], _T]],
        dump: Optional[Callable[[_T], str]],
    ) -> None:
        self.key = key
        self.load = load
        self.dump = dump


# The return type _T is technically wrong, but it allows checking if during
# runtime we get the correct type.
@overload
def field_deb822(
    deb822_key: str,
    /, *,
    deb822_load: Optional[Callable[[str], _T]] = None,
    deb822_dump: Optional[Callable[[_T], str]] = str,
    default: _T,
) -> _T:
    ...


@overload
def field_deb822(
    deb822_key: str,
    /, *,
    deb822_load: Optional[Callable[[str], _T]] = None,
    deb822_dump: Optional[Callable[[_T], str]] = str,
    default_factory: Callable[[], _T],
) -> _T:
    ...


@overload
def field_deb822(
    deb822_key: str,
    /, *,
    deb822_load: Optional[Callable[[str], _T]] = None,
    deb822_dump: Optional[Callable[[_T], str]] = str,
) -> _T:
    ...


def field_deb822(
    deb822_key: str,
    /, *,
    deb822_load: Optional[Callable[[str], _T]] = None,
    deb822_dump: Optional[Callable[[_T], str]] = str,
    default: Any = dataclasses.MISSING,
    default_factory: Any = dataclasses.MISSING,
) -> Any:
    metadata: dict[str, Any] = {
        'deb822': Deb822Field(
            key=deb822_key,
            load=deb822_load,
            dump=deb822_dump,
        ),
    }

    if default is not dataclasses.MISSING:
        return dataclasses.field(
            default=default,
            metadata=metadata,
        )
    else:
        return dataclasses.field(
            default_factory=default_factory,
            metadata=metadata,
        )


class Deb822DecodeError(ValueError):
    pass


class Deb822DecodeState(Generic[_DataclassT]):
    cls: type[_DataclassT]
    fields: dict[str, dataclasses.Field]
    ignore_unknown: bool

    data: dict[Optional[dataclasses.Field], str]
    current: Optional[dataclasses.Field]

    _line_re = re.compile(r'''
        ^
        (
            [ \t](?P<cont>.*)
            |
            (?P<key>[^: \t\n\r\f\v]+)\s*:\s*(?P<value>.*)
        )
        $
    ''', re.VERBOSE)

    def __init__(
        self,
        cls: type[_DataclassT],
        ignore_unknown: bool,
    ) -> None:
        self.reset()

        self.cls = cls
        self.fields = {}
        self.ignore_unknown = ignore_unknown

        for i in dataclasses.fields(cls):
            if i.init and (deb822_field := i.metadata.get('deb822')):
                self.fields[deb822_field.key] = i

    def reset(self) -> None:
        self.data = {}
        self.current = None

    def line(self, linenr: int, line: str) -> None:
        m = self._line_re.match(line)
        if not m:
            raise Deb822DecodeError(
                f'Not a header, not a continuation at line {linenr + 1}')
        elif cont := m.group('cont'):
            self.data[self.current] += '\n' + cont
        elif deb822_key := m.group('key'):
            field = self.fields.get(deb822_key)
            if not field and not self.ignore_unknown:
                raise Deb822DecodeError(
                    f'Unknown field "{deb822_key}" at line {linenr + 1}')

            self.current = field
            self.data[field] = m.group('value')
        else:
            raise NotImplementedError

    def generate(self) -> _DataclassT | None:
        if not self.data:
            return None

        r: dict[str, Any] = {}
        for field, value in self.data.items():
            field_factory: Optional[Callable[[str], Any]] = None
            if field is None:
                continue
            elif (deb822_field := field.metadata.get('deb822')) and (load := deb822_field.load):
                field_factory = load
            elif isinstance(field.default_factory, type):
                field_factory = field.default_factory
            elif field.type in ('str', 'Optional[str]'):
                field_factory = str
            else:
                raise RuntimeError(f'Unable to parse type {field.type}')

            if field_factory is not None:
                r[field.name] = field_factory(value)

        self.reset()
        return self.cls(**r)


def read_deb822(
    cls: type[_DataclassT],
    file: IO[str],
    /,
    ignore_unknown: bool = False,
) -> Iterable[_DataclassT]:
    state = Deb822DecodeState(cls, ignore_unknown)

    for linenr, line in enumerate(file):
        line = line.rstrip('\n')

        # Empty line, end of record
        if line == '':
            if (obj := state.generate()):
                yield obj
        # Strip comments rather than trying to preserve them
        elif line[0] == '#':
            continue
        else:
            state.line(linenr, line)

    if (obj := state.generate()):
        yield obj


def write_deb822(
    objs: Iterable[_DataclassT],
    file: IO[str],
    /,
) -> None:
    for obj in objs:
        for field in dataclasses.fields(obj):
            if (
                (value := getattr(obj, field.name, None))
                and (deb822_field := field.metadata.get('deb822'))
                and (dump := deb822_field.dump) is not None
            ):
                folded = '\n '.join(dump(value).strip().split('\n'))
                file.write(f'{deb822_field.key}: {folded}\n')
        file.write('\n')
