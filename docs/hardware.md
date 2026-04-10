# Hardware Guide

Buy the hardware, flash the image, done. No Linux experience needed.

## Recommended Configurations

### Budget: Voice-Only ($85)

Best for: voice control + cloud LLM. No local AI or cameras.

| Item | ~Price | Notes |
|------|--------|-------|
| Raspberry Pi 5 (4GB) | $60 | [raspberrypi.com](https://www.raspberrypi.com/products/raspberry-pi-5/) |
| Official Pi 5 power supply (27W USB-C) | $12 | Must be 5V/5A — don't use a phone charger |
| microSD card (32GB+) | $8 | Samsung EVO or SanDisk Extreme |
| Ethernet cable | $5 | WiFi works but wired is more reliable |

**Voice satellite (one per room, optional):**

| Item | ~Price |
|------|--------|
| ESP32-S3-DevKitC-1 (N16R8) | $8 |
| INMP441 MEMS microphone | $3 |
| MAX98357A I2S amplifier | $3 |
| Small speaker (3W, 4-8 ohm) | $3 |

> **Limitation:** The Pi 5 4GB can't run local LLMs well. You'll need an
> Anthropic or OpenAI API key for the brain. TTS (Piper) and STT (Whisper)
> still run locally.

---

### Sweet Spot: Fully Local ($130)

Best for: everything running locally. No cloud needed. No camera detection.

| Item | ~Price | Notes |
|------|--------|-------|
| Intel N100 mini PC, 16GB RAM, 256GB SSD | $120 | Beelink EQ12, MinisForum UN100D, or GMKtec N100 — any N100 with 16GB works |
| Ethernet cable | $5 | |

Search Amazon for: **"Intel N100 mini PC 16GB"** — pick any with good reviews under $130.

This runs: HA + Ollama (llama3.2 7B) + Piper TTS + Whisper STT + Clanker. Fully offline capable.

---

### Full Setup: Local AI + Cameras ($175)

Best for: everything local PLUS camera-based detection (Frigate).

| Item | ~Price | Notes |
|------|--------|-------|
| Intel N100 mini PC, 16GB RAM | $120 | Same as above |
| Google Coral USB Accelerator | $35 | Real-time object detection for Frigate |
| USB webcam (any) | $20 | Or use existing IP cameras (Reolink, etc.) |

The Coral makes Frigate run at full speed with near-zero CPU usage. Without it, Frigate works but is slow on CPU.

> **Coral availability:** The Coral USB Accelerator has periodic stock issues.
> Check [coral.ai](https://coral.ai/products/accelerator) and Amazon.
> Frigate works without it (CPU detection) — just slower.

---

### Premium: Full House ($250+)

For the serious setup — dedicated server with GPU potential.

| Item | ~Price | Notes |
|------|--------|-------|
| Intel N305 mini PC, 16-32GB RAM | $200+ | MinisForum UM773, Beelink SER5 — more headroom for larger models |
| Google Coral USB Accelerator | $35 | |
| ESP32-S3 voice satellites (x3) | $50 | One per room |

With 32GB RAM you can run larger Ollama models (13B+) for better reasoning.

---

## How to Set Up

### Option A: Flash the Clanker OS image (easiest)

1. Download the image for your hardware:
   - [x86 (mini PCs)](https://github.com/nolankramer/clanker/releases) — `.img.gz`
   - [arm64 (Raspberry Pi 5)](https://github.com/nolankramer/clanker/releases) — `.img.gz`
2. Flash to SD card or USB drive with [Balena Etcher](https://etcher.balena.io/)
3. Insert into your device and power on
4. Open `http://clanker.local` from any browser on your network
5. Walk through the setup wizard

### Option B: Install on existing hardware

If you already have a machine running Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/nolankramer/clanker/main/install.sh | bash
```

### Option C: HA Add-on (if you already have Home Assistant)

Settings → Add-ons → Add-on Store → ⋮ → Repositories →
Add `https://github.com/nolankramer/clanker` → Install Clanker

---

## Voice Satellite Build

Each room gets a tiny microphone + speaker that connects to Clanker via
Home Assistant's voice pipeline. Total cost: ~$15 per room.

### Parts

- **ESP32-S3-DevKitC-1 (N16R8)** — the brains ($8)
- **INMP441 I2S MEMS microphone** — far-field pickup ($3)
- **MAX98357A I2S amplifier** — drives the speaker ($3)
- **3W speaker, 4-8 ohm** — any small speaker works ($3)

### Wiring

```
ESP32-S3           INMP441 Mic
─────────          ──────────
GPIO 5   ────────  SCK
GPIO 6   ────────  WS
GPIO 4   ────────  SD
3.3V     ────────  VDD
GND      ────────  GND
                   L/R → GND (left channel)

ESP32-S3           MAX98357A Amp
─────────          ─────────────
GPIO 7   ────────  BCLK
GPIO 8   ────────  LRC
GPIO 9   ────────  DIN
VIN (5V) ────────  VIN
GND      ────────  GND
                   Speaker + / - → your speaker
```

### Firmware

Flash via browser at [ESPHome Web](https://web.esphome.io/):

1. Connect ESP32-S3 via USB
2. Flash the ESPHome voice satellite firmware
3. Configure WiFi and HA connection
4. The satellite appears in HA automatically

See `docs/recommended-build.md` for more detail on the voice satellite build.
