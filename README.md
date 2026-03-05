# Rime — Voice AI Restaurant Agent

A real-time voice AI agent that handles inbound phone calls for a restaurant. Callers are greeted by **Aria**, an AI assistant that takes food and drink orders and answers common questions about the restaurant.

---

## How It Works

When a customer calls the Twilio phone number, the system:

1. Receives the call via a Twilio webhook and returns TwiML that opens a media stream
2. Streams the caller's audio (mulaw 8kHz) to **Deepgram** for real-time speech-to-text
3. Sends each finalised transcript to **OpenAI GPT-4o-mini** to generate a response
4. Converts the response text to speech via **Rime.ai TTS**
5. Transcodes the audio to mulaw 8kHz and streams it back to the caller through Twilio

When the customer confirms their order, the LLM emits a structured `ORDER_COMPLETE` signal which the agent parses and logs.

---

## Architecture

```
Inbound call
     |
  Twilio
     |  webhook POST /twillio/incoming-call
     |  <-- TwiML: Connect <Stream url="wss://.../twillio/media-stream" />
     |
  WebSocket /twillio/media-stream  (FastAPI)
     |
     |-- audio frames (mulaw 8kHz) --> Deepgram WebSocket (STT)
     |                                       |
     |                              final transcript
     |                                       |
     |                            ConversationAgent (OpenAI gpt-4o-mini)
     |                                       |
     |                              response text
     |                                       |
     |                              Rime.ai TTS API
     |                                       |
     |                          WAV --> miniaudio resample --> audioop mulaw
     |                                       |
     |<------- mulaw 8kHz audio chunks ------+
     |
  Twilio plays audio to caller
```

### Key modules

| Path | Responsibility |
|------|---------------|
| `src/api.py` | FastAPI app entry point, registers router and middleware |
| `src/routers/twillio.py` | Twilio webhook + WebSocket handler, orchestrates the full call pipeline |
| `src/core/agent.py` | `ConversationAgent` — wraps OpenAI chat, tracks conversation history and order state |
| `src/core/restaurant.py` | Menu, FAQ, system prompt builder, and `Order` / `OrderItem` data classes |
| `src/services/tts.py` | Calls Rime.ai TTS, decodes and resamples audio to mulaw 8kHz for Twilio |
| `src/core/settings.py` | Loads API keys and config from environment variables |
| `src/middleware/logging.py` | Request logging middleware and uvicorn logger setup |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn[standard]` | ASGI server |
| `websockets` | WebSocket client for Deepgram |
| `deepgram-sdk` | Deepgram STT (Nova-2 model) |
| `openai` | OpenAI chat completions (gpt-4o-mini) |
| `httpx` | Async HTTP client for Rime TTS API |
| `miniaudio` | Audio decoding and resampling |
| `audioop-lts` | Linear16 PCM to mulaw encoding |
| `twilio` | Twilio helper library |
| `python-dotenv` | Load environment variables from `.env` |
| `loguru` | Structured logging |
| `certifi` | SSL certificate bundle |

---

## Setup

### Prerequisites

- Python 3.14+
- [`uv`](https://github.com/astral-sh/uv) (package manager)
- A publicly reachable URL for Twilio webhooks — use [ngrok](https://ngrok.com/) or similar during development

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment variables

Create a `.env` file in the project root:

```env
RIME_API_KEY=your_rime_api_key
OPENAI_AUTH=your_openai_api_key
DEEPGRAM_AUTH=your_deepgram_api_key
TWILLIO_AUTH=your_twilio_auth_token
TWILLIO_ACCOUNT_SID=your_twilio_account_sid

# Optional — post call data (transcript + order) to this URL when a call ends.
# Use the built-in receiver while developing:
WEBHOOK_URL=http://localhost:8000/webhook/call-complete

# Optional — path to a JSON config file defining the agent persona, menu, and FAQ.
# Defaults to the built-in Ristorante Bella config if not set.
AGENT_CONFIG_PATH=agent_config.json
```

### 3. Start the server

```bash
cd src
python api.py
```

The server starts on `http://0.0.0.0:8000`.

### 4. Expose the server with ngrok

```bash
ngrok http 8000
```

Copy the HTTPS forwarding URL (e.g. `https://abc123.ngrok.io`).

### 5. Configure Twilio

In your [Twilio Console](https://console.twilio.com), set the **Voice webhook** for your phone number to:

```
https://<your-ngrok-url>/twillio/incoming-call
```

HTTP method: `POST` (or `GET`).

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET/POST` | `/twillio/incoming-call` | Twilio voice webhook — returns TwiML to open a media stream |
| `WebSocket` | `/twillio/media-stream` | Bidirectional audio stream between Twilio and the agent |
| `GET` | `/health` | Health check — returns `{"message": "OK"}` |

---

## Environment Variable Reference

| Variable | Description |
|----------|-------------|
| `RIME_API_KEY` | Rime.ai API key for text-to-speech |
| `OPENAI_AUTH` | OpenAI API key — used for Whisper STT and GPT-4o-mini |
| `TWILLIO_AUTH` | Twilio auth token |
| `TWILLIO_ACCOUNT_SID` | Twilio account SID |
| `DEEPGRAM_AUTH` | Deepgram API key — used by the `/deepgram` pipeline |
| `WEBHOOK_URL` | URL to POST call data to after each call (optional) |
| `AGENT_CONFIG_PATH` | Path to a JSON agent config file (optional, see `agent_config.json`) |
