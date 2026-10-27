"""Test that the config and options flows are fully translated."""
import json
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from custom_components.luxtronik.config_flow import (LuxtronikFlowHandler,
                                                    LuxtronikOptionsFlowHandler)

COMPONENT = Path(__file__).parent.parent / "custom_components" / "luxtronik"
TRANSLATIONS = ["translations/en.json", "translations/de.json"]


def _load(name):
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def _fields(schema):
    return {str(key) for key in schema.schema}


def _config_fields():
    return _fields(LuxtronikFlowHandler()._get_schema())


def _options_fields():
    entry = MagicMock(options={}, data={})
    with patch.object(LuxtronikOptionsFlowHandler, "config_entry", new_callable=PropertyMock, return_value=entry):
        return _fields(LuxtronikOptionsFlowHandler()._get_options_schema())


@pytest.mark.parametrize("filename", TRANSLATIONS)
@pytest.mark.parametrize(("section", "fields"), [("config", _config_fields), ("options", _options_fields)])
def test_flow_fields_translated(filename, section, fields):
    """Every field of the user step has a label and a description."""
    step = _load(filename)[section]["step"]["user"]
    expected = fields()

    assert set(step["data"]) == expected
    assert set(step.get("data_description", {})) == expected
    assert all(step["data"].values())
    assert all(step["data_description"].values())


@pytest.mark.parametrize("section", ["config", "options"])
def test_strings_match_english(section):
    """strings.json is the source of the English translation."""
    assert _load("strings.json").get(section) == _load("translations/en.json")[section]
