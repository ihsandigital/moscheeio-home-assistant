<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ihsandigital/moscheeio-home-assistant/main/custom_components/moscheeio/brand/dark_logo.png">
    <img alt="moschee.io" src="https://raw.githubusercontent.com/ihsandigital/moscheeio-home-assistant/main/custom_components/moscheeio/brand/logo.png" width="300">
  </picture>
</p>

<h1 align="center">moschee.io for Home Assistant</h1>

<p align="center">
  Power the sound desk on before Fajr without anyone in the mosque, switch it from the moschee.io
  dashboard and app, and see the desk's channels in Home Assistant.
</p>

<p align="center">
  <a href="https://hacs.xyz/"><img alt="HACS Custom" src="https://img.shields.io/badge/HACS-Custom-41BDF5?style=for-the-badge&logo=homeassistantcommunitystore&logoColor=white"></a>
  <a href="https://github.com/ihsandigital/moscheeio-home-assistant/releases"><img alt="Release" src="https://img.shields.io/github/v/release/ihsandigital/moscheeio-home-assistant?style=for-the-badge"></a>
  <a href="https://www.home-assistant.io/"><img alt="Home Assistant version" src="https://img.shields.io/badge/dynamic/json?style=for-the-badge&logo=homeassistant&logoColor=white&color=41BDF5&label=Home%20Assistant&suffix=%2B&url=https%3A%2F%2Fraw.githubusercontent.com%2Fihsandigital%2Fmoscheeio-home-assistant%2Fmain%2Fhacs.json&query=%24.homeassistant"></a>
  <a href="https://github.com/ihsandigital/moscheeio-home-assistant/actions/workflows/validate.yml"><img alt="Validate" src="https://img.shields.io/github/actions/workflow/status/ihsandigital/moscheeio-home-assistant/validate.yml?branch=main&style=for-the-badge&label=validate"></a>
  <img alt="Beta" src="https://img.shields.io/badge/status-beta-F59E0B?style=for-the-badge">
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/github/license/ihsandigital/moscheeio-home-assistant?style=for-the-badge"></a>
</p>

> [!IMPORTANT]
> **Beta.** This integration and moschee.io's Smart Mosque are in beta. The sound desk's channels
> work with desks of the **Behringer X32** family only for now (X32, Compact, Producer, Rack, Core).

This integration connects Home Assistant to your mosque on [moschee.io](https://moschee.io). The
switches you share, such as the smart plug of the sound desk, appear next to the desk in moschee.io.
moschee.io's switch rules run in Home Assistant at the prayer times, also while the internet is
down. And the channels of the mosque's sound desk come to Home Assistant as entities.

<p align="center">
  <img alt="A Behringer X32 Compact in Home Assistant: a switch and a level in dB for each channel set up in moschee.io, such as Imam, Minbar and Muezzin" src="https://raw.githubusercontent.com/ihsandigital/moscheeio-home-assistant/main/docs/images/desk-device.png" width="760">
</p>

## Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Setup](#setup)
- [In moschee.io](#in-moscheeio)
- [Switch rules](#switch-rules)
- [Entities](#entities)
- [Automation examples](#automation-examples)
- [Safety](#safety)
- [What moschee.io sees](#what-moscheeio-sees)
- [Data updates](#data-updates)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Removal](#removal)
- [Reporting a bug](#reporting-a-bug)
- [How it works](#how-it-works)
- [Development](#development)

## Features

| | |
| --- | --- |
| 🔌 **Switches next to the desk** | The Home Assistant switches you share, such as the sound desk's power, appear in moschee.io under **Smart Mosque → Mixer** and in the moschee.io app, and can be switched from there. |
| 🕌 **Switch rules at the prayer times** | Rules like "turn the desk on 15 minutes before Fajr" or "turn it off 30 minutes after Isha" are set up in moschee.io and run in Home Assistant from the mosque's prayer timetable. |
| 📡 **Works without internet** | The rules and the prayer times of the next seven days are kept on Home Assistant's disk. Runs that could not be reported are sent once the connection is back. |
| 🎚️ **The desk's channels in Home Assistant** | The channels set up in moschee.io appear as entities, with their level in dB. You can mute and unmute them from Home Assistant if moschee.io allows it. |
| 🛡️ **Safe during the prayer** | Nothing is switched off while a translation is live, and a protected channel such as the imam's microphone is never muted from Home Assistant during the prayer. |

## Prerequisites

- A mosque on [moschee.io](https://moschee.io) with **Smart Mosque**, included in the **Gemeinde Plus** and
  **Reichweite** plans, and an account that is an owner or admin of the mosque.
- The mosque's prayer timetable in moschee.io: the switch rules follow it.
- Home Assistant **2025.2** or newer.
- [HACS](https://hacs.xyz/docs/use/download/download/), unless you install the integration manually.
- For the desk's channels: a Behringer X32 connected to moschee.io through a Smart-Mosque-Box. The
  shared switches and the switch rules work without a box.

## Installation

### With HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ihsandigital&repository=moscheeio-home-assistant&category=integration)

The button adds this repository to HACS in your Home Assistant. To add it by hand instead:

1. Open **HACS**, then the ⋮ menu at the top right, and pick **Custom repositories**.
2. Enter `https://github.com/ihsandigital/moscheeio-home-assistant` as the repository, pick
   **Integration** as the type and select **Add**.
3. Search HACS for **moschee.io**, open it and select **Download**.
4. Restart Home Assistant.

HACS tells you when a new version is out.

### Manually

1. Download the source code of the [latest release](https://github.com/ihsandigital/moscheeio-home-assistant/releases/latest).
2. Copy its `custom_components/moscheeio` folder into the `custom_components` folder of your Home
   Assistant configuration directory, the one with `configuration.yaml`. Create `custom_components`
   if it is missing.
3. Restart Home Assistant.

Take a release, not the `main` branch, which may hold changes that are not released yet.

## Setup

[![Open your Home Assistant instance and start setting up moschee.io.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=moscheeio)

Home Assistant pairs with your mosque by a code, the same way a Smart-Mosque-Box does. You never
enter a password in Home Assistant.

1. Go to [**Settings → Devices & services**](https://my.home-assistant.io/redirect/integrations/),
   select **Add integration** and pick **moschee.io**. Confirm the first step.
2. Home Assistant shows a link and a code. Open the link on any device, sign in to moschee.io as an
   owner or admin of your mosque, check that the code matches, choose your mosque and confirm.
3. Home Assistant continues on its own and names the entry after your mosque.

<p align="center">
  <img alt="Home Assistant shows a link to moschee.io and the code to confirm there" src="https://raw.githubusercontent.com/ihsandigital/moscheeio-home-assistant/main/docs/images/pairing.png" width="520">
</p>

### Sharing switches

moschee.io sees nothing from Home Assistant until you share it. On the integration's card in
**Settings → Devices & services**, select **Configure**:

1. Choose the entities moschee.io may see and switch: `switch`, `input_boolean` and `light`
   entities, up to 50. A smart plug for the sound desk's power is the typical one.
2. Choose which of them moschee.io asks about before switching off. moschee.io then asks for a
   confirmation, and warns while a translation is live.

You can change the choice at any time. The desk's own channels are not offered here, because moschee.io
switches them directly.

<p align="center">
  <img alt="The Configure dialog with the sound desk power and the amplifier shared with moschee.io" src="https://raw.githubusercontent.com/ihsandigital/moscheeio-home-assistant/main/docs/images/configure.png" width="520">
</p>

### Connecting again

If the connection is removed in moschee.io, Home Assistant asks you to connect again under
**Settings → Devices & services**. Confirm it and pair with a new code as above. moschee.io sees the
new pairing as a new connection, so set up its switch rules again.

### Stage

Home Assistant users with **Advanced mode** turned on in their profile can pick **Stage** in the
first step, moschee.io's preview environment. It is only for testing previews of moschee.io; pick
**moschee.io** otherwise.

## In moschee.io

Everything about Home Assistant is under **Smart Mosque → Mixer** in the moschee.io dashboard, and
under **Mixer** in the admin area of the moschee.io app:

- **Live** has a **Switches** card with the shared switches, their state and who changed them last.
  A switch that asks before switching off shows a confirmation first.
- **Automations** has the [switch rules](#switch-rules) for Home Assistant, next to the desk's own
  automations, and their **History**.
- **Setup → Home Assistant** shows whether Home Assistant is connected and sets what it may do with
  the sound desk: **Off**, **View only** (the default) or **Control**. You also rename the shared
  switches there, and disconnect Home Assistant.

## Switch rules

A switch rule turns shared switches on or off at a prayer moment. You set it up in moschee.io and
Home Assistant runs it.

- **When:** the Adhan, the end of the Adhan, the Iqama or the end of the prayer, with an offset in
  minutes. A negative offset is before the moment, so "15 minutes before the Fajr Adhan" is
  the Adhan with `-15`.
- **Only if:** some prayers (Fajr to Isha, and Jumu'ah), some weekdays, or only while a livestream
  is running. No selection means always.
- **Then:** switch a shared entity on or off, or wait between two steps.
- **Watch first:** a new rule only logs what it would have done. Check its **History** for a few
  days, then turn on **Switches in Home Assistant**.

The rules follow the timetable only, because Home Assistant does not hear the Adhan. The rules
that react to the Adhan heard in a live translation, and the ones that mute or move the desk's
channels, run on the Smart-Mosque-Box instead.

## Entities

The integration adds a device named after your mosque, and one device for each sound desk, named
after its box in moschee.io and connected through the mosque's device.

<p align="center">
  <img alt="The mosque's device in Home Assistant: Live translations, Next switch rule, the moschee.io connection and the sound desk as a connected device" src="https://raw.githubusercontent.com/ihsandigital/moscheeio-home-assistant/main/docs/images/mosque-device.png" width="600">
</p>

| Entity | Type | Description |
| --- | --- | --- |
| moschee.io connection | `binary_sensor` | On while Home Assistant is connected to moschee.io and moschee.io can switch. A diagnostic entity. |
| Live translations | `sensor` | How many live translation rooms of the mosque are running right now. |
| Next switch rule | `sensor` | When the next switch rule runs. Its attributes `rule`, `mode` (`on` or `dry_run`), `prayer` and `event` say which rule, and at which moment. |
| *Channel*, such as Imam | `switch` or `binary_sensor` | One per channel set up in moschee.io, named as in moschee.io. On while the channel is not muted. A `switch` with **Control**, a read-only `binary_sensor` with **View only**. |
| *Channel* level | `sensor` | The channel's fader in dB, for channels with a fader. |

The channels have the attributes `target` (the desk's channel, such as `ch/01`), `role`, `protected`,
`desk_name`, `changed_at` and `changed_by`. They are unavailable while the desk is offline. With
**Off**, there are no desk entities at all. When you change the access in moschee.io, Home
Assistant rebuilds the desk's entities by itself.

### Entity IDs

Entity IDs are made from the device's name and the entity's name, in the language Home Assistant
had when the integration was set up. For a mosque named "Example Mosque" and a desk named "Main hall
desk":

| Entity | English | German |
| --- | --- | --- |
| Connection | `binary_sensor.example_mosque_moschee_io_connection` | `binary_sensor.example_mosque_moschee_io_verbindung` |
| Live translations | `sensor.example_mosque_live_translations` | `sensor.example_mosque_live_ubersetzungen` |
| Next switch rule | `sensor.example_mosque_next_switch_rule` | `sensor.example_mosque_nachste_schalter_regel` |
| Imam channel, with **Control** | `switch.main_hall_desk_imam` | `switch.main_hall_desk_imam` |
| Imam level | `sensor.main_hall_desk_imam_level` | `sensor.main_hall_desk_imam_pegel` |

To find yours, open the device under **Settings → Devices & services → moschee.io**, select an
entity, then the ⚙️ icon.

## Automation examples

The switch rules belong in moschee.io, where they show up in the History and follow the safety rules
below. The entities are there for everything else. Replace the entity IDs with
[yours](#entity-ids). To use an example, create an automation, pick **Edit in YAML** in its ⋮ menu
and paste it.

Get a notification when Home Assistant loses moschee.io for five minutes:

```yaml
alias: moschee.io connection lost
triggers:
  - trigger: state
    entity_id: binary_sensor.example_mosque_moschee_io_connection
    to: "off"
    for: "00:05:00"
actions:
  - action: notify.notify
    data:
      message: Home Assistant has lost its connection to moschee.io.
```

Turn on an "on air" sign while a translation is live:

```yaml
alias: On air sign
triggers:
  - trigger: state
    entity_id: sensor.example_mosque_live_translations
actions:
  - if:
      - condition: numeric_state
        entity_id: sensor.example_mosque_live_translations
        above: 0
    then:
      - action: light.turn_on
        target:
          entity_id: light.on_air_sign
    else:
      - action: light.turn_off
        target:
          entity_id: light.on_air_sign
```

Get a notification when the imam's microphone is muted. With **View only**, the channel is
`binary_sensor.main_hall_desk_imam` instead:

```yaml
alias: Imam microphone muted
triggers:
  - trigger: state
    entity_id: switch.main_hall_desk_imam
    from: "on"
    to: "off"
actions:
  - action: notify.notify
    data:
      message: >
        The imam's microphone was muted by
        {{ state_attr('switch.main_hall_desk_imam', 'changed_by') or 'someone' }}.
```

## Safety

- **No power cut during a translation.** A rule never switches anything off while a translation is
  live. The History shows it as "not switched off, a translation is live".
- **The imam's microphone stays on.** The desk refuses to mute a channel marked "Protected in
  prayer" from Home Assistant while the prayer is on.
- **A person always wins.** A rule can leave alone a switch that someone changed in the last few
  minutes, in Home Assistant or in moschee.io.
- **No catching up.** A run more than two minutes late, for example because Home Assistant was off,
  is skipped.
- **View only by default.** Until an admin chooses **Control** in moschee.io, Home Assistant can see
  the desk but not switch it.

## What moschee.io sees

moschee.io only sees the entities you share: their entity ID, their name, whether they are on and
who switched them last, with the name of the Home Assistant user if a person did. It also gets the
versions of Home Assistant and of the integration. Nothing else leaves your Home Assistant.

## Data updates

- Home Assistant checks in with moschee.io every minute. That updates the desk access and
  **Live translations**.
- The switch rules and the prayer moments of the next seven days are fetched at start, every ten
  minutes and right after a rule changes in moschee.io. If moschee.io cannot be reached, the copy on
  disk is used.
- While connected, changes travel both ways within a second: a shared switch's new state to
  moschee.io, and a desk channel's state to Home Assistant.
- Each run is reported to moschee.io right away. Reports that fail are kept on disk, up to 500, and
  sent again every 30 seconds.

## Known limitations

- Beta: details can still change.
- Desk channels only with the Behringer X32 family, through a Smart-Mosque-Box.
- From Home Assistant, desk channels can be muted and unmuted. Levels are read only.
- Switch rules only switch shared entities and wait. They follow the timetable, not the Adhan heard
  in a translation.

## Troubleshooting

### moschee.io is not in the list of integrations

Restart Home Assistant after the download, then reload the page in your browser. With a manual
installation, check that the files are in `custom_components/moscheeio` and not one folder deeper.

### The code expired or was declined

Start the setup again for a new code. Confirm it while signed in as an owner or admin of the mosque.

### "The code was confirmed, but not for a mosque"

Choose your mosque when you confirm the code on moschee.io, then start again.

### A switch is missing in moschee.io

Share it under **Configure** on the integration. Only `switch`, `input_boolean` and `light` entities
can be shared. A switch that Home Assistant cannot reach shows as unavailable.

### The desk's channels are missing or unavailable

Check **Setup → Home Assistant** in moschee.io: with **Off**, Home Assistant gets no channels. Only
the channels set up under **Setup** in moschee.io appear. They are unavailable while the
Smart-Mosque-Box or the desk is offline.

### Switching a channel fails

"moschee.io only lets this Home Assistant view the desk" means the access is **View only**. "The desk
refused" means the channel is protected and the prayer is on.

### A switch rule did not switch anything

The rule's **History** in moschee.io gives the reason: logged only, no livestream, someone had just
changed it, a translation was live, or Home Assistant could not reach the switch. If nothing
appears, Home Assistant was off at the time and the run was skipped.

### Debug logs

On the moschee.io page under **Settings → Devices & services**, pick **Enable debug logging**.
Reproduce the problem and pick **Disable debug logging**: Home Assistant downloads the log. To log from the start, add
this to `configuration.yaml` and restart:

```yaml
logger:
  logs:
    custom_components.moscheeio: debug
```

## Removal

1. In **Settings → Devices & services → moschee.io**, open the ⋮ menu of the entry and pick
   **Delete**.
2. In moschee.io, open **Smart Mosque → Mixer → Setup → Home Assistant** and pick **Disconnect Home
   Assistant**. That also deletes its switch rules and their History.
3. To remove the files, open **moschee.io** in HACS and pick **Remove** in its ⋮ menu. After a manual
   installation, delete `custom_components/moscheeio`.
4. Restart Home Assistant.

## Reporting a bug

Open an [issue](https://github.com/ihsandigital/moscheeio-home-assistant/issues) and attach the
diagnostics: ⋮ menu of the entry, **Download diagnostics**. The token and the relay address are
removed from the file, but it still holds your mosque's name, the shared entities and the switch
rules. Read through it before you attach it to a public issue.

## How it works

Home Assistant pairs like a Smart-Mosque-Box, with the OAuth device authorization flow and the client
id `smart-mosque-ha`. After pairing it:

- calls `GET /api/smart-mosque/me` every minute as a heartbeat;
- fetches its rules and the prayer moments from `GET /api/smart-mosque/config` and keeps them on
  disk;
- reports the shared entities with `PUT /api/smart-mosque/switches`;
- reports runs to `POST /api/smart-mosque/runs`;
- keeps a websocket to the Smart Mosque relay, which brings moschee.io's commands to switch and the
  desks' state, and passes Home Assistant's desk commands to the box.

## Development

```sh
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt ruff
pytest
ruff check . && ruff format --check .
```

CI runs hassfest, the HACS action, ruff and pytest on every pull request.

## License

MIT, see [LICENSE](LICENSE). The integration needs a moschee.io account.
