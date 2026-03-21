from __future__ import annotations

from dataclasses import (
    fields,
    is_dataclass,
    replace,
)
from typing import (
    Protocol,
    TypeVar,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from _typeshed import DataclassInstance as _DataclassInstance

    class _HasName(Protocol, _DataclassInstance):
        name: str

    _DataclassT = TypeVar('_DataclassT', bound=_DataclassInstance)
    _HasNameT = TypeVar('_HasNameT', bound=_HasName)


def default(
    cls: type[_DataclassT],
    /,
) -> _DataclassT:
    f = {}

    for field in fields(cls):
        if 'default' in field.metadata:
            f[field.name] = field.metadata['default']

    return cls(**f)


def merge(
    self: _DataclassT,
    other: _DataclassT | None, /,
) -> _DataclassT:
    if other is None:
        return self

    f = {}

    for field in fields(self):
        if not field.init:
            continue

        field_default_type = object
        if isinstance(field.default_factory, type):
            field_default_type = field.default_factory

        self_field = getattr(self, field.name)
        other_field = getattr(other, field.name)

        if field.name == 'name':
            assert self_field == other_field
        elif field.type == 'bool':
            f[field.name] = other_field
        elif field.metadata.get('merge') == 'assoclist':
            f[field.name] = _merge_assoclist(self_field, other_field)
        elif is_dataclass(field_default_type):
            f[field.name] = merge(self_field, other_field)
        elif issubclass(field_default_type, list):
            f[field.name] = self_field + other_field
        elif issubclass(field_default_type, dict):
            f[field.name] = self_field | other_field
        elif field.default is None:
            if other_field is not None:
                f[field.name] = other_field
        else:
            raise RuntimeError(f'Unable to merge for type {field.type}')

    return replace(self, **f)


def merge_default(
    cls: type[_DataclassT],
    /,
    *others: _DataclassT,
) -> _DataclassT:
    ret: _DataclassT = default(cls)
    for o in others:
        ret = merge(ret, o)
    return ret


def _merge_assoclist(
    self_list: list[_HasNameT],
    other_list: list[_HasNameT],
    /,
) -> list[_HasNameT]:
    '''
    Merge lists where each item got a "name" attribute
    '''
    if not self_list:
        return other_list
    if not other_list:
        return self_list

    ret: list[_HasNameT] = []
    other_dict = {
        i.name: i
        for i in other_list
    }
    for i in self_list:
        if i.name in other_dict:
            ret.append(merge(i, other_dict.pop(i.name)))
        else:
            ret.append(i)
    ret.extend(other_dict.values())
    return ret
