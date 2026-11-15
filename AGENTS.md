# AGENTS.md

Guidance for coding agents (Claude Code, Codex, Cursor) in this repository. `CLAUDE.md` imports
this file, so edit instructions here. `README.md` is the user guide, also shown in HACS.

The moschee.io custom integration for Home Assistant (HACS, beta): it shares Home Assistant
switches with moschee.io, runs moschee.io's switch rules at prayer times, and shows and mutes the
channels of a Behringer X32 desk through a Smart-Mosque-Box. It pairs like a box, with the device
authorization flow and client id `smart-mosque-ha`, and talks to `/api/smart-mosque/*` in
`ihsandigital/moschee.io` and to the relay in `ihsandigital/moscheeio-smart-mosque`. Python 3.13,
code in `custom_components/moscheeio/`.

## Boundaries

- **Rules switch real devices in a mosque.** Keep the safety rules from `README.md` intact: nothing
  is switched off while a translation is live, a protected channel is never muted from Home
  Assistant during the prayer, a person always wins, runs more than two minutes late are skipped,
  and access is view only until an admin chooses Control. A change near them needs tests in
  `tests/test_runner.py` or `tests/test_automations.py`.
- **Only Youcef releases.** HACS installs from GitHub Releases on `v*` tags. Don't push tags or
  publish releases; bump the version and hand him the command (see Releases).
- The protocol is shared with moschee.io, the box and the relay; it is documented in
  `docs/protocol.md` of `ihsandigital/moscheeio-smart-mosque`. A change there needs the matching
  moschee.io change, and the PR says which ships first.
- Only the shared entities leave Home Assistant (README "What moschee.io sees"). Don't send other
  states, attributes or user data, and keep tokens out of logs and diagnostics
  (`diagnostics.py` redacts them).

## Commands

```sh
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt ruff
pytest
ruff check . && ruff format --check .
```

## CI and releases

- `validate.yml` runs hassfest, the HACS action, ruff and pytest on PRs and pushes to `main`. The
  HACS check ignores `brands` until the icon is in `home-assistant/brands`.
- A release: bump `version` in `custom_components/moscheeio/manifest.json` and `VERSION` in
  `const.py` together (moschee.io sees it in the client header), merge, then Youcef tags
  `vX.Y.Z` on `main` and publishes the GitHub Release, for example
  `gh release create v0.1.3 --repo ihsandigital/moscheeio-home-assistant --target main --generate-notes`.

## Branches and PRs

- PRs go to `main`; there is no `stage` branch. Merges need Youcef's OK.
- moschee.io's stage environment is picked in the config flow (Advanced mode only), not by branch.

## Conventions

- Strings live in `translations/en.json` and `translations/de.json`; add every new key to both.
- Tests use `pytest-homeassistant-custom-component` with `asyncio_mode = "auto"`; the fakes for
  moschee.io and the relay are in `tests/conftest.py`.
- Screenshots in `docs/images/` are shown in the README and HACS; retake them when a step changes.
