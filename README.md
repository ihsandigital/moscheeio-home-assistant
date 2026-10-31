# moschee.io for Home Assistant

A Home Assistant integration, installed through HACS, that connects Home Assistant to
[moschee.io](https://moschee.io) and its Smart Mosque relay:

- **Switches next to the Mischpult.** The switches you share, such as the sound desk's power,
  appear in moschee.io under Smart Mosque → Mischpult and in the moschee.io app, and can be
  switched from there.
- **Switch rules at the prayer times.** Rules like "Mischpult 15 Minuten vor Fajr einschalten"
  are set up in moschee.io and run in Home Assistant from the mosque's timetable. They keep running
  without internet.
- **The desk's channels in Home Assistant.** The channels set up in moschee.io appear as entities.
  You can switch them if moschee.io allows it.

## Install

1. In HACS, open the menu → *Custom repositories*, add
   `https://github.com/ihsandigital/moscheeio-home-assistant` as an *Integration*.
2. Download **moschee.io** in HACS and restart Home Assistant.
3. Go to *Settings → Devices & services → Add integration* and pick **moschee.io**.
4. Home Assistant shows a code. Open the link while signed in to moschee.io as an owner or admin of
   your mosque and confirm the code. Home Assistant continues on its own.
5. Open the integration's *Configure* and choose the switches moschee.io may see, and which of them
   it asks about before switching off.

Use the *Stage* environment only if moschee.io asked you to test a preview.

## In moschee.io

Under Smart Mosque → Mischpult:

- **Live** has a *Schalter* card with the shared switches. If a switch is marked "ask before
  switching off", moschee.io asks first, and warns while a translation is live.
- **Automationen** has the rules for Home Assistant. They only switch shared entities and wait, and
  they only run from the timetable, because Home Assistant does not hear the Adhan. New rules start
  in dry run and only log what they would have done.
- **Einrichtung → Home Assistant** sets what this Home Assistant may do with the desks: *Aus*
  (nothing), *Nur ansehen* (default) or *Steuern*. It is also where you rename the shared switches
  and remove the connection.

## Entities

| Entity | |
| --- | --- |
| `binary_sensor` moschee.io connection | connected to the relay |
| `sensor` Live translations | live translation rooms of the mosque |
| `sensor` Next switch rule | when the next rule runs, with its name and prayer |
| `switch` / `binary_sensor` per desk channel | on while not muted; a `switch` with *Steuern*, a `binary_sensor` with *Nur ansehen* |
| `sensor` per channel with a fader | its level in dB |

The desk's channels belong to one device per desk, named as in moschee.io.

## Safety

- A rule never switches anything off while a translation is live (outcome `skipped_live`).
- The desk refuses to mute a protected channel, such as the imam's microphone, from Home Assistant
  during the prayer.
- With *Nur ansehen*, the relay refuses every desk command from Home Assistant.
- "A person always wins": a rule with *skip touched* leaves alone a switch someone changed
  recently.
- Every run, including dry runs, appears in moschee.io's Verlauf. A run more than two minutes late
  (Home Assistant was off) is skipped.

## How it works

Home Assistant pairs like a Smart-Mosque-Box, using the OAuth device flow with client id
`smart-mosque-ha`. After pairing it:

- sends a heartbeat to `GET /api/smart-mosque/me` every 60 seconds;
- fetches its rules and the prayer moments of the next days from `GET /api/smart-mosque/config`
  and keeps them on disk;
- reports its shared entities with `PUT /api/smart-mosque/switches`;
- reports runs to `POST /api/smart-mosque/runs`;
- keeps a websocket to the Smart Mosque relay. The relay brings moschee.io's `switch_set` commands
  and the desks' state.

## Development

```sh
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt ruff
pytest
ruff check . && ruff format --check .
```

## License

MIT, see [LICENSE](LICENSE). The integration needs a moschee.io account.
