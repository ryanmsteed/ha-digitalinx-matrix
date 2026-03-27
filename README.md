# DigitaLinx HDMI Matrix — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A custom Home Assistant integration for the **Liberty AV DigitaLinx DL-S42-H2** 4×2 HDMI 2.0 Matrix Switcher (and compatible DigitaLinx models) with TCP/IP control.

## Features

- **One `media_player` entity per HDMI output zone** — source selection routes HDMI inputs
- **Named inputs** — configure friendly names (e.g. "Apple TV", "Shield", "PS5") during setup
- **CEC display power** — turn on/off connected displays via CEC passthrough
- **Audio mute** — mute/unmute de-embedded audio per output
- **Polling state** — automatically polls the matrix for current routing and mute state
- **Config flow** — full UI-based setup, no YAML required
- **Options flow** — rename inputs and adjust poll interval without reconfiguring

## Hardware

| Feature | Spec |
|---|---|
| Inputs | 4× HDMI 2.0b |
| Outputs | 2× HDMI 2.0b |
| Resolution | Up to 4K@60Hz 4:4:4 HDR |
| Audio | PCM 2.0/5.1/7.1, Dolby TrueHD, Atmos, DTS-HD MA, DTS:X |
| Audio De-embed | Analog 3.5mm (Out 1), Toslink (Out 1 & 2), ARC (Out 2) |
| Control | TCP/IP (port 23), RS-232, IR, Front Panel, Web GUI |

## Installation

### HACS (Recommended)

1. Open HACS → Integrations → ⋮ menu → **Custom Repositories**
2. Add `https://github.com/ryanmsteed/ha-digitalinx-matrix` as **Integration**
3. Search for "DigitaLinx" and install
4. Restart Home Assistant

### Manual

1. Copy `custom_components/digitalinx_matrix/` to your HA `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"DigitaLinx HDMI Matrix"**
3. Enter the IP address of your DL-S42-H2 (default port 23)
4. Name your HDMI inputs (e.g. "Apple TV", "Shield Pro", "PS5", "PC")
5. Done — you'll get two `media_player` entities (one per output zone)

## Usage

### Source Selection (Input Routing)

Use the source dropdown on each output's media player card to route any HDMI input:

```yaml
service: media_player.select_source
target:
  entity_id: media_player.digitalinx_matrix_output_1
data:
  source: "Apple TV"
```

### CEC Display Power

```yaml
service: media_player.turn_on
target:
  entity_id: media_player.digitalinx_matrix_output_1
```

### Audio Mute

```yaml
service: media_player.volume_mute
target:
  entity_id: media_player.digitalinx_matrix_output_1
data:
  is_volume_muted: true
```

## Protocol Notes

The DL-S42-H2 uses a simple ASCII protocol over TCP port 23 (telnet):

| Command | Description |
|---|---|
| `SET SW in{1-4} out{1-2}` | Route input to output |
| `GET SW out{1-2}` | Query current route |
| `SET MUTE out{1-2} {on\|off}` | Mute/unmute output |
| `GET MUTE out{1-2}` | Query mute state |
| `SET CEC out{1-2} {on\|off}` | CEC display power |
| `GET VER` | Query firmware version |

All commands terminated with `\r\n`. Default IP: `192.168.1.254`.

## Network Setup

Assign a static IP on your main LAN (e.g. `10.10.10.x`). The device ships with default `192.168.1.254` — you'll need to change this via the web GUI first by connecting directly or being on the same subnet.

## License

MIT
