"""Main help module."""
import json
import os.path
from functools import cache

from homeassistant.components.sensor import ENTITY_ID_FORMAT

from ..const import DOMAIN, LANG_DEFAULT, LANGUAGES_SENSOR_NAMES, LOGGER


@cache
def _load_lang_from_file(fname: str, log_warning=True):
    dir_path = os.path.dirname(os.path.realpath(__file__))
    fname = os.path.join(dir_path, fname)
    if not os.path.isfile(fname):
        if log_warning:
            LOGGER.warning("_load_lang_from_file - file not found %s", fname)
        return {}
    with open(fname, encoding="utf-8") as f:
        return json.load(f)


def _normalize_lang(lang: str) -> str:
    if lang is None:
        return LANG_DEFAULT
    lang = lang.lower()
    if '-' in lang:
        lang = lang.split('-')[0]
    if lang not in LANGUAGES_SENSOR_NAMES:
        return LANG_DEFAULT
    return lang


def _load_texts(lang: str) -> dict:
    return _load_lang_from_file(f"../translations/texts.{lang}.json")


def _load_value_texts(lang: str, platform: str) -> dict:
    return _load_lang_from_file(
        f"../translations/{platform}.{lang}.json", log_warning=lang == LANG_DEFAULT
    )


def load_texts(lang: str) -> None:
    """Load all text files, so the getters don't do file I/O inside the event loop."""
    lang = _normalize_lang(lang)
    for file_lang in {LANG_DEFAULT, lang}:
        _load_texts(file_lang)
        _load_value_texts(file_lang, "sensor")


def get_sensor_text(lang: str, key: str) -> str:
    """Get a sensor text."""
    lang = _normalize_lang(lang)
    if lang != LANG_DEFAULT:
        content_locale = _load_texts(lang)
        if key in content_locale:
            return content_locale[key]
    content_default = _load_texts(LANG_DEFAULT)
    if key in content_default:
        return content_default[key]
    LOGGER.warning("get_sensor_text key %s not found in %s", key, content_default)
    return key.replace("_", " ").title()


def get_sensor_value_text(
    lang: str, key: str, value: str, platform="sensor"
) -> str:
    """Get a sensor value text."""
    content = _load_value_texts(_normalize_lang(lang), platform)
    if (
        "state" in content
        and key in content["state"]
        and value in content["state"][key]
    ):
        return content["state"][key][value]
    LOGGER.warning(
        "get_sensor_value_text key %s / value %s not found in %s",
        key,
        value,
        content,
    )
    return key.replace("_", " ").title()


def get_yaml_unique_id(sensor_key: str) -> str:
    """Get the unique_id of a sensor configured in YAML, kept from the YAML platforms."""
    return ENTITY_ID_FORMAT.format(f"{DOMAIN}_{sensor_key.split('.')[-1]}")
