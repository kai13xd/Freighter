import inspect
import tomllib
from functools import wraps
from os import PathLike
from types import UnionType
from typing import Any, Type, TypeVar, Union, get_args, get_origin

import attrs

from freighter.console import Console
from freighter.exceptions import FreighterException
from freighter.numerics import Number
from freighter.path import FilePath


@attrs.define
class TOMLFieldInfo:
    class_type: type = attrs.field(repr=False)
    class_name: str
    generic_arg_types: tuple[type, type] = attrs.field(repr=False)
    origin: type | None = attrs.field(repr=False)
    attr_name: str
    toml_key: str | None = attrs.field(repr=False)
    default: Any = attrs.field(repr=False)
    comment: str = attrs.field(repr=False)
    required: bool
    serialize: bool

    def __init__(self, attr: attrs.Attribute):
        self.class_type = attr.type  # type: ignore
        self.origin = get_origin(self.class_type)
        self.generic_arg_types = get_args(self.class_type)
        self.class_name = ""
        if self.origin is Union or self.origin is UnionType:
            self.class_name = " | ".join(x.__name__ for x in self.generic_arg_types)
        else:
            self.class_name = attr.type.__name__  # type: ignore
        self.toml_key = attr.alias
        self.attr_name = attr.name
        self.default = attr.default
        self.comment = attr.metadata["comment"]
        self.required = attr.metadata["required"]
        self.serialize = attr.metadata["serialize"]

    @property
    def is_TOMLObject(self):
        return issubclass(self.class_type, TOMLObject)

    def __lt__(self, other):
        return self.required > other.required


@wraps(attrs.field)
def tomlfield(*args, comment="", required=False, serialize=True, toml_key="", **kwargs):
    attr_field = attrs.field(*args, **kwargs)
    if toml_key:
        attr_field.alias = toml_key
    attr_field.metadata["comment"] = comment
    attr_field.metadata["required"] = required
    attr_field.metadata["serialize"] = serialize
    if serialize == False:
        attr_field.init = False
    return attr_field


def toml_format(obj: Any) -> str:
    if isinstance(obj, PathLike) or isinstance(obj, str):
        return f'"{obj}"'
    if isinstance(obj, dict):
        string = ""
        if not obj:
            return "{}"
        for key, value in obj:
            string += f"{key} = {toml_format(value)}"
        return string
    elif isinstance(obj, list):
        string = "["
        for item in obj:
            string += toml_format(item) + ","
        return string.removesuffix(",") + "]"
    elif isinstance(obj, Number):
        return obj.hex
    return str(obj)


@attrs.define
class TOMLObject:
    @classmethod
    def get_fields(cls):
        Console.printDebug(f"Class Type '{cls.__name__}'")
        field_info = [TOMLFieldInfo(x) for x in attrs.fields(cls)]
        return field_info

    @classmethod
    def get_required_fields(cls):
        field_info = []
        for field in cls.get_fields():
            if field.required:
                field_info.append(field)
        return field_info

    @classmethod
    def get_optional_fields(cls) -> list[TOMLFieldInfo]:
        field_info = []
        for field in cls.get_fields():
            if not field.required:
                field_info.append(field)
        return field_info

    @property
    def toml_string(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        string = ""
        required_fields = self.get_required_fields()
        optional_fields = self.get_optional_fields()
        if required_fields:
            string += self.serialize_fields(required_fields)
        if optional_fields:
            string += self.serialize_fields(optional_fields)

        return string

    def serialize_fields(self, field_info: list[TOMLFieldInfo]) -> str:
        string = ""
        for field in field_info:
            if not field.serialize:
                continue
            if not hasattr(self, field.attr_name) and not field.required:
                continue

            field_value = self.__getattribute__(field.attr_name)
            if issubclass(self.__class__, TOMLConfig):
                if isinstance(field_value, list):
                    for value in field_value:
                        string += f"[[{field.toml_key}]]\n"
                        string += str(value)
                elif isinstance(field_value, dict):
                    for key, value in field_value.items():
                        string += f"[{field.toml_key}.{key}]\n"
                        string += str(value)
                elif isinstance(field_value, TOMLObject):
                    string += f"\n[{field.toml_key}]\n"
                    string += f"{toml_format(field_value)}\n"
                # Top-level table fields
                else:
                    string += f"{field.toml_key} = {toml_format(field_value)}"
            else:
                string += f"{field.toml_key} = {toml_format(field_value)}"

            if field.comment:
                string += f"\t# {field.comment}\n"
            else:
                string += "\n"

        return string


ConfigType = TypeVar("ConfigType", bound="TOMLConfig")


@attrs.define
class TOMLConfig(TOMLObject):
    config_path: FilePath = tomlfield(serialize=False)
    is_empty: bool = tomlfield(serialize=False)

    def save(self, path: FilePath):
        with open(path, "w") as f:
            f.write(self.toml_string)
        Console.printVerbose(f'Saved "{path.stem}" to {path.parent}.')

    @classmethod
    def load(cls: Type[ConfigType], config_path: FilePath) -> ConfigType:
        Console.printDebug(f"Creating TOMLConfig class'{cls.__name__}'")
        config_path.assert_exists()
        object = cls()
        object.config_path = config_path

        with open(object.config_path, "rb") as f:
            toml_dict = tomllib.load(f)

        if not toml_dict:
            object.is_empty = True
            return object

        object.is_empty = False

        field_info = cls.get_fields()
        if object.has_required_fields(toml_dict, field_info):
            for field in field_info:
                if not field.serialize:
                    continue
                result_object = object.get_field_or_default(field, toml_dict)
                object.__setattr__(field.attr_name, result_object)
        Console.printVerbose(f'Finished Loaded "{config_path.stem}.toml" from "{config_path.parent}".')
        return object

    def get_field_or_default(self, field: TOMLFieldInfo, toml_dict: dict):
        if field.toml_key in toml_dict.keys():
            return self.parse_field(field, toml_dict[field.toml_key])
        elif field.default == attrs.NOTHING:
            return None
        elif hasattr(field.default, "factory"):
            return field.default.factory()
        else:
            return field.default

    def has_required_fields(self, toml_dict: dict, field_info: list[TOMLFieldInfo]):
        required_fields = [x for x in field_info if x.required]
        if not required_fields:
            return True
        missing_fields = []
        for field in required_fields:
            if field.toml_key not in toml_dict.keys():
                missing_fields.append(field.toml_key)
        if missing_fields:
            raise FreighterException(f"{self.__class__.__name__} at '{self.config_path} 'is missing values for the following keys:\n{missing_fields}")
        return True

    def prepare_kwargs(self, field_info: list[TOMLFieldInfo], value: dict):
        kw_args = {}
        if self.has_required_fields(value, field_info):
            for field in field_info:
                if not field.serialize:
                    continue
                kw_args[field.attr_name] = self.get_field_or_default(field, value)
        return kw_args

    def parse_dict(self, field: TOMLFieldInfo, toml_dict: dict):
        Console.printDebug(f"Instantiating 'dict[{field.generic_arg_types[0].__name__}, {field.generic_arg_types[1].__name__}]' with the TOML key '{field.toml_key}'")
        result_dict = {}
        dict_value_type = field.generic_arg_types[1]
        if issubclass(dict_value_type, TOMLObject):
            field_info = dict_value_type.get_fields()
            # Prepare the kwargs of the dict's value type and instantiate it with values

            for key, value in toml_dict.items():
                if self.has_required_fields(value, field_info):
                    result_object = self.parse_toml_object(dict_value_type, value)
                    result_dict[key] = result_object
        else:
            for key, value in toml_dict.items():
                result_dict[key] = dict_value_type(value)

        return result_dict

    def parse_list(self, field: TOMLFieldInfo, toml_list: list):
        result = []
        list_type = field.generic_arg_types[0]
        if issubclass(list_type, TOMLObject):
            for item in toml_list:
                result.append(self.parse_toml_object(list_type, item))
        else:
            for item in toml_list:
                result.append(list_type(item))
        return result

    def parse_toml_object(self, toml_object_type: type[TOMLObject], toml_dict: dict):
        Console.printDebug(f"Instantiating TOMLObject '{toml_object_type}'")
        field_info = toml_object_type.get_fields()
        kwargs = self.prepare_kwargs(field_info, toml_dict)
        return toml_object_type(**kwargs)

    def parse_field(self, field: TOMLFieldInfo, toml_value: Any):
        # Iterate all keys and values of subdict and convert values back to their original types
        if field.origin == dict:
            result_object = self.parse_dict(field, toml_value)
        elif field.origin == list:
            result_object = self.parse_list(field, toml_value)
        elif field.is_TOMLObject:
            result_object = self.parse_toml_object(field.class_type, toml_value)
        else:
            result_object = field.class_type(toml_value)
        return result_object
