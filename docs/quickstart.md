# Quick-Start Guide

Get Clanker running on your local machine with minimal hardware.

## What You Need

| Requirement | Notes |
|---|---|
| Computer (Linux, Mac, or Windows with WSL2) | Runs HA, Ollama, Frigate, and Clanker |
| Webcam (USB or built-in) | Acts as a Frigate camera for testing |
| Microphone (webcam mic works) | For voice input / wake word detection |
| Anthropic API key | Cloud brain — [console.anthropic.com](https://console.anthropic.com) |

**Total cost: $0 in hardware** (you already have all of this). Anthropic API is pay-per-use — testing costs pennies.

---

## Step 1: Install Home Assistant (Container)

```bash
mkdir -p ~/homeassistant
docker run -d \
  --name homeassistant \
  --restart unless-stopped \
  -v ~/homeassistant:/config \
  -v /run/dbus:/run/dbus:ro \
  --network host \
  ghcr.io/home-assistant/home-assistant:stable
```

Open `http://localhost:8123`, create your account, and complete onboarding.

**Get a Long-Lived Access Token:**
1. Click your profile (bottom-left) → Security → Long-Lived Access Tokens → Create Token
2. Save it — you'll need it for `CLANKER_HA__TOKEN`.

## Step 2: Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2        # general-purpose (~2GB)
ollama pull llava           # vision/multimodal (~4.5GB, optional)
ollama pull nomic-embed-text  # embeddings for semantic memory (optional)
```

Verify: `ollama run llama3.2 "Say hello"` — should respond.

## Step 3: Set Up Frigate (Optional — for Camera Detection)

Skip this step if you just want LLM + HA without camera stuff.

```bash
mkdir -p ~/frigate/config
```

Create `~/frigate/config/config.yml`:

```yaml
mqtt:
  enabled: false

cameras:
  webcam:
    enabled: true
    ffmpeg:
      inputs:
        - path: /dev/video0
          roles: ["detect"]
    detect:
      width: 1280
      height: 720
      fps: 5
```

```bash
docker run -d \
  --name frigate \
  --restart unless-stopped \
  --device /dev/video0:/dev/video0 \
  -v ~/frigate/config:/config \
  -v /etc/localtime:/etc/localtime:ro \
  -p 5000:5000 \
  -p 8971:8971 \
  ghcr.io/blakeblackshear/frigate:stable
```

Open `http://localhost:5000` to verify your webcam feed.

> **Note:** For CPU-only detection, Frigate works but is slow. A Google Coral USB
> Accelerator (~$35) makes it real-time. See `docs/recommended-build.md`.

### Connect Frigate to Home Assistant

1. In HA: Settings → Integrations → Add Integration → search "Frigate"
2. Enter `http://localhost:5000` as the URL
3. Frigate entities (cameras, sensors, events) will appear in HA

## Step 4: Configure Clanker

```bash
cd /path/to/clanker
cp config/clanker.yaml.example config/clanker.yaml
cp .env.example .env
```

Edit `.env`:
```bash
CLANKER_HA__TOKEN=your_long_lived_access_token_here
CLANKER_ANTHROPIC__API_KEY=sk-ant-your-key-here
```

Edit `config/clanker.yaml` — the defaults work for a local setup. Key changes:

```yaml
ha:
  url: "http://localhost:8123"

frigate:
  enabled: true  # set to false if you skipped Step 3
  url: "http://localhost:5000"

ollama:
  base_url: "http://localhost:11434"
  model: "llama3.2"
```

## Step 5: Run Clanker

```bash
# Install dependencies
pip install -e .

# Or with uv (recommended)
uv pip install -e .

# Run
python -m clanker.main
```

You should see:
```
clanker.starting    version=0.1.1
ha.connecting       url=ws://localhost:8123/api/websocket
ha.connected        ha_version=2025.x.x
clanker.subscribed  event_type=state_changed
clanker.ready
```

## Step 6: Run Tests

```bash
pip install -e ".[dev]"   # install dev dependencies
pytest tests/ -v          # should see 75 tests pass
```

---

## Voice Control & Wake Word ("Hey Clanker")

### How It Works

Voice control uses **Home Assistant's voice pipeline**:

```
Mic → Wake Word Engine → Speech-to-Text → Intent/LLM → Text-to-Speech → Speaker
          ↑                                    ↑
    openWakeWord                          Clanker brain
   "Hey Clanker"                      (conversation agent)
```

Clanker plugs in as the **conversation agent** — it doesn't do wake word
detection itself. HA handles the audio pipeline via the **Wyoming protocol**.

### Can I Use My Webcam Mic?

**Yes, for testing.** Any ALSA-compatible mic works. Your webcam mic is fine
for a desk setup. For across-the-room detection you'd want a dedicated mic
array (the ESP32 voice satellite kits are ~$15).

### Training a Custom "Hey Clanker" Wake Word

Home Assistant uses **openWakeWord** for wake word detection. Creating a
custom wake word does NOT require you to record yourself saying it hundreds
of times. Instead, it generates synthetic speech samples automatically.

**The process:**

1. **Clone the openWakeWord repo:**
   ```bash
   git clone https://github.com/dscripka/openWakeWord.git
   cd openWakeWord
   ```

2. **Generate synthetic training data:**
   The training pipeline uses multiple TTS engines (Google, Azure, etc.) to
   generate thousands of diverse audio clips of "Hey Clanker" with different
   accents, speeds, and pitches. This happens automatically — you just provide
   the phrase.

3. **Train the model:**
   Use the provided Google Colab notebook or local Python scripts.
   Training takes ~30 minutes on CPU, faster with GPU. See
   `openWakeWord/docs/custom_models.md` for the full walkthrough.

4. **Export:** You get a `.tflite` file (~50KB).

5. **Deploy to Home Assistant:**
   - Copy the `.tflite` model to a HA-accessible directory (e.g., `/share/openwakeword/`)
   - In the openWakeWord add-on config, set `custom_model_dir` to that path
   - Restart the add-on
   - Go to Settings → Voice Assistants → your pipeline → set wake word to "Hey Clanker"

### microWakeWord (for ESP32 Voice Satellites)

If you later build ESP32-S3 voice satellites (see `docs/recommended-build.md`),
those use **microWakeWord** — a separate, ultra-lightweight engine that runs
on the ESP32 itself. It also uses synthetic training via a Google Colab
notebook, same idea but optimized for microcontroller inference.

### Do I Need to "Train My Voice"?

**No.** openWakeWord is speaker-independent — it detects the *phrase*, not
*your* voice. The synthetic training data covers diverse speakers, so it works
for anyone in your household out of the box.

To **reduce false triggers**, the model is trained with negative examples
(common phrases that sound similar but aren't the wake word). The default
training pipeline handles this automatically. If you get false triggers in
practice, you can fine-tune by adding your specific background audio as
negative examples and retraining.

---

## What's Next

Once you have the basic setup running:

1. **Add entities in HA** — lights, switches, sensors (even virtual ones for testing)
2. **Test the brain** — Clanker's MCP server exposes tools for HA control
3. **Try Frigate detection** — walk in front of your webcam, check events at `localhost:5000`
4. **Set up voice** — install the Wyoming + openWakeWord add-ons in HA
5. **Build a voice satellite** — ESP32-S3 + mic + speaker (~$15, see `docs/recommended-build.md`)
