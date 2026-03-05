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
---

# STT Evaluation
## Deepgram Nova-2 vs OpenAI Whisper

Why we are running both pipelines in parallel
and what we are looking to learn from each.

---

## Why Test Two STT Models?

Speech-to-text is the first thing that can go wrong on a phone call.

If the agent mishears the customer, every downstream step —
the LLM response, the order, the TTS — is wrong too.

We are running Deepgram and Whisper **simultaneously** on the same
hardware and the same Twilio setup so we can compare them fairly
on the thing that actually matters: **real phone calls**.

---

## How the Two Pipelines Differ

```
Deepgram pipeline (/deepgram/incoming-call)
─────────────────────────────────────────────────────────
Twilio audio (mulaw 8kHz)
  → Deepgram WebSocket (streaming, real-time)
      → is_final transcript (every ~300ms of silence)
          → GPT-4o-mini → Rime TTS → Twilio


Whisper pipeline (/twillio/incoming-call)
─────────────────────────────────────────────────────────
Twilio audio (mulaw 8kHz)
  → VAD buffer (silence detection, ~1.5s threshold)
      → full utterance WAV → OpenAI Whisper API
          → transcript → GPT-4o-mini → Rime TTS → Twilio
```

Everything after the STT stage is **identical**.
Any difference in call quality is caused by the STT layer alone.

---

## Deepgram Nova-2 — How It Works

Deepgram keeps an open WebSocket for the entire call and transcribes
audio in real time as it arrives, token by token.

**Endpointing:** Deepgram's own model detects when you have stopped
speaking (`endpointing=300` — 300ms of silence triggers `is_final`).

**Key characteristics:**
- Transcript arrives within ~300ms of you finishing a sentence
- Handles mulaw 8kHz natively — no format conversion needed
- Interim results available (we ignore them, but they exist)
- Custom vocabulary — you can boost specific words (menu items, names)

---

## OpenAI Whisper — How It Works

Whisper is a batch model — it cannot transcribe until it has the
complete utterance. We handle endpointing ourselves using silence detection.

**Endpointing:** We monitor each 20ms audio frame from Twilio.
When 95%+ of a frame's bytes are `0xFF` (mulaw silence), we count it.
After 1.5 seconds of sustained silence following at least 200ms of speech,
we flush the buffer and send it to the Whisper API.

**Key characteristics:**
- Transcript only available after the caller has fully stopped speaking
- Needs format conversion (mulaw → WAV) before the API call
- Trained on a vastly larger and more diverse dataset than Deepgram
- No streaming — adds API round-trip latency on every turn

---

## Latency Comparison

| Stage | Deepgram | Whisper |
|---|---|---|
| Endpointing | 300ms (built-in) | ~1,500ms (silence threshold) |
| Transcription | Streaming — 0ms extra | API call ~300–600ms |
| **Time caller waits** | **~300ms** | **~1,800–2,100ms** |

Deepgram wins on latency — it is purpose-built for real-time phone audio.

Whisper's latency is the cost of its accuracy advantage.
The question is whether that trade-off is worth it.

---

## Accuracy Comparison — Where Each Wins

### Deepgram is better at:
- **Real-time phone audio** — trained specifically on telephony data
- **Fast speech** — handles rushed or clipped speech well
- **Short utterances** — "the ribeye please" transcribes accurately
- **Consistent latency** — predictable response time

### Whisper is better at:
- **Accents and non-native English** — trained on 680,000 hours of multilingual audio
- **Noisy environments** — more robust to kitchen noise, background music
- **Unusual words** — menu items, proper nouns, brand names
- **Longer, complex utterances** — "I'd like the mushroom risotto and a glass of prosecco"

---

## Cost Comparison

| | Deepgram Nova-2 | OpenAI Whisper |
|---|---|---|
| Pricing | $0.0043 / minute | $0.006 / minute |
| At 1,000 calls (3 min avg) | ~$13 | ~$18 |
| At 10,000 calls | ~$129 | ~$180 |
| Vendor | Separate API key | Same key as GPT |

Deepgram is ~28% cheaper per minute.
Whisper's cost is offset by removing one vendor from the stack —
one API key (OpenAI) handles both STT and LLM.

---

## What We Are Measuring

When we run test calls on both pipelines, we are looking for:

1. **Word error rate** — does the transcript match what was said?
   - Run the same phrases on both and compare
   - Pay attention to menu item names and prices

2. **End-to-end latency** — how long from finishing speaking to hearing the agent?
   - Deepgram's 300ms endpointing should be noticeably faster

3. **Sensitivity to noise** — what happens with background noise?
   - Try calling with music or noise in the background

4. **Interruption handling** — what if you speak before the agent finishes?
   - Both pipelines handle this differently at the buffering layer

---

## How to Switch Between Pipelines

Both are running on the same server simultaneously.
To switch, change the Twilio webhook URL for your phone number:

| Pipeline | Twilio Webhook URL |
|---|---|
| Whisper | `https://<ngrok>/twillio/incoming-call` |
| Deepgram | `https://<ngrok>/deepgram/incoming-call` |
| Chroma (GPU) | `https://<ngrok>/chroma/incoming-call` |

No code changes. No restart. Just update the URL in the Twilio console.

---

## Expected Outcome

We expect to find that:

- **Deepgram wins on latency** — 300ms endpointing vs 1.5s VAD is significant
- **Whisper wins on accuracy** — especially for accented speech and unusual words
- **Neither is clearly better for all scenarios**

The right choice depends on the client:
- High volume, fast-paced calls → Deepgram
- Diverse customer base with varied accents → Whisper
- Tight budget, single vendor → Whisper (OpenAI already in the stack)
- Need custom vocabulary (menu items) → Deepgram

This is exactly why we built the pipeline to be swappable.

---

# Summary

| | Deepgram | Whisper |
|---|---|---|
| **Latency** | Fast (~300ms) | Slower (~1.8s) |
| **Accuracy** | Good for phone audio | Better on accents/noise |
| **Cost** | $0.0043/min | $0.006/min |
| **Vendors** | +1 (Deepgram) | OpenAI only |
| **Endpointing** | Built-in | Custom VAD |
| **Custom vocab** | Yes | No |

**Test both. Let the data decide.**
