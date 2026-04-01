# Providers

Guide to LLM provider selection, model comparison, API key setup, and switching providers at runtime.

---

## Supported Providers

| Provider | Active Value | API Key Variable | API Docs |
|----------|-------------|-----------------|----------|
| Anthropic Claude | `"anthropic"` | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| Google Gemini | `"gemini"` | `GOOGLE_GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) |
| OpenAI GPT | `"openai"` | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |

---

## Switching Providers

Edit `config.json`:

```json
{
  "providers": {
    "active": "gemini"
  }
}
```

That's it — no agent files or tool schemas need to change.

---

## Model Selection

### Anthropic Claude

| Model | Speed | Cost | Best For |
|-------|-------|------|----------|
| `claude-opus-4-5` | Slow | High | Complex reasoning, long-form generation, nuanced tasks |
| `claude-opus-4-0` | Slow | Medium-High | Previous Opus — strong capability |
| `claude-sonnet-4-5` | Medium | Medium | **Recommended default** — balanced speed and quality |
| `claude-sonnet-3-7` | Medium | Medium | Extended thinking — step-by-step reasoning |
| `claude-haiku-3-5` | Fast | Low | Simple Q&A, classification, quick responses |
| `claude-haiku-3-0` | Very Fast | Very Low | High-throughput, latency-sensitive workloads |

To change the active Anthropic model:

```json
"anthropic": {
  "model": "claude-sonnet-4-5"
}
```

---

### Google Gemini

| Model | Speed | Cost | Best For |
|-------|-------|------|----------|
| `gemini-3.1-flash-lite-preview` | Ultra-fast | Very Low | **Default** — latest Flash Lite, cost-effective |
| `gemini-3.1-flash-preview` | Very Fast | Low | Latest Flash generation preview — fast + high quality |
| `gemini-3.1-pro-preview` | Medium | High | Most capable 3.1 — complex reasoning, long context |
| `gemini-2.5-pro` | Medium | High | Previous Pro — 1M token context, multimodal, complex tasks |
| `gemini-2.5-flash` | Fast | Medium | Previous Flash — fast + capable, best balance |
| `gemini-2.5-flash-lite` | Very Fast | Very Low | Ultra-fast / cheapest — high-volume, latency-critical |
| `gemini-2.0-pro` | Medium | Medium | Legacy Pro — strong reasoning, multimodal |
| `gemini-2.0-flash` | Fast | Low | Legacy Flash — reliable, widely supported |
| `gemini-1.5-pro` | Medium | Medium | Legacy long-context — 2M token window |
| `gemini-1.5-flash` | Fast | Low | Legacy fast — cost-effective for simple tasks |

---

### OpenAI GPT

| Model | Speed | Cost | Best For |
|-------|-------|------|----------|
| `gpt-4o` | Medium | High | **Recommended** — vision, tool use, complex tasks |
| `gpt-4o-mini` | Fast | Low | **Budget default** — excellent for everyday tasks |
| `gpt-4-turbo` | Medium | Medium | 128k context, strong reasoning |
| `o3` | Slow | High | Multi-step logic and math (reasoning model) |
| `o3-mini` | Medium | Medium | Fast chain-of-thought at lower cost |
| `o4-mini` | Fast | Medium | Latest reasoning mini — coding and math |
| `gpt-3.5-turbo` | Very Fast | Very Low | Legacy — simplest completions |

---

## Fallback Configuration

If the active provider's API call fails (timeout, rate limit, outage), the Orchestrator falls back through the configured order:

```json
"orchestration": {
  "fallback_provider_order": ["anthropic", "gemini", "openai"]
}
```

Change the order or remove providers as needed. The fallback chain is used in sequence until one succeeds or all fail.

---

## API Key Management

### Setting Keys

1. Copy `.env.example` to `.env`
2. Add your key(s):
   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   GOOGLE_GEMINI_API_KEY=AIza...
   OPENAI_API_KEY=sk-...
   ```
3. Only the key for your active provider is required at runtime

### Security Best Practices

- Never commit `.env` to version control (it is already in `.gitignore`)
- Use least-privilege API keys with only the permissions you need
- Rotate keys regularly and immediately if exposed
- Use environment-specific keys (different keys for dev/staging/prod)
- Consider using a secrets manager (AWS Secrets Manager, HashiCorp Vault) in production

### Key Sources

| Provider | API Key URL |
|----------|-------------|
| Anthropic | https://console.anthropic.com/settings/keys |
| Google Gemini | https://aistudio.google.com/app/apikey |
| OpenAI | https://platform.openai.com/api-keys |

---

## Provider-Specific Notes

### Anthropic

- The Anthropic API uses `system` + `messages` format
- `max_tokens` is a hard limit per request (default: 8192)
- Rate limits vary by tier — check [Anthropic rate limits](https://docs.anthropic.com/en/api/rate-limits)
- Extended thinking (for `claude-sonnet-3-7`) requires passing `thinking.type = "enabled"`

### Google Gemini

- Uses the `generativelanguage.googleapis.com/v1beta` endpoint
- 1M+ token context available on Gemini 2.5 Pro
- Safety filters apply by default — some content may be blocked
- Multimodal inputs (images, PDFs) supported on 2.5 Pro and 2.0 models

### OpenAI

- Uses the standard OpenAI Chat Completions API
- `o3` and `o4-mini` are reasoning models — they use a different parameter set (no `temperature`)
- Function/tool calling supported on all `gpt-4` and `gpt-4o` models
- Vision supported on `gpt-4o` variants

---

## Adding a New Provider

1. Add a new entry under `providers` in `config.json`:

   ```json
   "my_provider": {
     "model": "my-model-id",
     "available_models": {
       "my-model-id": "Description of the model"
     },
     "api_key_env": "MY_PROVIDER_API_KEY",
     "max_tokens": 8192,
     "temperature": 0.7,
     "top_p": 1.0,
     "api_base": "https://api.myprovider.com/v1"
   }
   ```

2. Add the API key to `.env.example`:

   ```bash
   MY_PROVIDER_API_KEY=your_key_here
   ```

3. Implement the provider adapter in your LLM runner (maps to the provider's API format)

4. Update `providers.active` to `"my_provider"`

See [Extension Guide](Extension-Guide.md) for the full provider integration walkthrough.
