# Recommended Hardware Build

This guide covers the hardware setup that works best with Clanker + Home Assistant. None of this is strictly required — Clanker works with any HA setup — but this is the reference build.

## Voice Satellites

Voice is input-agnostic: any HA Assist-compatible surface works. Recommended options:

### ESP32-S3 Voice Satellites (budget, DIY)

The best bang-for-buck voice input for whole-home coverage.

- **Board**: ESP32-S3-DevKitC-1 (N16R8 variant — 16MB flash, 8MB PSRAM)
- **Microphone**: INMP441 I2S MEMS mic — good sensitivity, low noise, ~$2
- **Speaker**: MAX98357A I2S amplifier + a small 3W 4Ω speaker
- **Case**: 3D-printed or a small project box
- **Firmware**: [ESPHome voice assistant](https://esphome.io/components/voice_assistant.html) or [microWakeWord](https://github.com/kahrendt/microWakeWord)
- **Cost**: ~$10–15 per room

**Tradeoffs**: Requires soldering and ESPHome config. Wake word runs on-device (microWakeWord) or in HA. Audio quality is adequate but not premium.

### Home Assistant Voice Preview Edition (plug-and-play)

- **Device**: HA Voice PE — purpose-built for Assist
- **Pros**: Zero config, good mic array, built-in speaker, official support
- **Cons**: More expensive (~$59), limited availability
- **Best for**: Non-DIY users who want it to just work

### Existing Smart Speakers

If you already have speakers with HA integration (Sonos, Google Home via HA Cloud, etc.), they can serve as TTS output targets. Voice input still needs a dedicated mic source.

## Camera System (for Frigate)

Clanker's vision pipeline relies on [Frigate](https://frigate.video/) for object detection.

### Cameras

- **Recommended**: Any RTSP-capable camera with good night vision
  - **Budget**: Reolink RLC-510A or RLC-520A (~$45) — PoE, 5MP, good Frigate support
  - **Mid-range**: Reolink RLC-810A (~$55) — 4K, excellent detection performance
  - **Doorbell**: Reolink Video Doorbell PoE (~$80) or Amcrest AD410 (~$80)
- **Avoid**: Cloud-only cameras (Ring, Nest) — they don't expose RTSP easily

### Frigate Server

Frigate needs a dedicated detector for real-time object detection:

- **Google Coral TPU** (USB or M.2): The gold standard for Frigate. ~$25–60 depending on form factor. USB version works with any machine; M.2 for NUCs/mini-PCs.
- **CPU fallback**: Works but burns CPU and adds latency. Fine for 1–2 cameras.
- **GPU**: NVIDIA GPUs work via TensorRT if you already have one.

Frigate itself runs as a Docker container alongside HA.

## Face Recognition

For personalized doorbell announcements ("Your neighbor Jim is at the door"):

- **[Double Take](https://github.com/jakowenko/double-take)**: Sits between Frigate and HA. Routes face crops to recognition backends.
- **[CompreFace](https://github.com/exadel-inc/CompreFace)**: Open-source face recognition API. Self-hosted, good accuracy. Used as a backend for Double Take.
- **Training**: Upload 3–5 clear photos per person via the CompreFace UI. More photos = better accuracy.

## Audio Output (Speakers)

Each main room needs a speaker that HA can target for TTS:

- **Google Nest Mini / Nest Hub**: Cheap (~$25–50), native HA integration via Cast
- **Sonos**: Premium quality, native HA integration
- **ESP32 I2S speakers**: Same as voice satellite with speaker — doubles as both input and output
- **Any AirPlay/Cast/DLNA speaker**: Works via HA media_player integrations

## Compute

Clanker itself is lightweight (Python async service). The heaviest local compute is:

- **Ollama** (if using local LLMs): Needs a decent GPU (RTX 3060+ for 7B models) or beefy CPU (acceptable for small models)
- **Frigate** with Coral: Minimal CPU, the Coral handles inference
- **HA**: Runs on anything from a Pi 4 to a full server

**Recommended setup**: A mini-PC (Intel NUC, Beelink) running:
- Home Assistant OS or Container
- Frigate (Docker)
- Clanker (Docker)
- Ollama (Docker, if using local models)
- Coral USB plugged in

Budget: ~$200–400 for the NUC + Coral + a couple cameras. Voice satellites add ~$15/room.

## Network

- **PoE switch** recommended for cameras (clean single-cable runs)
- Wired Ethernet for the compute box (reliability matters for home automation)
- WiFi is fine for voice satellites and smart speakers
