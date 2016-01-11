import collections

from dcos import package
from dcos.errors import DCOSException

import pytest

MergeData = collections.namedtuple(
    'MergeData',
    ['first', 'second', 'expected'])


@pytest.fixture(params=[
    MergeData(
        first={},
        second={'a': 1},
        expected={'a': 1}),
    MergeData(
        first={'a': 'a'},
        second={'a': 1},
        expected={'a': 1}),
    MergeData(
        first={'b': 'b'},
        second={'a': 1},
        expected={'b': 'b', 'a': 1}),
    MergeData(
        first={'b': 'b'},
        second={},
        expected={'b': 'b'}),
    MergeData(
        first={'b': {'a': 'a'}},
        second={'b': {'c': 'c'}},
        expected={'b': {'c': 'c', 'a': 'a'}}),
    MergeData(
        first={'b': 'c'},
        second={'b': 'd'},
        expected={'b': 'd'}),
    ])
def merge_data(request):
    return request.param


def test_options_merge_wont_override():
    with pytest.raises(DCOSException):
        package._merge_options({'b': 'c'}, {'b': 'd'}, False)


def test_option_merge(merge_data):
    assert merge_data.expected == package._merge_options(
        merge_data.first,
        merge_data.second)


DefaultConfigValues = collections.namedtuple(
    'DefaultConfigValue',
    ['schema', 'expected'])


@pytest.fixture(params=[
    DefaultConfigValues(
        schema={
            "type": "object",
            "properties": {
                "foo": {
                    "type": "object",
                    "properties": {
                        "bar": {
                            "type": "string",
                            "description": "A bar name."
                        },
                        "baz": {
                            "type": "integer",
                            "description": "How many times to do baz.",
                            "minimum": 0,
                            "maximum": 16,
                            "required": False,
                            "default": 4
                        }
                    }
                },
                "fiz": {
                    "type": "boolean",
                    "default": True,
                },
                "buz": {
                    "type": "string"
                }
            }
        },
        expected={'foo': {'baz': 4}, 'fiz': True}),
    DefaultConfigValues(
        schema={
            "type": "object",
            "properties": {
                "fiz": {
                    "type": "boolean",
                    "default": True,
                },
                "additionalProperties": False
            }
        },
        expected={'fiz': True}),
    DefaultConfigValues(
        schema={
            "type": "object",
        },
        expected=None)])
def config_value(request):
    return request.param


def test_extract_default_values(config_value):
    try:
        result = package._extract_default_values(config_value.schema)
    except DCOSException as e:
        result = str(e)
    assert result == config_value.expected
