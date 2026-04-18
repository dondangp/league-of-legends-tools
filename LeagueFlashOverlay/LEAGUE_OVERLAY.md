# League Overlay

Run the overlay with:

```bash
python3 league_overlay.py
```

What it does:

- Keeps internal cooldown timing with a single global reset.
- Shows five compact enemy rows in a vertical strip.
- Tracks `Flash` only.
- Displays both the remaining cooldown and the time when Flash is back up.
- Plays a spoken macOS alert like `Top completed` when a Flash timer ends.
- Can be dragged from the header area.
- Supports quick hotkeys: `1-5` choose lane, `Q` trigger Flash.
- Lets you adjust transparency with `Cmd/Ctrl` `+` and `-`.

Notes:

- This is a manual overlay, not an automated Riot client integration.
- Cooldowns are base values and do not adjust for runes, summoner spell haste, or special game modes.
