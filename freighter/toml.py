import inspect
import tomllib
import attrs

from os import PathLike
from typing import Any, Union, get_args, get_origin
from types import UnionType
from freighter.console import Console, PrintType
from freighter.exceptions import FreighterException
from freighter.numerics import Number
from freighter.path import FilePath
from functools import wraps


@wraps(attrs.field)
def tomlfield(*args, comment="", required=False, **kwargs):
    attr_field = attrs.field(*args, **kwargs)
    attr_field.metadata["comment"] = comment
    attr_field.metadata["required"] = required
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


def get_field_info(class_type):
    Console.print(f"Class Type '{class_type.__name__}'", PrintType.DEBUG)
    field_types = dict[str, FieldInfo]()
    for i, field in enumerate(attrs.fields(class_type)):
        field = FieldInfo(field)
        if field.alias:
            field_types[field.alias] = field
        else:
            field_types[field.name] = field
        arg_count = len(inspect.signature(field.class_type.__init__).parameters) - 1
        Console.print(f"Field {i}\n\tAttribute Name: '{field.name}'\n\tTOML Alias: '{field.alias}'\n\tType: '{field.class_name}'\n\t__init__ Expects {arg_count} args", PrintType.DEBUG)
    return field_types


@attrs.define
class TOMLObject:
    def __str__(self) -> str:
        string = ""
        for field in get_field_info(self.__class__).values():
            toml_value = toml_format(self.__getattribute__(field.name))
            if field.comment:
                string += f"{field.name} = {toml_value} # {field.comment}\n"
            else:
                string += f"{field.name} = {toml_value}\n"
        return string


@attrs.define
class FieldInfo:
    class_type: type
    class_name: str
    generic_arg_types: tuple[type, type]
    origin: type | None
    name: str
    alias: str | None
    default: Any
    comment: str
    required: bool

    def __init__(self, attr: attrs.Attribute):
        self.class_type = attr.type
        self.origin = get_origin(self.class_type)
        self.generic_arg_types = get_args(self.class_type)
        self.class_name = ""
        if self.origin is Union or self.origin is UnionType:
            self.class_name = " | ".join(x.__name__ for x in self.generic_arg_types)
        else:
            self.class_name = attr.type.__name__

        self.alias = attr.alias

        self.name = attr.name
        self.default = attr.default
        self.comment = attr.metadata["comment"]
        self.required = attr.metadata["required"]

    @property
    def is_TOMLObject(self):
        return issubclass(self.class_type, TOMLObject)


@attrs.define
class TOMLConfig:
    def save(self, path: FilePath):
        with open(path, "w") as f:
            f.write(self.toml_string)
        Console.print(f'Saved "{path.stem}" to {path.parent}.', PrintType.VERBOSE)

    @staticmethod
    def from_toml_dict(class_type: type, toml_dict: dict):
        Console.print(f"Creating TOMLConfig class'{class_type.__name__}'", PrintType.DEBUG)
        object = class_type()
        field_info = get_field_info(class_type)
        for attribute_name, field in field_info.items():
            if attribute_name in toml_dict.keys():
                result_object = object.parse_field(field, toml_dict[attribute_name])
            elif field.default and field.default != attrs.NOTHING:
                if hasattr(field.default, "factory"):
                    result_object = field.default.factory()
                else:
                    result_object = field.default
            elif field.default == attrs.NOTHING:
                result_object = None
            else:
                raise FreighterException(f"Missing a required value for the key {field.name}")
            object.__setattr__(field.name, result_object)
        return object
        # Console.print(f'Finished Loaded "{path.stem}.toml" from "{path.parent}".', PrintType.VERBOSE)

    def load(self, path: FilePath):
        Console.print(f"Creating TOMLConfig class'{self.__class__.__name__}'", PrintType.DEBUG)
        with open(path, "rb") as f:
            toml_config = tomllib.load(f)

        field_info = get_field_info(self.__class__)

        for attribute_name, field in field_info.items():
            if attribute_name in toml_config.keys():
                result_object = self.parse_field(field, toml_config[attribute_name])
            elif field.default and field.default != attrs.NOTHING:
                if hasattr(field.default, "factory"):
                    result_object = field.default.factory()
                else:
                    result_object = field.default
            elif field.default == attrs.NOTHING:
                result_object = None
            else:
                raise FreighterException(f"{path} is missing a required value for the key {field.name}")
            self.__setattr__(field.name, result_object)

        Console.print(f'Finished Loaded "{path.stem}.toml" from "{path.parent}".', PrintType.VERBOSE)

    def construct_list(self, class_type, list_data):
        result = []
        for item in list_data:
            result.append(class_type(item))
        return result

    def parse_field(self, field: FieldInfo, object_attributes: dict):
        # Iterate all keys and values of subdict and convert values back to their original types
        if field.origin == dict:
            result_object = field.class_type()
            value_class_type = field.generic_arg_types[1]
            kw_args = {}
            for key, value in object_attributes.items():
                # Instantiate an instance of the value's type and set it's attributes
                field_info = get_field_info(value_class_type)
                for attribute_key, attribute_value in value.items():
                    field = field_info[attribute_key]
                    if field.origin == list:
                        list_value_type = field.generic_arg_types[0]
                        kw_args[attribute_key] = self.construct_list(list_value_type, attribute_value)
                        continue
                    elif field.origin == dict:
                        inner_value_type = field.generic_arg_types[1]
                        if issubclass(inner_value_type, TOMLObject):
                            kw_args[attribute_key] = self.parse_field(field, attribute_value)
                        else:
                            # if the dict value's class type is a primitive type just set the kw_arg as is
                            kw_args[attribute_key] = attribute_value
                            continue
                    else:
                        kw_args[attribute_key] = field.class_type(attribute_value)
                result_object[key] = value_class_type(**kw_args)
                Console.print(f"Created an instance of type '{field.class_name}' with the key '{field.name}' for '{key}'", PrintType.DEBUG)

        elif field.is_TOMLObject:
            Console.print(f"Instantiating TOMLObject '{field.class_name}'", PrintType.DEBUG)
            kw_args = []
            field_info = get_field_info(field.class_type)
            for key, value in object_attributes.items():
                kw_args.append(field_info[key].class_type(value))
            result_object = field.class_type(*kw_args)
        else:
            result_object = field.class_type(object_attributes)
        return result_object

    @property
    def toml_string(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        string = ""
        for field in get_field_info(self.__class__).values():
            if field.default == attrs.NOTHING and not hasattr(self, field.name):
                continue
            field_value = self.__getattribute__(field.name)
            if isinstance(field_value, list):
                for value in field_value:
                    string += f"[[{field.name}]]\n"
                    string += str(value)
            elif isinstance(field_value, dict):
                for key, value in field_value.items():
                    string += f"[{field.name}.{key}]\n"
                    string += str(value)
            elif isinstance(field_value, TOMLObject):
                string += f"[{field.name}]\n"
                string += f"{toml_format(field_value)}\n"
            # Skip writing fields that are optional and are None
            elif field_value == None:
                continue
            # Top-level table fields
            else:
                string += f"{field.name} = {toml_format(field_value)}"
            if field.comment:
                string += f"# {field.comment}\n"
            else:
                string += "\n"
        return string
