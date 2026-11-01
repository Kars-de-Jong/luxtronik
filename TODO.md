# TODO

These issues came up while bringing the integration to the Home Assistant Integration Quality Scale **Bronze** tier (commits `1ca89f7`..`e15d33c` on `legacy`). None of them was fixed in that work.

Paths are relative to `custom_components/luxtronik/` unless noted otherwise. Line numbers are as of commit `e15d33c`, so verify them before editing.

Conventions from the Bronze work:
- **One commit per fix.**
- **Write the failing test first.** Run tests with `.venv/bin/pytest` and lint with `.venv/bin/flake8 . --count --select=E9,F63,F7,F82 --exclude=.venv`.
- **Use the shared test fixtures.** `tests/conftest.py` has a `luxtronik` fixture: a MagicMock device patched over `custom_components.luxtronik.LuxtronikDevice`.
- **Update `quality_scale.yaml`** when a fix completes a quality scale rule.
- **Validate with hassfest** after changes to `manifest.json`, `strings.json`, `translations/`, `services.yaml` or `quality_scale.yaml`: `docker run --rm -v "$PWD":/github/workspace ghcr.io/home-assistant/hassfest` from the repository root. This is the image the `home-assistant/actions/hassfest` GitHub Action uses. It currently reports the errors listed in item 4; a fix must not add new ones.

## Improvements

### 1. YAML platforms can miss the config entry at startup
- **Where:** `model.py` (`get_runtime_data`) and `sensor.py`/`binary_sensor.py` `async_setup_platform`.
- **Problem:** if the YAML `sensor:` platform is set up before the Luxtronik config entry has stored its runtime data, the YAML sensors are skipped with a warning. The old code had the same race.
- **Fix idea:** raise `PlatformNotReady` instead of returning, so HA retries.

### 2. Config flow cleanups
- **Where:** `config_flow.py`.
- **Problems:**
  - `_async_abort_entries_match(data)` (~line 113) matches on *all* fields, so it only aborts when every option is identical. It should match on `{CONF_HOST: ..., CONF_PORT: ...}` only. The unique-id check catches real duplicates today.
  - `CONF_SAFE: False` and `CONF_LOCK_TIMEOUT: 30` (~101-102) are hardcoded.
  - `update_immediately_after_write` can only be set at setup; the options flow doesn't offer it.
  - `control_mode_home_assistant` and `ha_sensor_indoor_temperature` are stored in `data` at setup and in `options` afterwards. `climate.py` merges both (`{**data, **options}`). A cleaner split would store them in `options` from the start, which needs a config entry migration.
  - The fields use plain `str`/`int`/`bool`. Selectors would be better, e.g. an `EntitySelector(domain="sensor", device_class="temperature")` for the indoor temperature sensor.
  - The options flow uses step id `user`, reached via `async_step_init`. HA convention is `init`, so the translations would need to move to match.
  - The default indoor temperature sensor is `sensor.luxtronik2_room_temperature`. Since entity IDs are generated from the device name, new installs call the heatpump's room sensor `sensor.heatpump_<serial>_heating_room`, so the default points to an entity that doesn't exist and the climate entity shows no current temperature. Look up the room sensor by unique ID (`<serial>_room_temperature`) instead, or use an `EntitySelector` without a default.
  - `control_mode_home_assistant` has no effect. The climate entity only read it in a branch that could never run, which was removed. Remove the option (with a config entry migration) or implement what it was meant to do.
  - The `existing_instance_updated` abort string in the translations looks unused.
  - When the DHCP step finds an already configured unique id, it does not update the host of the existing entry. That is the Gold rule `discovery-update-info`.

### 3. Housekeeping
- `manifest.json` `"version"` is still `2023.9.10`.
- README typos outside the parts that were rewritten: "ofcourse", "carfully", "heatpump und home assistant" in the intro. The YAML Binary Sensor section also doesn't mention that a UI config entry is required; the Sensor section does.
- The tests trigger flake8 E128 warnings (continuation indent of the import blocks), and there is one E302 in `tests/test_init.py`. CI only fails on E9/F63/F7/F82.
- `setup.cfg` sets `max-line-length = 88` but ignores E501.
- `tests/test_entity_naming.py` defines its own `SERIAL` while `tests/conftest.py` also has one.
- Consider adding the `home-assistant/actions/hassfest` GitHub Action to `.github/workflows/validate.yaml` to validate `manifest.json` and `quality_scale.yaml`. Fix the errors in item 4 first, or the job fails.

### 4. hassfest errors
Running hassfest (see Conventions) currently reports:
- **`manifest.json` has a `homeassistant` key.** Not a valid manifest option; the minimum version belongs in `hacs.json` only, which already has it. Remove it from the manifest.
- **Domain does not match the directory name.** The domain is `luxtronik2`, the directory is `luxtronik`. Renaming either one is a breaking change (entity IDs, config entries, the `luxtronik2.write` action, YAML config), inherited from upstream. Decide whether to fix it with a migration or accept this error.
- **Invalid translation key `-1`** in `entity.sensor.switchoff_reason.state` in `strings.json` and `translations/en.json`. State keys must match `[a-z0-9-_]+` and can't start with a hyphen. Map the value `-1` to a valid key (e.g. `unknown`) in the sensor, then rename the translation key.

### 5. Findings from the best practices review
- **Use HA translations instead of the own text files.** Device names via `translation_key` on the device info, status sensors as `SensorDeviceClass.ENUM` with translated states, the action texts in the `services` section of `strings.json`. Exception translations are done for the write action and entity writes; `ConfigEntryNotReady` in `__init__.py` and `UpdateFailed` in `coordinator.py` still use plain messages (`exception-translations`). `translations/climate.de.json` is not loaded by anything.
- **Icons:** move the `icon` properties to `icons.json` (`icon-translations`).
- **Extra state attributes** have free-text German keys (`'WP Seit (ID_WEB_Time_WPein_akt)'`, `'EVU first start time'`) and every entity has `Luxtronik_Key`. Prefer snake_case keys, or separate disabled-by-default diagnostic sensors. Breaking for automations that use them.
- **Config flow:** `FlowResult` is deprecated, use `ConfigFlowResult`; type `async_step_dhcp` with `DhcpServiceInfo`; consider `OptionsFlowWithReload` instead of the update listener.
- **Logging:** setup logs the full config entry at `info` level; f-strings in log calls.
- **`manifest.json`:** `after_dependencies: ["http"]` looks unused.
- **Swallowed keyword arguments:** `LuxtronikSwitch.__init__` takes `*args, **kwargs` and ignores them, so `entity_registry_enabled_default=False` on the `pump_heat_control` switch has no effect and the switch is enabled for new installs. Passing it on would disable the switch by default for new installs only; existing registry entries keep their setting.
- **Thermal disinfection number:** `_update_attrs` calls `float(self.native_value)`, which raises when the heatpump has no value for the target.
- **`LuxtronikEntityDescription`** should be `@dataclass(frozen=True, kw_only=True)`.
- **`setup.cfg`:** mypy targets Python 3.7 with `ignore_errors = true`.
- **Coordinator follow-ups:**
  - The status sensor builds `status_text` from the states of the status time and status line sensors. They are updated after it, so the text lags one update (30 s) behind. Building it from the device values would fix that.
  - The climate entity reads the indoor temperature sensor from `hass.states` only when the coordinator updates. Tracking that sensor's state changes would show changes at once.
  - `homeassistant.update_entity` requests a coordinator refresh, which waits 3 s like the refresh after a write.
  - Debounced writes (the `luxtronik2.write` action and the number entities) run after the call returned, so a device error (lock timeout, unreachable heatpump) is only logged. A repair issue or a persistent notification would make it visible.
