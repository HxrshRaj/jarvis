# AI provider setup (LLM, vision, speech)

JARVIS talks to models only through `app/llm/providers.py`. Keys come from **backend environment variables** (or `backend/.env`);
they are never stored in the database, never returned by the API, and never logged. With no provider configured the app runs
in **offline mode**: tools, memory, document search (extractive answers) and evals work; open-ended answers, LLM planning,
screenshot analysis and server-side speech do not, and the UI says so.

## OpenAI-compatible endpoint (OpenAI, Ollama, LM Studio, vLLM, …)
```ini
JARVIS_LLM_PROVIDER=openai_compat
JARVIS_LLM_BASE_URL=https://api.openai.com/v1      # or http://localhost:11434/v1 for Ollama
JARVIS_LLM_API_KEY=<your key>                       # may be empty for local servers
JARVIS_LLM_MODEL=<chat model id>
# optional capabilities (leave empty to disable):
JARVIS_LLM_VISION_MODEL=<a vision-capable model id>   # enables "Look at This"
JARVIS_LLM_STT_MODEL=<e.g. whisper-1>                 # enables push-to-talk transcription
JARVIS_LLM_TTS_MODEL=<e.g. tts-1>                     # enables server-side spoken replies
# optional cost *estimates* (USD per 1M tokens):
JARVIS_PRICE_PROMPT_PER_MTOK=0
JARVIS_PRICE_COMPLETION_PER_MTOK=0
```
Restart the backend after changing variables. Check **Models & Providers** in the UI (read-only) or `GET /api/v1/capabilities`.

## What is verified
- The adapter is unit-tested against **scripted fake providers** (plan fallback, failures, citations, vision/voice endpoints).
- **It has not been exercised against a live provider in this repository's test runs.** Treat the first real run as an integration
  test: try a chat, a document question, and a screenshot, and check Models & Providers → Provider usage.
- Usage tracking records token counts the provider returns (measured). Cost is an estimate only when you configure pricing.
- Not implemented: streaming responses, native function-calling (plans are JSON, validated by the engine), wake-word.

## Voice behaviour
- Push-to-talk only: the microphone opens while the button is held, the track is released immediately, and audio goes to *your*
  backend `/voice/transcribe` (which forwards to the configured STT model). Nothing is recorded continuously.
- Spoken replies are opt-in ("Speak responses"). If no TTS model is configured the browser's local `speechSynthesis` is used (no upload).
  Mute, volume and a stop button are provided.
- Microphone-denied, unsupported-browser and provider-unavailable states are shown explicitly.
