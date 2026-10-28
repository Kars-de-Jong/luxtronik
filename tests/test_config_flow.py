"""Test the config and options flows."""
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SENSORS
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik.const import (
    CONF_CONTROL_MODE_HOME_ASSISTANT,
    CONF_HA_SENSOR_INDOOR_TEMPERATURE,
    CONF_LOCK_TIMEOUT,
    CONF_SAFE,
    CONF_UPDATE_IMMEDIATELY_AFTER_WRITE,
    DEFAULT_PORT,
    DOMAIN,
)

from .conftest import SERIAL

HOST = "192.168.1.10"
PORT = 8889
USER_INPUT = {
    CONF_HOST: HOST,
    CONF_PORT: PORT,
    CONF_CONTROL_MODE_HOME_ASSISTANT: False,
    CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True,
    CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.luxtronik2_room_temperature",
}
DHCP_DISCOVERY = DhcpServiceInfo(ip=HOST, hostname="wwp2", macaddress="0060ab123456")
ENTRY_DATA = {
    CONF_HOST: HOST,
    CONF_PORT: PORT,
    CONF_SAFE: False,
    CONF_LOCK_TIMEOUT: 30,
    CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: True,
    CONF_CONTROL_MODE_HOME_ASSISTANT: False,
    CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.luxtronik2_room_temperature",
}


def schema_defaults(result):
    """Return the default values of the form in a flow result."""
    return {str(key): key.default() for key in result["data_schema"].schema}


@pytest.fixture
def device():
    """Mock a heatpump returned by a successful connect."""
    return MagicMock(
        unique_id=SERIAL, serial_number="2311-1234", manufacturer="Alpha Innotec", model="LWD")


@pytest.fixture
def mock_connect():
    """Patch the connection test of the config flow."""
    with patch("custom_components.luxtronik.config_flow.LuxtronikDevice.connect") as connect, \
            patch("custom_components.luxtronik.async_setup_entry", return_value=True):
        yield connect


async def test_user_flow_recovers_from_connection_error(hass, mock_connect, device):
    """A failed connection shows an error and the user can retry."""
    mock_connect.side_effect = OSError
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    mock_connect.side_effect = None
    mock_connect.return_value = device
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alpha Innotec LWD 2311-1234"
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == SERIAL
    mock_connect.assert_called_with(HOST, PORT)


async def test_user_flow_shows_form(hass, mock_connect):
    """The user flow starts with an empty form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}
    mock_connect.assert_not_called()


async def test_user_flow_aborts_when_unique_id_configured(hass, mock_connect, device):
    """A heatpump that is already configured is not added twice."""
    MockConfigEntry(domain=DOMAIN, version=3, unique_id=SERIAL, data={CONF_HOST: "192.168.1.20"}).add_to_hass(hass)
    mock_connect.return_value = device
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_aborts_when_entry_data_matches(hass, mock_connect):
    """An entry with identical settings aborts before connecting."""
    MockConfigEntry(domain=DOMAIN, version=3, data=ENTRY_DATA).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_connect.assert_not_called()


async def test_user_flow_unknown_error(hass, mock_connect):
    """An unexpected error shows the unknown error."""
    mock_connect.side_effect = ValueError
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_dhcp_flow_aborts_for_other_device(hass, mock_connect):
    """A DHCP discovery that is not confirmed by the broadcast aborts."""
    with patch("custom_components.luxtronik.config_flow.discover", return_value=("192.168.1.99", PORT)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP_DISCOVERY)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "not_luxtronik_device"
    mock_connect.assert_not_called()


async def test_dhcp_flow_aborts_when_unreachable(hass, mock_connect):
    """A DHCP discovery aborts when the heatpump cannot be reached."""
    mock_connect.side_effect = OSError
    with patch("custom_components.luxtronik.config_flow.discover", return_value=(HOST, PORT)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP_DISCOVERY)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_flow_creates_entry(hass, mock_connect, device):
    """A confirmed DHCP discovery prefills the user form and creates an entry."""
    mock_connect.return_value = device
    with patch("custom_components.luxtronik.config_flow.discover", return_value=(HOST, PORT)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP_DISCOVERY)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert schema_defaults(result)[CONF_HOST] == HOST
    assert schema_defaults(result)[CONF_PORT] == PORT
    mock_connect.assert_called_with(HOST, PORT)

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    assert result["result"].unique_id == SERIAL


async def test_dhcp_flow_uses_default_port(hass, mock_connect, device):
    """The default port is used when the broadcast answer has no port."""
    mock_connect.return_value = device
    with patch("custom_components.luxtronik.config_flow.discover", return_value=(HOST, None)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP_DISCOVERY)

    assert result["type"] == FlowResultType.FORM
    assert schema_defaults(result)[CONF_PORT] == DEFAULT_PORT


async def test_dhcp_flow_aborts_when_unique_id_configured(hass, mock_connect, device):
    """A discovered heatpump that is already configured aborts."""
    MockConfigEntry(domain=DOMAIN, version=3, unique_id=SERIAL, data=ENTRY_DATA).add_to_hass(hass)
    mock_connect.return_value = device
    with patch("custom_components.luxtronik.config_flow.discover", return_value=(HOST, PORT)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP_DISCOVERY)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_defaults(hass):
    """The options form falls back to the defaults without data or options."""
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert schema_defaults(result) == {
        CONF_CONTROL_MODE_HOME_ASSISTANT: False,
        CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.luxtronik2_room_temperature",
    }


async def test_options_flow_updates_options(hass):
    """The options form prefers options over data and stores the submitted values."""
    entry = MockConfigEntry(
        domain=DOMAIN, version=3,
        data={CONF_CONTROL_MODE_HOME_ASSISTANT: True, CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.from_data"},
        options={CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.from_options"})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert schema_defaults(result) == {
        CONF_CONTROL_MODE_HOME_ASSISTANT: True,
        CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.from_options",
    }

    user_input = {CONF_CONTROL_MODE_HOME_ASSISTANT: False, CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.living_room"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == user_input


async def test_options_flow_keeps_yaml_sensors(hass):
    """The options form keeps the sensors synced from YAML."""
    sensors = [{"id": "calculations.ID_WEB_Temperatur_TVL"}]
    entry = MockConfigEntry(domain=DOMAIN, version=3, data={}, options={CONF_SENSORS: sensors})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input = {CONF_CONTROL_MODE_HOME_ASSISTANT: False, CONF_HA_SENSOR_INDOOR_TEMPERATURE: "sensor.living_room"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], user_input)

    assert entry.options == {**user_input, CONF_SENSORS: sensors}


async def test_dhcp_flow_aborts_when_broadcast_finds_nothing(hass, mock_connect):
    """A DHCP discovery aborts when no heatpump answers the broadcast."""
    with patch("custom_components.luxtronik.config_flow.discover", return_value=None):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DHCP_DISCOVERY)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "not_luxtronik_device"
    mock_connect.assert_not_called()


async def test_user_flow_stores_update_immediately_after_write(hass, mock_connect, device):
    """The submitted update immediately after write setting is stored."""
    mock_connect.return_value = device
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_UPDATE_IMMEDIATELY_AFTER_WRITE: False})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_UPDATE_IMMEDIATELY_AFTER_WRITE] is False
