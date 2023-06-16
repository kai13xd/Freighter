import inspect
import tomllib
from dataclasses import dataclass, fields
from os import PathLike
from typing import Any, get_args, get_origin

from freighter.console import Console, PrintType
from freighter.exceptions import FreighterException
from freighter.numerics import Number
from freighter.path import FilePath


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


@dataclass
class TOMLObject:
    def __str__(self) -> str:
        string = ""
        for field in fields(self):
            toml_value = toml_format(self.__getattribute__(field.name))
            # if "_" in field.name:
            #     toml_key = ""
            #     parts = field.name.split("_")
            #     for part in parts:
            #         toml_key += part.capitalize()
            # else:
            #     toml_key = field.name.capitalize()
            # toml_key = field.name.capitalize()
            string += f"{field.name} = {toml_value}\n"
        return string + "\n"


"""
So here's the idea for structuring Freighter's configs. TOMLConfig is the base class
to start building the programmatic representation of the config. The class must be also
be a dataclass.

Dataclasses are a nice builtin way of providing context of the field's class type.
This give's us a way to transform the TOML data back into their original types. 

If a dataclass member of the class is a collection of class objects we use a dict[TOMLObject] 
where the keys will serve to identify unique instances of the TOMLObject class

Since the keys are anologous to the kw args of the dataclass we can create a dict and 
populate it from the toml dict tomlib.load returns and construct the objects back into 
their original types.


=======================================================
Top-level TOMLObjects:
=======================================================
[TOMLObject] #Class Type
Field0 = "foo"
Field1 = 0xF00

{
  "TOMLObject": {
    "Field0": "foo",
    "Field1": 3840
  }
}

=======================================================
Top-level Dicts of TOMLObjects:
=======================================================
[TOMLObject.DictKey0] #First namespace is the class type
Field0 = "foo"
Field1 = 0xF00

[TOMLObject.DictKey1]
Field0 = "foo"
Field1 = 0xF00

{
  "TOMLObject": {
    "DictKey0": {
      "Field0": "foo",
      "Field1": 3840
    },
    "DictKey1": {
      "Field0": "foo",
      "Field1": 3840
    }
  }
}

=======================================================
Top-level Lists, Tuples, Sets
=======================================================
[[TOMLObject]] #Double brackets represents a list of tables. We don't need to worry about unique names.
Field0 = "foo"
Field1 = 0xF00

[[TOMLObject]]
Field0 = "foo"
Field1 = 0xF00

{
  "TOMLObject": [
    {
      "Field0": "foo",
      "Field1": 3840
    },
    {
      "Field0": "foo",
      "Field1": 3840
    }
  ]
}
"""


@dataclass
class TOMLConfig:
    def save(self, path: FilePath):
        with open(path, "w") as f:
            f.write(self.toml_string)
        Console.print(f'Saved "{path.stem}" to {path.parent}.', PrintType.VERBOSE)

    # TODO: Clean up this messy function
    def load(self, path: FilePath):
        with open(path, "rb") as f:
            toml_config = tomllib.load(f)

        dataclass_typedict = dict[str, type]()

        for i, field in enumerate(self.__dataclass_fields__.values()):
            class_type = field.type
            name = field.type.__name__
            arg_count = len(inspect.signature(field.type.__init__).parameters) - 1
            Console.print(f"Field {i} {field.name}:\n\tType:{name}\n\t__init__ Expects {arg_count} args", PrintType.DEBUG)
            dataclass_typedict[field.name] = field.type

        for i, kv in enumerate(toml_config.items()):
            toml_key, toml_value = kv
            Console.print(f"TOML_Field {i}: {toml_key} = {toml_value}", PrintType.DEBUG)

        Console.print(f"TOMLConfig ({self.__class__.__name__})", PrintType.DEBUG)
        try:
            for keyword, attribute_dict in toml_config.items():
                class_type = dataclass_typedict[keyword]
                result_object = self.parse_dataclass_field(class_type, attribute_dict)
                Console.print(f"Parsed {keyword} of type {dataclass_typedict[keyword].__name__}", PrintType.DEBUG)
                self.__setattr__(keyword, result_object)

            Console.print(f'Loaded "{path.stem}.toml" from "{path.parent}".', PrintType.VERBOSE)
        except:
            raise FreighterException(f'The TOML config "{path}" is malformed!')

    def construct_list(self, class_type, list_data):
        result = []
        for item in list_data:
            result.append(class_type(item))
        return result

    def parse_dataclass_field(self, class_type: type, attribute_dict: dict):
        if get_origin(class_type) == dict:
            result_object = class_type()
            key_type, value_type = get_args(class_type)
            kw_args = {}
            for key, value in attribute_dict.items():
                for inner_key, inner_value in value.items():
                    inner_type = value_type.__dataclass_fields__[inner_key].type
                    if get_origin(inner_type) == list:
                        list_value_type = get_args(inner_type)[0]
                        kw_args[inner_key] = self.construct_list(list_value_type, inner_value)
                        continue
                    elif get_origin(inner_type) == dict:
                        inner_key_type, inner_value_type = get_args(inner_type)
                        if issubclass(inner_value_type, TOMLObject):
                            kw_args[inner_key] = self.parse_dataclass_field(inner_type, inner_value)
                            continue
                    kw_args[inner_key] = inner_type(inner_value)
                result_object[key] = value_type(**kw_args)
        # elif isinstance(class_type, list):
        #     result_object = class_type()
        #     for obj_dict in attribute_dict:
        #         kw_args = []
        #         for key, value in obj_dict.items():
        #             kw_args.append(class_type.__dataclass_fields__[key].type(value))
        #         result_object.append(class_type(*kw_args))
        elif issubclass(class_type, TOMLObject):
            kw_args = []
            for key, value in attribute_dict.items():
                kw_args.append(class_type.__dataclass_fields__[key].type(value))
            result_object = class_type(*kw_args)
        else:
            result_object = class_type(attribute_dict)
        return result_object

    @property
    def toml_string(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        string = ""
        for field in fields(self):
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
            # Top-level table fields
            else:
                string += f"{field.name} = {toml_format(field_value)}\n"
        return string
