---
marp: true
theme: default
paginate: true
backgroundColor: '#0f0f0f'
color: '#f0f0f0'
style: |
  section {
    font-family: 'Inter', sans-serif;
    padding: 48px 64px;
  }
  h1 { color: #a78bfa; font-size: 2.2em; margin-bottom: 0.2em; }
  h2 { color: #7c3aed; font-size: 1.5em; border-bottom: 2px solid #7c3aed; padding-bottom: 8px; }
  h3 { color: #c4b5fd; }
  code { background: #1e1e2e; padding: 2px 8px; border-radius: 4px; color: #a6e3a1; }
  table { width: 100%; border-collapse: collapse; }
  th { background: #7c3aed; color: white; padding: 10px; }
  td { padding: 10px; border-bottom: 1px solid #2a2a3a; }
  .pill { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.8em; margin: 2px; }
---

# Rime
## AI Voice Agent for Restaurants

**In-house replacement for Bland AI**
Twilio · Deepgram · Gemini Flash · Rime TTS

---

## The Problem

**Bland AI & Vapi are black boxes.**

- No control over conversation pathways
- Expensive per-minute pricing at scale
- Can't fine-tune on your own data
- Vendor lock-in — they own the pipeline

**The opportunity:** Build the same stack in-house, own every layer, train on your data.

---

## What the Agent Does

- **Greets** the caller warmly by name
- **Takes food & drink orders** from the menu
- **Answers questions** about the restaurant
  - Reservations, children's policy, parking, hours
- **Confirms the order** with a line-item summary and total
- **Outputs a structured order** for the kitchen or POS system

---

## Full Pipeline Architecture

```
┌─────────────┐     TwiML      ┌─────────────────────────────────────────────┐
│   Customer  │ ─────────────► │              Rime Server (FastAPI)           │
│  (Phone)    │                │                                              │
│             │◄────────────── │  ┌──────────────────────────────────────┐   │
│  🎙  speaks │  mulaw audio   │  │          WebSocket Handler            │   │
│  🔊  hears  │  base64        │  │                                       │   │
└─────────────┘                │  │  1. Receive Twilio audio stream       │   │
       ▲                       │  │         ↓                             │   │
       │                       │  │  2. Deepgram STT (streaming)          │   │
  Twilio PSTN                  │  │         ↓  (final transcript)         │   │
  Cloud                        │  │  3. Gemini Flash (LLM brain)          │   │
                               │  │         ↓  (response text)            │   │
                               │  │  4. Rime TTS → mulaw 8kHz             │   │
                               │  │         ↓                             │   │
                               │  │  5. Stream audio back to Twilio       │   │
                               │  └──────────────────────────────────────┘   │
                               └─────────────────────────────────────────────┘
```

---

## Component 1: Telephony — Twilio

**What it does:** Handles the phone number, PSTN connection, and audio streaming.

**How it works:**
1. Caller dials a Twilio number
2. Twilio fetches our TwiML endpoint → we return a `<Stream>` instruction
3. Twilio opens a WebSocket and streams **mulaw 8kHz audio** in real time
4. We send audio back over the same WebSocket → Twilio plays it to the caller

**Why Twilio:** Industry standard, reliable, handles all carrier complexity.
PSTN → WebSocket bridge in 3 lines of TwiML.

---

## Component 2: Speech-to-Text — Deepgram

**What it does:** Converts the caller's voice to text in real time.

**Key settings:**
```
encoding=mulaw  sample_rate=8000  endpointing=300ms
```

- `endpointing=300` — marks a transcript as **final** after 300ms silence
- `punctuate=true` — adds punctuation for cleaner LLM input
- `is_final=true` — the signal we act on (ignores interim results)

**Why Deepgram over Whisper:**
- Streaming (Whisper needs full audio first) → much lower latency
- 300ms TTFT vs 1–3s for local Whisper
- Deepgram custom vocabulary → train on your menu item names

---

## Component 3: LLM Brain — Gemini Flash

**What it does:** Reads the transcript, generates a natural spoken response, tracks the order.

**System prompt layers:**
- Full menu with prices
- Restaurant FAQ (children, reservations, hours, etc.)
- Conversation rules ("keep responses to 1–3 sentences")
- Order extraction signal: `ORDER_COMPLETE: [JSON]`

**Why Gemini Flash over GPT-4o:**
- ~10x cheaper per token
- ~50% faster response time
- Comparable quality for structured dialogue tasks

**Latency target:** < 800ms LLM response time

---

## Component 4: Text-to-Speech — Rime.ai

**What it does:** Converts the LLM response text to spoken audio.

**Audio pipeline:**
```
Rime HTTP API (WAV 22050Hz)
  → strip WAV header → 16-bit PCM
  → resample to 8000Hz  (audioop)
  → encode to mulaw     (audioop)
  → base64 → Twilio WebSocket
```

**Why Rime:**
- Trained on real customer service interactions
- Deterministic pronunciation (menu item names, prices)
- Voice cloning → custom branded voice per restaurant
- 225ms time-to-first-audio on dedicated endpoints

---

## Conversational Pathways

**How the agent navigates a conversation:**

```
     GREETING
        │
        ▼
   TAKING_ORDER ◄─────────────────┐
        │                         │
        ├─── FAQ question? ───► ANSWER_FAQ ─┘
        │
        ▼
  CONFIRMING_ORDER
        │
        ▼
    ORDER_COMPLETE → structured JSON output
```

**MVP (what we built):** LLM-guided — system prompt instructs the model to follow this flow.

**Production:** State machine (LangGraph) + LLM per state. Guarantees correct transitions, prevents the agent from going off-script.

---

## Training Strategy

### Layer 1 — ASR (Deepgram)
- Add menu items as **custom vocabulary** (keyword boosting)
- Collect call recordings → fine-tune a restaurant-specific model
- Train on background noise from the actual venue

### Layer 2 — LLM (Gemini)
- Generate 1,000+ synthetic ordering conversations
- Collect real anonymised transcripts from Twilio recordings
- Fine-tune via Google AI Studio → smaller, faster, cheaper model

### Layer 3 — TTS Voice (Rime)
- Record 1 hour of audio from chosen voice talent
- Submit to Rime for voice cloning
- Brand-consistent voice across all restaurant locations

---

## ASP — Audio Signal Processing

**The reliability layer for real restaurant environments.**

```
Twilio raw audio
      ↓
  [ASP Layer]  ← sits here, before Deepgram
      ↓
  Deepgram STT
```

| Component | Problem it solves | Tool |
|---|---|---|
| **VAD** | Only send speech frames to Deepgram | Silero VAD |
| **Noise Suppression** | Kitchen noise, music, other diners | RNNoise |
| **AEC** | TTS bleed-back into microphone | WebRTC AEC |
| **Barge-in** | Customer interrupts agent → stop TTS | VAD + AEC |

**Phase 2 priority.** Without ASP, accuracy drops in a live restaurant by ~15–25%.

---

## FlashLabs Chroma — The Future

**What it is:** An end-to-end audio model — audio in, audio out. No separate STT/LLM/TTS.

```
Current:  Twilio → Deepgram STT → Gemini Flash → Rime TTS → Twilio
Future:   Twilio → Chroma (4B params, audio→audio) → Twilio
```

**The upside:**
- Removes 2 API hops → latency drops dramatically
- Single model to fine-tune and version

**The constraint:**
- Requires a CUDA GPU server (not a cloud API)
- 4B parameters → infrastructure cost and expertise
- Less control over individual pipeline stages

**Our position:** Monitor Chroma's development. Adopt when dedicated GPU inference is cost-justified at scale.

---

## Bland AI vs In-House Comparison

| | Bland AI | Rime (ours) |
|---|---|---|
| **Cost** | ~$0.09/min | ~$0.01–0.02/min |
| **Customisation** | Pathway editor (no code) | Full code control |
| **Voice** | Pre-built library | Clone any voice |
| **STT model** | Locked in | Swap or fine-tune |
| **LLM model** | Locked in | Any model, any prompt |
| **Training on own data** | No | Yes |
| **ASP / noise handling** | Basic | Full control |
| **Vendor dependency** | High | None |

---

## Latency Budget

**Target: < 2 seconds end-to-end**

| Stage | Target |
|---|---|
| Twilio audio → our server | ~50ms |
| Deepgram STT (streaming) | ~300ms (endpointing) |
| Gemini Flash (LLM) | ~600ms |
| Rime TTS (first chunk) | ~250ms |
| Twilio playback start | ~50ms |
| **Total** | **~1.25s** |

Compared to human response time (~500ms), this is acceptable for phone interactions.
With ASP barge-in: add ~50ms. Still within budget.

---

## Restaurant Use Cases

1. **Phone ordering** — take full dine-in or future takeaway orders
2. **Reservation enquiries** — check availability, answer booking questions
3. **FAQ deflection** — hours, parking, dietary, children's policy (no human needed)
4. **Overflow handling** — busy periods, evenings, weekends
5. **Multi-location** — one codebase, different system prompts per restaurant
6. **Post-call order routing** — structured JSON order → POS / kitchen display system

---

## MVP Architecture — What We Built Today

```
src/
├── api.py                  ← FastAPI server
├── core/
│   ├── settings.py         ← env config (Twilio, Deepgram, Gemini, Rime)
│   ├── restaurant.py       ← menu, FAQ, system prompt, Order dataclass
│   └── agent.py            ← Gemini Flash conversation manager
├── services/
│   └── tts.py              ← Rime TTS → mulaw 8kHz (Twilio-ready)
└── routers/
    └── twillio.py          ← WebSocket handler (full pipeline wired)
```

**To run:** `uv sync && uv run python src/api.py`
**To test:** expose via ngrok, point Twilio webhook to `/twillio/incoming-call`

---

## Next Steps

1. **This week** — test with real Twilio number + ngrok
2. **Week 2** — add ASP (VAD + noise suppression)
3. **Week 3** — LangGraph state machine (replace LLM-only pathway)
4. **Week 4** — Deepgram custom vocabulary for menu items
5. **Month 2** — collect real call data, begin LLM fine-tuning
6. **Month 3** — Rime voice cloning, custom restaurant voice
7. **Future** — evaluate FlashLabs Chroma for end-to-end audio model

---

# Thank You

**Rime — AI Voice Agent**

Stack: Twilio · Deepgram · Gemini Flash · Rime.ai
Built in Python with FastAPI + WebSockets

*Questions?*
