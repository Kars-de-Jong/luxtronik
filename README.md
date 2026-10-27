# Luxtronik

This component has been created to be used with Home Assistant.

> :warning: **Use at your own risk!** :warning:  
> You can write config parameters to your heatpump, altering it's efficiency and functionality.  
> Please be careful.

Based on [Bouni/luxtronik](https://github.com/Bouni/luxtronik) / [Bouni/python-luxtronik](https://github.com/Bouni/python-luxtronik). ❤️   

This component extends the original luxtronik component with automatic discovery of the heatpump und home assistant climate thermostat. The `Luxtronik` integration lets you monitor and control heat pump units containing a Luxtronik controller. It is used by various manufacturers such as:

- Alpha Innotec
- Siemens Novelan
- Roth
- Elco
- Buderus
- Nibe
- Wolf Heiztechnik

This integration works locally. It's only necessary to connect the Luxtronik controller to your network using an ethernet cable. No additional hard- or software is needed.

1. [Prerequisites  ](#1-prerequisites)  
2. [Installation  ](#2-installation)  
2.1 [HACS (Recommended)  ](#21-hacs-recommended)  
2.2 [Manual installation  ](#22-manual-installation)  
3. [Adding Luxtronik  ](#3-adding-luxtronik)  
4. [Tips for using Luxtronik  ](#4-tips-for-using-luxtronik)  
4.1 [Energy use  ](#41-energy-use)  
4.2 [Additional sensors (advanced)  ](#42-additional-sensors-advanced)  

## 1. Prerequisites

Before you install this integration, make sure you have:

- A heatpump with a **Luxtronik 2.x controller** (for example Alpha Innotec or Novelan, see the list above).
- The controller **connected to your local network with an ethernet cable**. Home Assistant must be able to reach it.
- A **fixed IP address** for the controller. Configure a DHCP reservation (static lease) in your router, so the address does not change.
- The **network port** of the controller. This is usually `8889`; controllers with older firmware use `8888`.
- **Home Assistant 2024.11.0 or newer**.
- [HACS](https://hacs.xyz/) installed, if you want to use the recommended installation method.

## 2. Installation

### 2.1 HACS (recommended)

Add the custom repository to HACS
1. In Home Assistant, go to `HACS`.
2. Select `Custom repositories` from the menu (three dots) in the top right.
3. Under Repository, enter `https://github.com/Kars-de-Jong/luxtronik`.
4. Under Type (Category), select `Integration`.
5. Click `Add`.

Download the integration
1. Search for `Luxtronik` in HACS and open it.
2. Select `Download` at the bottom right and confirm.
3. Restart Home Assistant (`Settings -> System -> Restart`).

Continue with [Adding Luxtronik](#3-adding-luxtronik).

### 2.2 Manual installation

1. Download the latest release of this integration from the [releases page](https://github.com/Kars-de-Jong/luxtronik/releases).
2. In your Home Assistant configuration directory, create the folder `config/custom_components` if it does not exist yet.
3. Copy the folder `custom_components/luxtronik` from the release into it, so you end up with `config/custom_components/luxtronik` (containing `manifest.json`).
4. Restart Home Assistant.

Continue with [Adding Luxtronik](#3-adding-luxtronik).

## 3. Adding Luxtronik

#### Autodiscovery 

Your heatpump should be autodiscovered by Home Assistant (via DHCP).  
<img src="https://user-images.githubusercontent.com/5879533/178813978-bd8f13ff-ed27-4fa8-bfd0-6ff86a6e9786.png" width="300" />

Press `Configure` and follow the steps to the end. 

#### Manual

If auto discovery does not work, please give feedback with the first six chars of your luxtronik heatpump mac address, the original hostname, the manufacturer and model. 

To add the heatpump manually:
1. Go to `Settings -> Devices & services`.
2. Click `Add integration` and search for `Luxtronik`.
3. Fill in the settings (see below) and click `Submit`.

<img src="https://user-images.githubusercontent.com/5879533/178814105-1dfc9445-1591-417b-9162-0b9f341cd0b2.png" width="500" />

The following settings are available:

- **Host**: the hostname or IP address of your Luxtronik controller.
- **Port**: the network port of the controller, usually `8889` (default) or `8888` on older firmware.
- **Control thermostats through Home Assistant (experimental)**: when a Home Assistant thermostat is idle, the off state is sent to the heatpump, so it cannot start that circuit.
- **Update immediately after writing**: read all values from the heatpump shortly after a setting has been written, so the change shows up without waiting for the next update.
- **Indoor temperature sensor**: the Home Assistant sensor entity that provides the current indoor temperature for the heating thermostat.

> ℹ️ Ensure the IP address is static. This can be configured in your router.

> ℹ️ The connection can only be set up through the UI. The former top-level `luxtronik2:` YAML configuration is no longer supported; remove it from your `configuration.yaml`. The YAML `sensor` and `binary_sensor` platforms (see [Additional sensors](#42-additional-sensors-advanced)) still work.

## 4. Tips for using Luxtronik

It's not always clear from the name alone what an entity exactly means and how it effects your heatpump. The main source of information is ofcourse the [Luxtronik Operating Manual](https://www.alpha-innotec.cz/wp-content/uploads/2019/03/controller2-1.pdf). 

Another great source is [FHEM - Luxtronik 2.0](https://wiki.fhem.de/wiki/Luxtronik_2.0). It's in German so use Google Translate.  
It contains details about the various parameters and how to use them to optimize your heatpump efficiency. Read carfully though. Make small incremental changes and monitor your progress in Home Assistant. You don't want to miss out on this information. 

### 4.1 Energy use

Not all heatpumps have build in electrical energy metering and instead only show the energy produced in heat, not the energy consumed in electricity. Adding a (strong) energy meter is a nice addition to measure the SCOP of your device. Shelly energy meters are recommended since they offer offer a [16A power plug](https://www.shelly.com/en-nl/products/product-overview/1xplug) and a [variety of in-line or clamp energy meters](https://www.shelly.com/en-nl/products/energy-metering-energy-efficiency) with various protection mechanisms. 

### 4.2 Additional sensors (advanced)

The most usefull sensors and parameters are created automaticly. But if you miss a sensor you can add it manually via yaml configuration like the original module from [Bouni/luxtronik](https://github.com/Bouni/luxtronik).

A short description of many of the available sensors can be found here [Loxwiki - Luxtronik Java Web Interface](https://loxwiki.atlassian.net/wiki/spaces/LOX/pages/1533935933/Java+Webinterface)

#### Parameter IDs

Take these files as a reference to figure ot which IDs to use:

- https://github.com/Bouni/python-luxtronik/blob/master/luxtronik/parameters.py
- https://github.com/Bouni/python-luxtronik/blob/master/luxtronik/calculations.py
- https://github.com/Bouni/python-luxtronik/blob/master/luxtronik/visibilities.py

#### Service

In order to change parameters on the Luxtronik conroller, you can use the following service:

```yaml
Domain: luxtronik2
Service: write
Service Data: {"parameter": "ID_Ba_Hz_akt", "value": "Automatic"}
```

- parameter
  - description: ID of the parameter.
  - type: string
- value
  - description: Value you want to set the parameter to.
  - type: [string, float]

Only a small number of the over 1100 parameters have a known funtion and only these can be written, these are:

- `ID_Ba_Hz_akt` The mode of operation of the heating circuit, possible values are "Automatic", "Second heatsource", "Party", "Holidays", "Off"
- `ID_Ba_Bw_akt` The mode of operation of the hot water circuit, possible valus are "Automatic", "Second heatsource", "Party", "Holidays", "Off"
- `ID_Soll_BWS_akt` The set point for hot water generation, for example 50.0 for 50.0°C 
- `ID_Einst_BA_Kuehl_akt` The mode of operation of the cooling circuit, possible values are "Automatic", "Off"
- `ID_Einst_KuehlFreig_akt` The outdoor temprature from wher on the cooling should start to operate, for example 24.0 
- `ID_Ba_Sw_akt` The mode of operation of the swimming pool heating circuit, possible values are "Automatic", "Party", "Holidays", "Off"
- `ID_Einst_TDC_Max_akt` Max. temperature difference of the hot water buffer tank, for example 70.0
- `ID_Sollwert_KuCft1_akt` Cooling set point for mixer circuit 1, for example 19.0
- `ID_Sollwert_KuCft2_akt` Cooling set point for mixer circuit 2, for example 19.0
- `ID_Sollwert_AtDif1_akt` Cooling working temperature difference 1, for example 5.0
- `ID_Sollwert_AtDif2_akt` Cooling working temperature difference 2, for example 5.0
- `ID_Ba_Hz_MK3_akt` The mode of operation of the heating mixer circuit 3, possible values are "Automatic", "Party", "Holidays", "Off"
- `ID_Einst_Kuhl_Zeit_Ein_akt` Cooling outdoor temperature overrun, for example 0.0
- `ID_Einst_Kuhl_Zeit_Aus_akt` Cooling outdoor temperature underrun, for example 0.0
- `ID_Einst_Solar_akt` Mode of operation for solar heat generation, "Automatic", "Second heatsource", "Party", "Holidays", "Off"
- `ID_Einst_BA_Lueftung_akt` Mode of operation of the integrated ventilation unit, posisble values are "Automatic", "Party", "Holidays", "Off"
- `ID_Sollwert_KuCft3_akt` Cooling set point for mixer circuit 3, for example 20.0
- `ID_Sollwert_AtDif3_akt` Cooling working temperature difference 3, for example 5.0

> ℹ️ Before changing a parameter it smart to first read the current value and note it somewhere in case you want to set it back to its original value.
All parameters can be configured as sensors and read that way.

#### Sensor

The Luxtronik sensor platform allows you to monitor the status values of a heat pump unit controlled by a Luxtronik controller.

Sensors are read-only. These YAML platforms require the integration to be set up through the UI first (see [Adding Luxtronik](#3-adding-luxtronik)). To write to the heatpump, use the provided service Luxtronik Integration - Service.

To use a Luxtronik sensor in your installation, add the following lines to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
sensor:
  - platform: luxtronik2
    sensors:
      - group: calculations
        id: ID_WEB_Temperatur_TVL
```

- group:
  - description: Value group where the ID is located, possible values are `calculations`, `parameters`, `visibilities`.
  - required: false, if group is provided in id.
  - type: string
- id:
  - description: The id of the value or the group.id (`calculations`, `parameters`, `visibilities`). e.g. calculations.ID_WEB_Temperatur_TVL
  - required: true
  - type: string
- friendly_name:
  - description: Sets a meaningful name for the sensor, if not provided the sensor will be named after the id, `sensor.luxtronik2_id_webemperatur_tvl` for example, otherwise `sensor.luxtronik2_temperature_forerun`.
  - required: false
  - type: string
- icon:
  - description: Set an icon for the sensor
  - required: false
  - type: string

#### Full example

```yaml
# Example configuration.yaml entry
sensor:
  - platform: luxtronik2
    sensors:
      - group: calculations
        id: ID_WEB_Temperatur_TVL
      - id: calculations.ID_WEB_Temperatur_TVL
        friendly_name: Temperature forerun
        icon: mdi:thermometer
```

#### Binary Sensor

The Luxtronik binary sensor platform allows you to monitor the status values of a heat pump unit controlled by a Luxtronik controller.

Binary sensors are read-only. To write to the heatpump, use the provided service Luxtronik Integration - Service.

To use a Luxtronik binary sensor in your installation, add the following lines to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry
binary_sensor:
  - platform: luxtronik2
    sensors:
      - group: calculations
        id: ID_WEB_EVUin
```

- group:
  - description: Value group where the ID is located, possible values are `calculations`, `parameters`, `visibilities`.
  - required: false, if group is provided in id.
  - type: string
- id:
  - description: The id of the value or the group.id (`calculations`, `parameters`, `visibilities`). e.g. calculations.ID_WEB_Temperatur_TVL
  - required: true
  - type: string
- friendly_name:
  - description: Sets a meaningful name for the sensor, if not provided the sensor will be named after the id, `sensor.luxtronik2_id_web_evuin` for example, otherwise `sensor.luxtronik2_utility_company_lock`.
  - required: false
  - type: string
- icon:
  - description: Set an icon for the sensor
  - required: false
  - type: string
- invert:
  - description: Inverts the value
  - required: false
  - type: boolean
  - default: false

#### Full example

```yaml
# Example configuration.yaml entry
binary_sensor:
  - platform: luxtronik2
    sensors:
      - group: calculations
        id: ID_WEB_EVUin
      - id: calculations.ID_WEB_EVUin
        friendly_name: Utility company lock
        icon: mdi:lock
```

## Some Screenshots
![image](https://user-images.githubusercontent.com/32298537/178588098-09e960f0-f849-475c-9afa-cf4a78e5d76d.png)
![image](https://user-images.githubusercontent.com/32298537/178588218-56f914f0-1ec5-4851-84ff-1d53bf8d4c1d.png)
![image](https://user-images.githubusercontent.com/32298537/178588500-2ec97e7f-c542-492c-9db0-3fcb68e1fe5c.png)
![image](https://user-images.githubusercontent.com/32298537/178588584-3a1004ff-dc8f-47bf-9c32-1d9aae0a3aeb.png)
![image](https://user-images.githubusercontent.com/32298537/178588670-0af53cc6-086d-4545-b3d0-0208043c188f.png)
![image](https://user-images.githubusercontent.com/32298537/178588738-6588f1c8-1840-4961-a4f8-c956df5f600c.png)
