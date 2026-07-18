# noris AI for Home Assistant

A custom Home Assistant integration for the **ai.noris.de** LLM gateway.

It adds a **Conversation agent** (for Assist / voice control of your devices)
and an **AI Task** entity (structured or free-text data generation for
automations), built on the OpenAI-compatible Chat Completions API of the
gateway.

Only the on-premise **`vllm/*`** models are offered in the model picker, so no
prompt data is routed to external providers. Reranker and small draft models
are filtered out automatically.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories*
2. Add `https://github.com/fsippel/noris-ai`, category **Integration**
3. Install **noris AI**, then restart Home Assistant

### Manual

Copy the `custom_components/noris_ai` folder into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Configuration

1. *Settings → Devices & Services → Add Integration → noris AI*
2. Enter your API key (the `sk-bf-...` value; it is sent in the `x-bf-vk`
   header). The key is validated against `https://ai.noris.de/v1/models`.
3. On the integration, use **Add conversation agent** and/or **Add AI task**,
   pick a `vllm/*` model, and (for the conversation agent) optionally enable
   *Control Home Assistant* to allow device control via tool-calling.

## Notes

- **Authentication:** the gateway uses a custom `x-bf-vk` header instead of the
  standard `Authorization: Bearer` scheme. This is handled by the integration.
- **TLS:** certificates are verified via Home Assistant's shared HTTP client.
- **Tool-calling:** device control requires a model that supports function
  calling. Larger instruct models (e.g. `vllm/gpt-oss-120b`,
  `vllm/gemma-4-31b-it`) work best; rerankers are not selectable.
- **Reasoning models:** `<think>...</think>` output and vLLM `reasoning` /
  `reasoning_content` fields are surfaced as separate thinking content.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Disclaimer

Community integration, not affiliated with or supported by noris network AG.
