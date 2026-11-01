"""Test the fallbacks of the text helpers."""
from custom_components.luxtronik.helpers import helper


def test_sensor_text_without_language():
    """Without a language, the English text is used."""
    assert helper.get_sensor_text(None, "heating") == "Heating"


def test_unknown_sensor_text(caplog):
    """An unknown text key is shown as a title, with a warning."""
    assert helper.get_sensor_text("de", "no_such_text") == "No Such Text"
    assert "no_such_text not found" in caplog.text


def test_sensor_value_text():
    """A status value is translated into the language."""
    assert helper.get_sensor_value_text(
        "de", "luxtronik2__status_line_1", "heatpump running") == "Die Wärmepumpe läuft"


def test_missing_text_file(caplog):
    """A missing text file is logged and gives no texts."""
    helper._load_lang_from_file.cache_clear()
    try:
        helper.get_sensor_value_text(
            "en", "luxtronik2__status_line_1", "heatpump running", platform="missing")
    finally:
        helper._load_lang_from_file.cache_clear()
    assert "file not found" in caplog.text
