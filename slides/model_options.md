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

# Model Selection Guide
## Voice Agent Pipeline — Options & Trade-offs

Twilio · STT · LLM · TTS
Proprietary & Open Source

---

## The Three Decision Points

Every voice agent pipeline has three AI components.
Each one is independently swappable.

```
Caller voice
    ↓
[ STT ]  —  who transcribes the speech?
    ↓
[ LLM ]  —  who generates the response?
    ↓
[ TTS ]  —  who speaks the reply?
    ↓
Caller hears
```

Choosing the right model at each stage directly controls:
**latency · cost · accuracy · vendor dependency**

---

## Stage 1: Speech-to-Text (STT)

### What we need from an STT model
- **Streaming** — transcribe in real time, not after the call ends
- **Endpointing** — detect when the caller has finished speaking
- **Phone audio tolerance** — mulaw 8kHz, background noise, accents
- **Low latency** — ideally < 400ms to first final transcript

---

## STT — Proprietary Options

| Model | Streaming | Latency | Cost | Best For |
|---|---|---|---|---|
| **Deepgram Nova-2** ✓ | Yes | ~300ms | $0.0043/min | Our current stack |
| **AssemblyAI** | Yes | ~400ms | $0.0065/min | High accuracy priority |
| **OpenAI Whisper API** | No | 1–3s | $0.006/min | Batch transcription |
| **Google Speech v2** | Yes | ~350ms | $0.016/min | Multilingual/accents |
| **Azure Speech** | Yes | ~350ms | $0.016/min | Enterprise compliance |

**Recommendation for MVP:** Deepgram Nova-2 — best latency/cost for phone audio with streaming built in.

---

## STT — Open Source Options

| Model | Streaming | Hardware | Quality |
|---|---|---|---|
| **Whisper (OpenAI)** | No (batch) | CPU/GPU | Excellent |
| **faster-whisper** | Near-realtime | CPU/GPU | Excellent |
| **whisper-streaming** | Yes (chunked) | GPU | Good |
| **Silero VAD + Whisper** | Yes (with VAD) | CPU | Good |
| **NVIDIA Parakeet** | Yes | GPU (CUDA) | Excellent |

### Trade-offs of self-hosting STT
- No per-minute cost once deployed
- Requires GPU infrastructure (~$0.50–2/hr on cloud GPU)
- You manage uptime, scaling, and model updates
- **Break-even vs Deepgram:** ~200 hours of audio/month

---

## STT — Deepgram vs Whisper (self-hosted)

| | Deepgram Nova-2 | faster-whisper (self-hosted) |
|---|---|---|
| Streaming | Native | Chunked (with latency) |
| Setup | API key | GPU server + deployment |
| Latency | 300ms | 500ms–1s |
| Cost at 100hrs/mo | ~$26 | ~$30 (GPU compute) |
| Cost at 1,000hrs/mo | ~$258 | ~$60 (GPU amortised) |
| Custom vocabulary | Yes | No (prompt engineering) |
| Maintenance | None | Your team |

**Verdict:** Use Deepgram for the MVP and early scaling. Evaluate self-hosting beyond ~500 hours/month.

---

## Stage 2: Large Language Model (LLM)

### What we need from an LLM
- **Speed** — time-to-first-token matters more than throughput
- **Instruction following** — must stay on script, not hallucinate menu items
- **Short outputs** — phone calls demand 1–3 sentence responses
- **Structured output** — reliably emit `ORDER_COMPLETE: [JSON]`

---

## LLM — Proprietary Options

| Model | Speed | Cost (1M tokens) | Context | Best For |
|---|---|---|---|---|
| **GPT-4o-mini** ✓ | Fast | $0.15 in / $0.60 out | 128k | Our current stack |
| **GPT-4o** | Medium | $2.50 in / $10 out | 128k | Complex reasoning |
| **Claude Haiku 4.5** | Fastest | $0.80 in / $4 out | 200k | Ultra-low latency |
| **Claude Sonnet 4.6** | Medium | $3 in / $15 out | 200k | Nuanced dialogue |
| **Gemini 2.0 Flash** | Fast | $0.10 in / $0.40 out | 1M | Cheapest at scale |
| **Gemini 2.5 Pro** | Slow | $1.25 in / $10 out | 1M | Highest capability |

---

## LLM — Open Source Options

| Model | Params | Hardware | Strengths |
|---|---|---|---|
| **Llama 3.3 70B** | 70B | 2× A100 | Best open source quality |
| **Llama 3.1 8B** | 8B | 1× A10G | Fast, cheap, good enough |
| **Mistral 7B Instruct** | 7B | 1× A10G | Very fast, instruction tuned |
| **Mixtral 8×7B** | 47B (MoE) | 1× A100 | 7B speed, 70B quality |
| **Qwen 2.5 7B** | 7B | 1× A10G | Strong multilingual |
| **Phi-4 14B** | 14B | 1× A100 | Punches above its weight |

### Why open source for voice agents?
- **Fine-tuneable on your call data** — proprietary models cannot be fine-tuned easily
- **No per-token cost** — critical at high call volume
- **Data privacy** — calls never leave your infrastructure

---

## LLM — Cost at Scale

Assume: average call = 3 mins, ~500 tokens in + ~150 tokens out per call

| Model | Cost per call | 1,000 calls/mo | 10,000 calls/mo |
|---|---|---|---|
| GPT-4o | ~$0.23 | ~$230 | ~$2,300 |
| GPT-4o-mini | ~$0.02 | ~$20 | ~$200 |
| Gemini 2.0 Flash | ~$0.01 | ~$10 | ~$100 |
| Llama 3.1 8B (self-hosted) | ~$0.001 | ~$1 + GPU | ~$10 + GPU |
| Claude Haiku 4.5 | ~$0.04 | ~$40 | ~$400 |

**GPT-4o-mini / Gemini Flash** are the sensible proprietary choices.
**Llama 3.1 8B** becomes compelling above ~5,000 calls/month.

---

## LLM — Recommendation by Stage

| Stage | Recommended Model | Reason |
|---|---|---|
| **MVP / Demo** | GPT-4o-mini | Reliable, fast, easy, well-documented |
| **Production v1** | Gemini 2.0 Flash | Cheapest proprietary, comparable quality |
| **Scale (>5k calls/mo)** | Llama 3.3 70B (hosted) | Fine-tunable, no per-token cost |
| **Fine-tuned** | Llama 3.1 8B (fine-tuned) | Smallest model that knows your data |

Fine-tuning an 8B model on 1,000 real call transcripts typically outperforms GPT-4o-mini out-of-the-box on the specific task — with 10× lower inference cost.

---

## Stage 3: Text-to-Speech (TTS)

### What we need from a TTS model
- **Low latency** — time to first audio byte, not full file
- **Natural prosody** — sounds like a real person, not a robot
- **Mulaw output or easy conversion** — Twilio requires mulaw 8kHz
- **Stability** — consistent pronunciation of prices, menu items

---

## TTS — Proprietary Options

| Provider | Latency (first audio) | Cost | Voice Cloning | Streaming |
|---|---|---|---|---|
| **Rime.ai** ✓ | ~225ms | $0.015/1k chars | Yes | Yes |
| **Cartesia** | ~50–150ms | $0.015/1k chars | Yes | Yes |
| **ElevenLabs** | ~400ms | $0.18/1k chars | Yes | Yes |
| **OpenAI TTS** | ~300ms | $0.015/1k chars | No | Yes |
| **Google TTS** | ~200ms | $0.016/1k chars | No | Yes |
| **Azure Neural TTS** | ~200ms | $0.016/1k chars | Custom | Yes |

**Cartesia** is worth evaluating — it is purpose-built for real-time voice agents and has the lowest latency of any proprietary provider.

---

## TTS — Open Source Options

| Model | Quality | Hardware | Voice Cloning | Latency |
|---|---|---|---|---|
| **Kokoro TTS** | Excellent | CPU (fast) | No | ~100ms |
| **Coqui XTTS v2** | Very good | GPU | Yes (6s sample) | ~300ms GPU |
| **StyleTTS2** | Excellent | GPU | Yes | ~400ms GPU |
| **Piper TTS** | Good | CPU (very fast) | No | ~50ms |
| **Parler TTS** | Good | GPU | Via description | ~500ms |

---

## TTS — Open Source Deep Dive

### Kokoro TTS
- 82M parameters — runs fast on CPU, no GPU needed
- Among the highest quality open source voices available
- Apache 2.0 licence — fully commercial-safe
- **Ideal for:** high-volume deployments where per-character cost adds up

### Coqui XTTS v2
- Voice cloning from a 6-second audio sample
- Multi-lingual (17 languages)
- GPU recommended for sub-300ms latency
- **Ideal for:** branded restaurant voice cloned from a real person

### Piper TTS
- Extremely fast on CPU, designed for edge/embedded
- Limited voice variety but very consistent
- **Ideal for:** on-premise deployments with no cloud dependency

---

## TTS — Cost at Scale

Assume: average agent response = 80 characters

| Provider | Cost per response | 100k responses/mo |
|---|---|---|
| ElevenLabs | ~$0.014 | ~$1,440 |
| Rime.ai | ~$0.0012 | ~$120 |
| OpenAI TTS | ~$0.0012 | ~$120 |
| Cartesia | ~$0.0012 | ~$120 |
| Kokoro (self-hosted) | ~$0.0001 | ~$10 (compute) |
| Coqui XTTS (self-hosted) | ~$0.0001 | ~$10 (compute) |

ElevenLabs quality is exceptional but the cost is 10–12× higher than alternatives at scale.

---

## Full Stack Comparison

| Stack | Latency | Cost/call | Control | Complexity |
|---|---|---|---|---|
| **MVP (current)** GPT-4o-mini + Deepgram + Rime | ~1.5s | ~$0.025 | High | Low |
| **Cheapest proprietary** Gemini Flash + Deepgram + OpenAI TTS | ~1.3s | ~$0.015 | High | Low |
| **Lowest latency** GPT-4o-mini + Deepgram + Cartesia | ~1.0s | ~$0.025 | High | Low |
| **Fully open source** Llama 8B + faster-whisper + Kokoro | ~1.5s | ~$0.002 | Full | High |
| **Hybrid scale** Llama 70B + Deepgram + Kokoro | ~1.3s | ~$0.008 | Full | Medium |

---

## Open Source Stack — Architecture

Self-hosting all three components eliminates per-call API costs.
Practical at ~2,000+ calls/month.

```
Caller → Twilio → FastAPI server
                      |
              ┌───────┴────────┐
              │   GPU Server   │
              │                │
              │  faster-whisper│ ← STT
              │  Llama 3.1 8B  │ ← LLM (fine-tuned on call data)
              │  Kokoro TTS    │ ← TTS
              └───────┬────────┘
                      |
              Twilio ← audio response
```

**Infrastructure:** 1× A10G GPU (~$1.20/hr on Lambda Labs)
**Break-even:** ~2,500 calls/month vs Gemini Flash + Deepgram + Rime stack

---

## Recommendation: Phased Approach

### Phase 1 — MVP (Now)
`GPT-4o-mini` · `Deepgram Nova-2` · `Rime.ai`
Fastest to build, easiest to debug, solid quality.

### Phase 2 — Cost Optimisation (Month 2–3)
`Gemini 2.0 Flash` · `Deepgram Nova-2` · `Cartesia`
Swap LLM and TTS, keep Deepgram. ~40% cost reduction, lower latency.

### Phase 3 — Fine-Tuning (Month 4–6)
`Llama 3.1 8B (fine-tuned)` · `Deepgram Nova-2` · `Kokoro TTS`
Train LLM on real call transcripts. Best quality for the specific task.
Self-host TTS — eliminate per-character cost.

### Phase 4 — Full Self-Hosted (Scale)
`Llama 3.3 70B` · `faster-whisper` · `Kokoro TTS`
All on-premise. Maximum control, minimum per-call cost, full data privacy.

---

## Key Principle

> **No model decision is permanent.**
> The pipeline is designed so every component is independently swappable
> with a one-line config change.

```python
# Change LLM:    set OPENAI_MODEL = "gpt-4o" or swap client entirely
# Change STT:    update DEEPGRAM_URL parameters or point to self-hosted
# Change TTS:    swap synthesize_speech() implementation in services/tts.py
# Change agent:  update agent_config.json — no code changes needed
```

This is the core architectural advantage over Bland AI —
every vendor, model, and prompt is under your control.

---

# Summary

| Stage | MVP Choice | Scale Choice | Open Source |
|---|---|---|---|
| **STT** | Deepgram Nova-2 | Deepgram + custom vocab | faster-whisper |
| **LLM** | GPT-4o-mini | Gemini 2.0 Flash | Llama 3.1 8B (fine-tuned) |
| **TTS** | Rime.ai | Cartesia | Kokoro TTS |

The stack is modular. Start fast, optimise progressively.
