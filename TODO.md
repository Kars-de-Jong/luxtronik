# TODO

These issues came up while bringing the integration to the Home Assistant Integration Quality Scale **Bronze** tier (commits `1ca89f7`..`e15d33c` on `legacy`). None of them was fixed in that work.

Paths are relative to `custom_components/luxtronik/` unless noted otherwise. Line numbers are as of commit `e15d33c`, so verify them before editing.

Conventions from the Bronze work:
- **One commit per fix.**
- **Write the failing test first.** Run tests with `.venv/bin/pytest` and lint with `.venv/bin/flake8 . --count --select=E9,F63,F7,F82 --exclude=.venv`.
- **Use the shared test fixtures.** `tests/conftest.py` has a `luxtronik` fixture: a MagicMock device patched over `custom_components.luxtronik.LuxtronikDevice`.
- **No `Co-Authored-By` lines** in commits.
- **Update `quality_scale.yaml`** when a fix completes a quality scale rule.

## Bugs

### 1. The write debounce drops writes to other parameters and other heatpumps
- **Where:** `helpers/debounce.py` and `luxtronik_device.py:193` (`@debounce(3)` on `__write_debounced`).
- **Problem:** the decorator keeps a single `Timer` on the decorated *function*. That timer is shared across all calls, all parameters and all `LuxtronikDevice` instances. Two writes within 3 s cancel each other, so only the last one is executed, even if it is for a different parameter or a different heatpump. Entities (climate, number, switch) and the `luxtronik2.write` action all write through it.
- **Fix idea:**
  - Debounce per `(device, parameter)`: keep a dict of timers on the instance, keyed by parameter.
  - Or drop the debounce and write directly in the executor.
- **Test:** call `write("A", 1)` and then `write("B", 2)` straight away, and assert that both parameters reach `_luxtronik.parameters.set`. Patch `Timer` or use a short wait.
- **README:** `README.md` (section "5. Actions") currently warns users to leave 3 s between calls. Update that text after the fix.

### 2. The lock is released even when acquiring it timed out
- **Where:** `luxtronik_device.py`:
  - `__write`: `acquire` at line ~201, `release` in `finally` at ~218.
  - `read`: `acquire` at ~241, `release` at ~249.
- **Problem:** when `self.lock.acquire(timeout=...)` returns False, the `finally` still calls `self.lock.release()`, which raises `RuntimeError: release unlocked lock`.
- **Fix:** only release when the lock was acquired, e.g. `if acquired: self.lock.release()`. Alternatively, use a context-manager helper; there is a TODO comment for that already.
- **Test:** hold the lock in the test, use a tiny `_lock_timeout_sec`, call `read()`, and expect the warning log and no exception.

### 3. Thermal disinfection stores the method instead of the date
- **Where:** `number.py:354`, `LuxtronikNumberThermalDesinfection.update`.
- **Problem:** `self._last_thermal_desinfection = datetime.now().date` is missing `()`. Because of that, the comparison at line 353 (`isinstance(..., date)`) never sees a real date afterwards. Also check how the value is restored from state attributes in `async_added_to_hass`: it comes back as a string there.
- **Fix:** use `datetime.now().date()`, and parse the restored attribute back to a `date`.

### 4. The v1 config entry migration blocks the event loop
- **Where:** `__init__.py:239-241`, `async_migrate_entry`.
- **Problem:** `LuxtronikDevice.connect(...)` runs synchronously in the event loop, and a connection `OSError` is not handled.
- **Fix:**
  - Use `await hass.async_add_executor_job(LuxtronikDevice.connect, host, port)`.
  - On `OSError`, return False (migration fails and is retried on the next start) or raise `ConfigEntryNotReady`. Check what HA allows during migration.
- **Test:** extend `tests/test_migration.py`.

### 5. Firmware update entity: blocking I/O and concurrent HTTP requests
- **Where:** `update.py`.
- **Problems:**
  - `luxtronik_device.read()` is called in `async_setup_entry` (line ~45) and again in the entity `__init__` (~85). This is blocking socket I/O in the event loop.
  - The `latest_version` property (~97) calls `_request_available_firmware_version()` on every state write until the first answer has arrived. Each call starts a new `threading.Thread` doing `requests.get(...)` (~134-157), so several requests can run at the same time.
- **Fix idea:**
  - Remove the reads; the device was already read during setup in `build_runtime_data`.
  - Fetch the firmware version in `async_update` using HA's aiohttp session (`async_get_clientsession`). That also covers the Platinum rules `inject-websession` and `async-dependency`, both `todo` in `quality_scale.yaml`.
  - Keep `SCAN_INTERVAL = 1h`.

## Improvements

### 6. Let the `luxtronik2.write` action target a specific heatpump
- **Where:** `__init__.py`, `async_setup` → `write_parameter`.
- **Problem:** the action always uses the first loaded config entry (`hass.config_entries.async_loaded_entries(DOMAIN)[0]`).
- **Fix:**
  - Add an optional `config_entry_id` field, with a `config_entry` selector (`integration: luxtronik2`) in `services.yaml`.
  - Fall back to the first entry when it is omitted.
  - Raise `ServiceValidationError` for an unknown or unloaded entry.
- **Docs:** update the README "5. Actions" section.

### 7. Unknown parameter names in `luxtronik2.write` fail silently
- **Problem:** the `luxtronik` library (0.3.14, `parameters.py`) only logs a warning and writes nothing when a parameter is unknown. The action returns before the write happens because of the debounce, so the user gets no error.
- **Fix:** validate the parameter in the action handler before scheduling the write: `device._luxtronik.parameters.get(parameter)`, or add a helper on `LuxtronikDevice`. Raise `ServiceValidationError` when it is unknown.
- **Library limitation:** in `parameters.py:1201` the check `if index:` means parameter index 0 can never be written by number.
- **Values are strings:** the `text` selector in `services.yaml` sends strings. Parameters whose conversion uses `int()` would fail on input like "19.0".

### 8. Remove dead dispatcher subscriptions
- **Where:** `sensor.py:1064` (`LuxtronikStatusSensor`) and `number.py:363` (`LuxtronikNumberThermalDesinfection`).
- **Problem:** both subscribe to `f"{DOMAIN}_data_updated"`, but nothing ever calls `async_dispatcher_send` for that signal. They are cleaned up correctly now, but they never fire.
- **Fix:** remove them (and `_schedule_immediate_update`), and update `tests/test_entity_event_setup.py` to match. Alternatively, send the signal after a write that re-reads values (`update_immediately_after_write`), if that was the original intent.
- **Also:** `self._state = state.state` in both `async_added_to_hass` methods (`sensor.py:1073`, `number.py:372`) looks unused.

### 9. YAML platforms can miss the config entry at startup
- **Where:** `model.py` (`get_runtime_data`) and `sensor.py`/`binary_sensor.py` `async_setup_platform`.
- **Problem:** if the YAML `sensor:` platform is set up before the Luxtronik config entry has stored its runtime data, the YAML sensors are skipped with a warning. The old code had the same race.
- **Fix idea:** raise `PlatformNotReady` instead of returning, so HA retries.

### 10. Device info `sw_version` may not be a string
- **Where:** `__init__.py:226`, `sw_version=luxtronik.get_value("calculations.ID_WEB_SoftStand")`.
- **Problem:** HA warns that a non-string `sw_version` will fail from 2026.12. In the tests the value is an int because the mock returns 1. In real use it is probably a string, but nothing guarantees it.
- **Fix:** wrap it in `str(...)`, or use `luxtronik.firmware_version`, which already does `str()`.

### 11. Config flow cleanups
- **Where:** `config_flow.py`.
- **Problems:**
  - `_async_abort_entries_match(data)` (~line 113) matches on *all* fields, so it only aborts when every option is identical. It should match on `{CONF_HOST: ..., CONF_PORT: ...}` only. The unique-id check catches real duplicates today.
  - `CONF_SAFE: False` and `CONF_LOCK_TIMEOUT: 30` (~101-102) are hardcoded.
  - `update_immediately_after_write` can only be set at setup; the options flow doesn't offer it.
  - `control_mode_home_assistant` and `ha_sensor_indoor_temperature` are stored in `data` at setup and in `options` afterwards. `climate.py` merges both (`{**data, **options}`). A cleaner split would store them in `options` from the start, which needs a config entry migration.
  - The fields use plain `str`/`int`/`bool`. Selectors would be better, e.g. an `EntitySelector(domain="sensor", device_class="temperature")` for the indoor temperature sensor.
  - The options flow uses step id `user`, reached via `async_step_init`. HA convention is `init`, so the translations would need to move to match.
  - The `existing_instance_updated` abort string in the translations looks unused.
  - When the DHCP step finds an already configured unique id, it does not update the host of the existing entry. That is the Gold rule `discovery-update-info`.

### 12. Housekeeping
- `manifest.json` `"version"` is still `2023.9.10`.
- README typos outside the parts that were rewritten: "ofcourse", "carfully", "heatpump und home assistant" in the intro. The YAML Binary Sensor section also doesn't mention that a UI config entry is required; the Sensor section does.
- The tests trigger flake8 E128 warnings (continuation indent of the import blocks), and there is one E302 in `tests/test_init.py`. CI only fails on E9/F63/F7/F82.
- `setup.cfg` sets `max-line-length = 88` but ignores E501.
- `tests/test_entity_naming.py` defines its own `SERIAL` while `tests/conftest.py` also has one.
- Coverage counts only function bodies in `custom_components`, because modules are imported before coverage starts, so module-level lines aren't measured.
- Consider adding the `home-assistant/actions/hassfest` GitHub Action to `.github/workflows/validate.yaml` to validate `manifest.json` and `quality_scale.yaml`.

## Next quality scale tier (Silver)
See `quality_scale.yaml` for the full list. The relevant items found so far:
- **`parallel-updates`:** nothing sets `PARALLEL_UPDATES`.
- **`action-exceptions`:** see items 6 and 7.
- **`log-when-unavailable` and `entity-unavailable`:** entities don't go unavailable when reads fail.
- **`config-entry-unloading`:** probably close to done after the runtime-data work. Verify, then mark it.
- **`reauthentication-flow`:** exempt, because there is no authentication.
