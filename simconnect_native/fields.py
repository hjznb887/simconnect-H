"""Field descriptors for get_many / subscribe_many."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Union

from .constants import SIMCONNECT_DATATYPE_FLOAT64_INT
from .parsing import DATATYPE_SIZES
from .utils import as_non_negative_int, is_string_datatype

FieldSpec = Union["DataField", Tuple[str, str], Tuple[str, str, int]]
FieldsMapping = Dict[str, FieldSpec]

ParsedField = Tuple[str, str, str, int]


@dataclass(frozen=True)
class DataField:
    """SimVar 字段描述（名称、单位、数据类型）。"""

    name: str
    unit: str = ""
    datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT

    def as_tuple(self) -> Tuple[str, str, int]:
        return (self.name, self.unit, int(self.datatype))


def parse_fields(fields: FieldsMapping) -> List[ParsedField]:
    """将 dict / DataField / tuple 规范为 (key, name, unit, dtype) 列表。"""
    parsed: List[ParsedField] = []
    for key, spec in fields.items():
        if isinstance(spec, DataField):
            name, unit, dtype = spec.as_tuple()
        elif len(spec) == 2:
            name, unit = spec
            dtype = SIMCONNECT_DATATYPE_FLOAT64_INT
        elif len(spec) == 3:
            name, unit, dtype = spec
        else:
            raise ValueError(f"fields[{key!r}] 格式无效: {spec!r}")
        dtype = as_non_negative_int(f"fields[{key!r}] datatype", int(dtype))
        parsed.append((key, name, unit, dtype))
    return parsed


def build_field_layout(parsed: List[ParsedField]) -> List[Tuple[str, int, int]]:
    """计算批量打包布局 [(key, dtype, offset), ...]。"""
    layout: List[Tuple[str, int, int]] = []
    offset = 0
    for key, _name, _unit, dtype in parsed:
        size = DATATYPE_SIZES.get(dtype)
        if size is None:
            raise ValueError(
                f"批量字段 {key!r} 暂不支持 datatype={dtype}"
            )
        layout.append((key, dtype, offset))
        offset += size
    return layout


def split_numeric_string_fields(
    parsed: List[ParsedField],
) -> Tuple[List[ParsedField], List[ParsedField]]:
    """拆分为可批量打包的数值字段与字符串字段。"""
    numeric: List[ParsedField] = []
    string: List[ParsedField] = []
    for item in parsed:
        if is_string_datatype(item[3]):
            string.append(item)
        elif DATATYPE_SIZES.get(item[3]) is not None:
            numeric.append(item)
        else:
            raise ValueError(
                f"字段 {item[0]!r} datatype={item[3]} 不支持"
            )
    return numeric, string
