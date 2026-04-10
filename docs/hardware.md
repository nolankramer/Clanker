# Hardware Guide

> **Status: untested.** These are reference configurations based on community
> experience with Home Assistant and Ollama. We haven't verified every
> combination yet. If you test one, please open an issue with your results.

## Recommended Configurations

### Budget: Voice-Only (~$85)

Best for: voice control + cloud LLM. No local AI or cameras.

- Raspberry Pi 5 (4GB) + official 27W USB-C power supply
- microSD card (32GB+, A2 rated)
- Ethernet cable (WiFi works but wired is more reliable)

**Voice satellite (one per room, optional):**
- ESP32-S3-DevKitC-1 (N16R8)
- INMP441 I2S MEMS microphone
- MAX98357A I2S amplifier + small speaker (3W, 4-8 ohm)

> **Limitation:** The Pi 5 4GB can't run local LLMs well. You'll need an
> Anthropic or OpenAI API key for the brain. TTS (Piper) and STT (Whisper)
> still run locally.

---

### Sweet Spot: Fully Local (~$130)

Best for: everything running locally. No cloud needed. No camera detection.

- Intel N100 mini PC with 16GB RAM, 256GB SSD (Beelink, MinisForum, GMKtec — any N100 with 16GB works)
- Ethernet cable

This should run: HA + Ollama (llama3.2 7B) + Piper TTS + Whisper STT + Clanker. Fully offline capable.

---

### Full Setup: Local AI + Cameras (~$175)

Best for: everything local PLUS camera-based detection (Frigate).

- Intel N100 mini PC, 16GB RAM (same as above)
- Google Coral USB Accelerator — real-time object detection for Frigate
- USB webcam or existing IP cameras (Reolink, etc.)

The Coral makes Frigate run at full speed with near-zero CPU usage. Without it, Frigate works but is slower on CPU.

---

### Premium: Full House (~$250+)

For the serious setup — dedicated server with more headroom.

- Intel N305 mini PC with 16-32GB RAM (more headroom for larger LLM models)
- Google Coral USB Accelerator
- ESP32-S3 voice satellites (one per room)

With 32GB RAM you can run larger Ollama models (13B+) for better reasoning.

---

## GPU-Accelerated LLM Inference

The configurations above use CPU-only inference, which is fine for small
models but slow (~5-15 tok/s on an N100). A GPU dramatically improves
response time for the LLM brain.

> **Note:** The intent fast-path handles most simple commands (~50ms)
> without the LLM. GPU acceleration mainly benefits complex/conversational
> requests that go through the brain.

### Budget GPU: Used RTX 3060 12GB (~$200 used)

~50-65 tokens/second on Llama 3.1 8B. Best bang for buck.
Put it in any desktop PC or workstation with a PCIe x16 slot + 500W PSU.

### Mid-Range: RTX 4060 Ti 16GB (~$400 new)

~80-100 tokens/second. Sweet spot for price/performance.
16GB VRAM comfortably runs 7-8B models with headroom.

### High-End: Used RTX 3090 24GB (~$800 used)

~90-110 tokens/second + 24GB VRAM. Runs 13B models fully offloaded
and even 70B models at heavy quantization. Best value for serious use.

### Silent/Low Power: Mac Mini M4 Pro (~$1,400 new)

~40-55 tokens/second. Silent (fanless under load), tiny, 30W power.
Unified memory means no separate GPU needed. Good if you value
aesthetics and silence over raw speed.

### Ultra-Budget: Used Tesla P40 24GB (~$150 used)

~35-45 tokens/second. No video output (headless server only).
Needs a blower cooler mod and 8-pin EPS power. But 24GB VRAM
for $150 is unbeatable for running larger models on a budget.

### What about NPUs?

Intel Core Ultra and AMD Ryzen AI chips have built-in NPUs, but these
**don't work with Ollama** and are too slow for LLM inference (~5-15
tok/s). They're designed for lightweight tasks, not running a 7B model.
Stick with a GPU if you want fast local inference.

### Quick Reference

| Hardware | ~Tok/s (8B model) | ~Price | VRAM | Power |
|----------|-------------------|--------|------|-------|
| Intel N100 (CPU only) | 5-15 | $120 | — | 15W |
| Tesla P40 (used) | 35-45 | $150 | 24GB | 250W |
| RTX 3060 12GB (used) | 50-65 | $200 | 12GB | 170W |
| Mac Mini M4 Pro | 40-55 | $1,400 | 24GB shared | 30W |
| RTX 4060 Ti 16GB | 80-100 | $400 | 16GB | 165W |
| RTX 3090 24GB (used) | 90-110 | $800 | 24GB | 350W |

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
