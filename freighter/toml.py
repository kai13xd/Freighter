import tomllib
from functools import wraps
from os import PathLike
from types import UnionType
from typing import Any, Type, TypeVar, Union, get_args, get_origin, TYPE_CHECKING

import attrs
from freighter.exceptions import FreighterException
from freighter.logging import *
from freighter.numerics import Number
from freighter.path import FilePath


class TOMLField:
    attr_name: str
    class_name: str
    toml_key: str | None
    default: Any
    required: bool
    class_type: type = attrs.field(repr=False)
    generic_arg_types: tuple[type, ...] = attrs.field(repr=False)
    origin: type | None = attrs.field(repr=False)
    _comment: str = attrs.field(repr=False)

    @property
    def comment(self):
        if self._comment:
            return f" #{self._comment}"
        else:
            return ""

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
        if attr.default == attrs.NOTHING:
            self.default = None
        else:
            self.default = attr.default
        self._comment = attr.metadata["comment"]
        self.required = attr.metadata["required"]


@wraps(attrs.field)
def tomlfield(*args, comment: str = "", required: bool = False, serialize: bool = True, toml_key: str = "", **kwargs):
    attr_field = attrs.field(*args, **kwargs)
    if toml_key:
        attr_field.alias = toml_key
    attr_field.metadata["comment"] = comment
    attr_field.metadata["required"] = required
    attr_field.metadata["serialize"] = serialize
    if serialize == False:
        attr_field.init = False
    return attr_field


class TOMLObject:
    _required_fields: list[TOMLField]
    optional_fields: list[TOMLField]
    _fields: list[TOMLField]
    if TYPE_CHECKING:
        __attrs_attrs__ = tuple[attrs.Attribute]()

    @classmethod
    @property
    def fields(cls) -> list[TOMLField]:
        try:
            return cls._fields
        except AttributeError:
            cls._init_fields()
            return cls._fields

    @classmethod
    @property
    def required_fields(cls) -> list[TOMLField]:
        try:
            return cls._required_fields
        except AttributeError:
            cls._init_fields()
            return cls._required_fields

    def __new__(cls, *args, **kwargs):
        Logger.debug(f"Creating TOMLObject class'{cls.__name__}'")
        if cls.fields:
            pass  # Logger.debug(f"Field info already loaded for '{cls.__name__}'")
        return super(TOMLObject, cls).__new__(cls)

    @classmethod
    def _init_fields(cls) -> None:
        debug_string_list = [f"Loading field info for '{cls.__name__}'"]
        cls._required_fields = []
        cls.optional_fields = []
        cls._fields = []
        for i, attr in enumerate(cls.__attrs_attrs__):
            if not attr.metadata["serialize"]:  # Don't include non-serialized fields
                continue
            field = TOMLField(attr)
            cls._fields.append(field)
            debug_string_list.append(f"\tField {i}: attr_name='{field.attr_name}'  class='{field.class_name}'")

        for field in cls._fields:
            if field.required:
                cls._required_fields.append(field)
            else:
                cls.optional_fields.append(field)
        Logger.debug("\n".join(debug_string_list))

    @classmethod
    def _assert_has_required_fields(cls, toml_dict: dict):
        if not cls.required_fields:
            Logger.debug(f"'{cls.__name__}' has no required fields.")
            return

        missing_fields = []
        for field in cls.required_fields:
            if field.toml_key not in toml_dict.keys():
                missing_fields.append(field.toml_key)

        if not missing_fields:
            return True

        raise FreighterException(f"{cls.__name__} 'is missing values for the following keys:\n{missing_fields}")

    @classmethod
    def _get_kw_args(cls, toml_dict: dict):
        kw_args = {}
        for field in cls.fields:
            kw_args[field.attr_name] = cls._get_dict_value_or_default(field, toml_dict)
        return kw_args

    @classmethod
    def _get_dict_value_or_default(cls, field: TOMLField, toml_dict: dict) -> Any | None:
        if field.toml_key in toml_dict.keys():
            return cls._parse_field(field, toml_dict[field.toml_key])
        elif field.default == attrs.NOTHING:
            return None
        else:
            try:
                return field.default.factory()
            except:
                return field.default

    @classmethod
    def _recreate_generic_dict(cls, field: TOMLField, toml_dict: dict[str, Any]) -> dict:
        Logger.debug(f"Instantiating 'dict[{field.generic_arg_types[0].__name__}, {field.generic_arg_types[1].__name__}]' with the TOML key '{field.toml_key}'")
        result = {}
        generic_type = field.generic_arg_types[1]
        if issubclass(generic_type, TOMLObject):
            # Prepare the kwargs of the dict's value type and instantiate it with values

            for key, value in toml_dict.items():
                Logger.debug(f"Instantiating TOMLObject '{generic_type}'")
                result_object = generic_type._init_toml_object(value)
                result[key] = result_object
        else:
            for key, value in toml_dict.items():
                result[key] = generic_type(value)

        return result

    @classmethod
    def _recreate_generic_list(cls, field: TOMLField, toml_list: list) -> list:
        result = []
        generic_type = field.generic_arg_types[0]
        if issubclass(generic_type, TOMLObject):
            for item in toml_list:
                result.append(generic_type._init_toml_object(item))
        else:
            for item in toml_list:
                result.append(generic_type(item))
        return result

    @classmethod
    def _init_toml_object(cls, toml_dict: dict[str, Any]):
        cls._assert_has_required_fields(toml_dict)
        kw_args = {}
        for field in cls.fields:
            kw_args[field.attr_name] = cls._get_dict_value_or_default(field, toml_dict)
        object = cls(**kw_args)
        return object

    @classmethod
    def _parse_field(cls, field: TOMLField, toml_value: Any) -> Any:
        # Iterate all keys and values of subdict and convert values back to their original types
        if field.origin == dict:
            result_object = cls._recreate_generic_dict(field, toml_value)
        elif field.origin == list:
            result_object = cls._recreate_generic_list(field, toml_value)
        elif issubclass(field.class_type, TOMLObject):
            result_object = field.class_type._init_toml_object(toml_value)
        else:
            result_object = field.class_type(toml_value)
        return result_object

    def _format_value(self, value: Any) -> str:
        if isinstance(value, str | PathLike):
            return f'"{value}"'

        elif isinstance(value, Number):
            return value.hex
        elif isinstance(value, TOMLObject):
            string = []
            for field in value.fields:
                string.append(f"{field.toml_key} = {self._format_value(value.__getattribute__(field.attr_name))}")
            return "\n".join(string)

        elif isinstance(value, list | tuple | set):
            string = ""
            parts = []
            for item in value:
                parts.append(self._format_value(item))
            return f"[{", ".join(parts)}]"

        elif isinstance(value, dict):
            string = ""
            if not value:
                return "{}"
            for key, value in value.items():
                string += f"{key} = {self._format_value(value)}"
            return string
        else:
            return str(value)


TOMLConfigType = TypeVar("TOMLConfigType", bound="TOMLConfigFile")


class TOMLConfigFile(TOMLObject):
    def __new__(cls, *args, **kw_args):
        cls.__init__ = TOMLConfigFile.__init__  # This seems big ugly
        return super(TOMLConfigFile, cls).__new__(cls)

    def __init__(self, config_path: FilePath, **kw_args) -> None:
        self.path = config_path
        for key, value in kw_args.items():
            self.__setattr__(key, value)
        Logger.debug(f'Finished Loaded "{config_path}"')

    @classmethod
    def load(cls: Type[TOMLConfigType], config_path: FilePath) -> TOMLConfigType | None:
        if not config_path.exists:
            return None

        with open(config_path, "rb") as config_file:
            toml_dict: dict[str, Any] = tomllib.load(config_file)

        if not toml_dict:
            return None

        return cls(config_path, **cls._get_kw_args(toml_dict))

    @classmethod
    def load_from_dict(cls: Type[TOMLConfigType], config_path: FilePath, toml_dict: dict) -> TOMLConfigType:
        return cls(config_path, **cls._get_kw_args(toml_dict))

    def __comment__(self) -> str:
        return ""

    @property
    def toml_string(self) -> str:
        formatted_lines = list[str]()

        # Prepare top-level comment
        toplevel_comment = self.__comment__()
        if toplevel_comment:
            toplevel_comment = f"# {toplevel_comment} #"
            fill = "".ljust(len(toplevel_comment), "#")
            formatted_lines.append(fill)
            formatted_lines.append(toplevel_comment)
            formatted_lines.append(fill)
            formatted_lines.append("")

        for field in self.fields:
            value = self.__getattribute__(field.attr_name)
            if value == None:
                continue

            if field.origin == list | set | tuple:
                formatted_lines.append("")
                formatted_lines.append(f"[[{field.toml_key}]]{field.comment}")
                formatted_lines.append(self._format_value(value))

            elif field.origin == dict:
                value: dict = value
                for key, value in value.items():
                    formatted_lines.append("")
                    formatted_lines.append(f"[{field.toml_key}.{key}]{field.comment}")
                    formatted_lines.append(self._format_value(value))

            elif issubclass(field.class_type, TOMLObject):
                formatted_lines.append("")
                formatted_lines.append(f"[{field.toml_key}]{field.comment}")
                formatted_lines.append(self._format_value(value))
            else:
                formatted_lines.append(f"{field.toml_key} = {self._format_value(value)}{field.comment}")
        result = "\n".join(formatted_lines).rstrip()
        Logger.debug(result)
        return result

    def has_required_fields(self):
        missing_fields = list[tuple[Any, TOMLField]]()
        for field in self.required_fields:
            attribute = self.__getattribute__(field.attr_name)
            if attribute is None or attribute.__class__ != field.class_type:
                missing_fields.append((attribute, field))

        if not missing_fields:
            return True

        exception_string = list[str]()
        exception_string.append(f"TOMLConfig {self.__class__.__name__} is missing required attributes:")
        for attribute, field in missing_fields:
            exception_string.append(f"\t{field.attr_name} = {attribute.__class__.__name__}")
        exception_string = "\n".join(exception_string)
        raise FreighterException(exception_string)

    def save(self) -> None:
        if self.has_required_fields():
            with open(self.path, "w") as f:
                f.write(self.toml_string)
        Logger.debug(f'Saved "{self.path.stem}" to {self.path.parent}.')
