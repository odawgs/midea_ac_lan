# Midea split heat pump water heater (MHW-V28WD2N7 / 171000AU) for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Stable](https://img.shields.io/github/v/release/odawgs/midea_ac_lan?include_prereleases)](https://github.com/odawgs/midea_ac_lan/releases/latest)

Local Home Assistant control of the **Midea MHW-V28WD2N7 split heat pump water heater** (model code `171000AU`), built as a fork of the [Midea AC LAN](https://github.com/wuwentao/midea_ac_lan) integration by wuwentao.

The unit reports as Midea device type `C3` but speaks a different protocol from the air-to-water heat pumps that type normally means. With the original integration it shows up as two climate zones, a tank at 98 °C and error code 7. Here it gets a working water heater entity plus the sensors, switches and settings the Midea app offers, all over the local network. The MSmartHome app keeps working alongside Home Assistant.

> **Scope of this fork:** the split heat pump water heater is the **only device maintained here**. All other appliances (air conditioners, dehumidifiers, washers and so on) are an unmodified copy of upstream at v2026.9.2 and are not tested, updated or supported in this fork. For any other Midea appliance use [wuwentao/midea_ac_lan](https://github.com/wuwentao/midea_ac_lan) and report problems there. This fork is provided as is, with no support channel.

## Is this your unit?

It goes by several names, so if you searched for any of these you are in the right place:

- Midea **MHW-V28WD2N7** split heat pump water heater / heat pump hot water system (sold in Australia, usually with the MT-300R28E20 300 L tank)
- **Split HPWH** in the Midea **MSmartHome** app
- Model code **171000AU**, shown in Home Assistant as _Heat Pump Wi-Fi Controller 171000AU_ or _Central Heating Water Heater_, device type **C3** (`0xC3`)
- Symptoms with the standard Midea AC LAN integration: tank temperature stuck at **98 °C**, **error code 7** (_E6: Ambient temp. sensor (T4) fault_), a water heater that is always `off` with a 20 °C target, and two heating zones that do not exist

## What you get

Created by default:

- `water_heater` entity with on/off and target temperature (range as reported by the unit, 52-60 °C)
- Tank temperature (upper and bottom probes), ambient temperature, input power, run mode
- Electric heater and compressor energy over the last 24 h
- Compressor running, backup heater running, disinfection running
- Switches: Auxiliary heater, Disinfect now, Auto disinfection
- Settings: backup heater on temperature, restart offset, disinfection hour, temperature and cycle

Optional extra sensors (energy counter, current, compressor frequency, run hours) and disabled-by-default diagnostics (coil, discharge and suction temperatures, voltages, currents, firmware versions) are listed in [doc/C3.md](doc/C3.md#split-heat-pump-water-heater-model-171000au), together with notes on how the unit behaves.

## Install

Home Assistant 2024.4.1 or newer is required.

### Via HACS (recommended)

1. In HACS, open the menu (three dots, top right) and choose **Custom repositories**.
2. Add `https://github.com/odawgs/midea_ac_lan` with type **Integration**.
3. Search HACS for **Midea AC LAN** and download the one from `odawgs/midea_ac_lan` (not the upstream entry with the same name).
4. Restart Home Assistant.

Or open it directly: [![Open your Home Assistant instance and open this repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=odawgs&repository=midea_ac_lan&category=integration)

If you already have the upstream Midea AC LAN installed, remove it first. Both use the same `midea_ac_lan` folder, so only one can be installed; your configured devices are kept.

### Manually

1. Download the source zip of the [latest release](https://github.com/odawgs/midea_ac_lan/releases/latest).
2. Copy `custom_components/midea_ac_lan` from the zip into `/config/custom_components/` in Home Assistant, so `manifest.json` ends up at `/config/custom_components/midea_ac_lan/manifest.json`.
3. Restart Home Assistant.

## Add the water heater

1. Give the unit a fixed IP address in your router first, so Home Assistant does not lose it later.
2. Go to **Settings → Devices & services → Add integration** and pick **Midea AC LAN**, or click [![Configuration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=midea_ac_lan).
3. Sign in with the MSmartHome account the water heater is registered to. The login is used once, to fetch the unit's Token and Key from the Midea cloud; after that everything is local.
4. Choose **Discover automatically** (or enter the unit's IP address if it is on another subnet) and add the device. It is recognised by its model code, so no extra configuration is needed.
5. Back up the unit's `.json` file from `.storage/midea_ac_lan/` in your Home Assistant config. If Midea ever closes the Token service, that file lets you re-add the unit without the cloud. See [doc/debug.md](doc/debug.md#4-obtain-device-json-configuration).

> Only a personal MSmartHome account that owns the appliance can fetch the Token. Do not migrate an account from another Midea app; create a fresh account if needed.

## Options

**Settings → Devices & services → Midea AC LAN → Devices → Configure** lets you change the IP address, the refresh interval (default 30 s; the unit also pushes changes on its own) and which extra sensors are created. The entities and their meanings are in [doc/C3.md](doc/C3.md#split-heat-pump-water-heater-model-171000au).

## Debugging and development

- Debug logs and testing: [doc/debug.md](doc/debug.md)
- Development setup (uses [uv](https://docs.astral.sh/uv/)): [CONTRIBUTING](.github/CONTRIBUTING.md)

## Credits

All of the device discovery, encryption and the integration framework come from [wuwentao/midea_ac_lan](https://github.com/wuwentao/midea_ac_lan) and the [midea-lan](https://github.com/wuwentao/midea-lan) library. This fork only adds the split heat pump water heater protocol on top. Licensed under the same terms as upstream, see [LICENSE](LICENSE).
