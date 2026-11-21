# noris AI for Home Assistant

**English Summary**

This is a fork of [fsippel/noris-ai](https://github.com/fsippel/noris-ai) that adds
**Speech-to-text** and **Text-to-speech** entities to the integration. It adds a
**Conversation agent** (for Assist / voice &amp; text control of your devices), an
**AI Task** entity (structured or free-text data generation for automations), a
**Speech-to-text** entity (transcribe Assist voice commands), and a
**Text-to-speech** entity (speak through the gateway's speech models), built on
the OpenAI-compatible Chat Completions, transcription, and speech APIs of the
gateway.

For the **Conversation agent** and **AI Task** entities, the model picker lists
the gateway's chat models (rerankers and draft models are filtered out
automatically). Speech-to-text and Text-to-speech entities draw models from the
other providers available on the gateway.

## Was ist das?

- 💬 **Conversation agent** — use it in Assist (voice or text pipelines) to chat
  or control your smart home. Optionally enable *Control Home Assistant* to let
  the model call entities via tool-calling.
- 🧩 **AI Task entity** — generate free text or structured (JSON) data from
  automations and scripts, e.g. summaries, classifications, sensor values.
- 🧠 **Reasoning models** — `thinking` output and vLLM `reasoning` /
  `reasoning_content` fields are surfaced as separate thinking content.
- 🌍 **Translations** — English and German UI.
- 🎙️ **Speech-to-text and Text-to-speech** — transcribe Assist voice commands with an audio model
  (Voxtral), or speak through available speech models. Add *Speech-to-text* or *Text-to-speech*
  entities and select them in your voice pipeline.

Die **noris AI**-Integration für Home Assistant erweitert dein Smart Home um vier zentrale Funktionen:

1. **Conversation Agent** — ein KI-basierter Sprach- und Textassistent für Home Assistant Assist. Du kannst Fragen stellen, Geräte steuern und Automationen auslösen.
2. **AI Task** — eine Entity für strukturierte und freie Datengenerierung. Nützlich für Automationen, die KI-basierte Eingaben brauchen (z. B. Datenextraktion, Klassenbildung, Synthesis).
3. **Speech-to-text** — transkribiert Assist-Sprachbefehle mit Audio-Modellen (z. B. Voxtral).
4. **Text-to-speech** — spricht durch die verfügbaren Sprachmodelle des Gateways.

Alle Funktionen laufen über das **Bifrost-Gateway** (`https://ai.noris.de/v1`) der noris network AG — eine OpenAI-kompatible API mit Zugriff auf lokale (`vllm/*`) und externe Modelle.

**Datenschutz:** Alle Gateway-Modelle sind wählbar, aber nur die **`vllm/*`**-Modelle laufen **on-premises** im noris-Rechenzentrum Nürnberg 6 — deine Daten verlassen dabei das Rechenzentrum nicht. Anthropic-Modelle sind ebenfalls wählbar, werden aber extern geroutet.

## Installation

### Über HACS (empfohlen)

1. Öffne Home Assistant und gehe zu **Settings → Devices & Services → HACS** (oder rufe HACS auf).
2. Oben rechts: **⋮** → **Custom repositories**.
3. Füge die URL dieses Repositorys hinzu: `https://github.com/fsippel/noris-ai`
   - **Kategorie:** *Integration*
4. Klick auf **Create**, dann suche nach **noris AI** in der HACS-Integrationsliste.
5. Klick auf **Install**, wähle eine Version und warte auf die Installation.
6. Starten Sie Home Assistant neu (oder verwenden Sie **Developer Tools → Restart Home Assistant**).

### Manuell

1. Laden Sie den neuesten Release herunter oder klonen Sie das Repository.
2. Kopieren Sie den Ordner `custom_components/noris_ai` in das Verzeichnis `config/custom_components/` Ihrer Home Assistant-Instanz.
3. Starten Sie Home Assistant neu.

## Konfiguration

1. Go to **Settings → Devices &amp; Services → Add Integration** and search for
   **noris AI**.
2. Paste your API key (the `sk-bf-…` value). The key is validated against
   `https://ai.noris.de/v1/models`.
3. Once added, open the integration card and use **Add conversation agent**,
   **Add AI task**, **Add speech-to-text**, and/or **Add text-to-speech** to create
   entities:
   - For the **Conversation agent** and **AI task**, pick a chat model from the
     dropdown (loaded live from the gateway).
   - For the conversation agent, optionally enable **Control Home Assistant**
     to allow device control via tool-calling.
   - For **Speech-to-text**, only models the gateway can transcribe with are listed
     — see [Speech-to-text](#speech-to-text) below.
   - For **Text-to-speech**, select from available speech models — see
     [Text-to-speech](#text-to-speech) below.

### Schritt 1: Integration hinzufügen

1. Gehe zu **Settings → Devices & Services → Integrations** (oder **Add Integration**).
2. Suche nach **noris AI** und wähle die Integration aus.
3. Gib deinen **API-Schlüssel** ein (Format: `sk-bf-...`).
   - Der Schlüssel wird beim Anlegen gegen `https://ai.noris.de/v1/models` validiert.
   - Home Assistant speichert den Schlüssel in seiner Konfiguration; in den Diagnostics wird er automatisch geschwärzt.
   - Wird der Schlüssel später ungültig, startet die Integration einen **Reauth-Flow** — du gibst einfach einen neuen Schlüssel ein.

### Schritt 2: Entities hinzufügen

Nach erfolgreicher Authentifizierung siehst du die noris AI-Integration in der Geräteliste.

#### Conversation Agent hinzufügen

1. Klick auf **Add conversation agent**.
2. Wähle ein Modell aus der Liste (Standard: `vllm/gpt-oss-120b`).
3. Optional:
   - **Control Home Assistant:** aktiviere dies, um Geräte per Tool-Call zu steuern (setzt ein Modell mit Function-Calling-Unterstützung voraus).
   - **Empfohlene Einstellungen:** vorgestellt, für die meisten Nutzer ausreichend.
   - **Erweiterte Einstellungen:** Anpassungen für Power User (z. B. `max_tokens`, Temperatur).

#### AI Task hinzufügen

1. Klick auf **Add AI task**.
2. Gib einen **Namen** an (z. B. `data_extractor`).
3. Wähle ein Modell (Standard: `vllm/gpt-oss-120b`).
4. Optional erweiterte Einstellungen.

Ein JSON-Schema für strukturierte Ausgaben wird nicht in diesem Flow konfiguriert, sondern **zur Laufzeit** beim Aufruf des Service `ai_task.generate_data` über den Parameter `structure` übergeben.

#### Speech-to-text / Text-to-speech hinzufügen

1. Klick auf **Add speech-to-text** bzw. **Add text-to-speech**.
2. Wähle ein Audio- bzw. Sprachmodell aus der Liste (live vom Gateway geladen).
3. Gehe zu **Settings → Voice assistants**, öffne deine Pipeline und setze **Speech-to-text** bzw. **Text-to-speech** auf die neue Entity.

## Modelle

Der **Modell-Picker** zeigt alle für dein Konto verfügbaren Modelle auf `ai.noris.de/v1/models`.

### Verfügbare Modelltypen

- **`vllm/*`** — On-premises-Modelle im Rechenzentrum Nürnberg 6. Sie stehen in der Liste ganz oben und sind die richtige Wahl, wenn Datenschutz eine Rolle spielt (z. B. `vllm/gpt-oss-120b`).
- **Anthropic-Modelle** — ebenfalls wählbar, werden aber über externe APIs geroutet.

### Automatisch gefiltert

- **Reranker-Modelle** — werden nicht angezeigt (nicht für Conversation/Task geeignet).
- **Draft-Modelle** — kleine Hilfsmodelle werden ausgeblendet.

### Standard

Das Standardmodell ist **`vllm/gpt-oss-120b`** (ein großes, generalistisches Instruct-Modell mit guter Function-Calling-Unterstützung).

## Hinweise

- **Chat and AI-task dropdowns:** populated **live** from `https://ai.noris.de/v1/models`
  when you add an agent or task. Models whose ID contains `reranker` or
  `harrier` (draft models) are filtered out.
- **Speech-to-text and Text-to-speech dropdowns:** populated live from available
  models on the gateway. The integration recognizes audio and speech models by name
  (Voxtral, Whisper, Kokoro-TTS, Cosyvoice3, etc.).
- **Tool-calling** (device control) requires a chat model that supports function
  calling. Larger instruct models (e.g. `vllm/gpt-oss-120b`,
  `vllm/gemma-4-31b-it`) work best.
- Even temporarily unavailable models remain selectable; availability changes
  over time and errors are reported cleanly at runtime.

### Authentifizierung

Der `sk-bf-...`-Schlüssel wird sowohl im Standard-**`Authorization: Bearer`**-Header (automatisch gesetzt durch die OpenAI-SDK) als auch im benutzerdefinierten **`x-bf-vk`**-Header des Gateways gesendet — so funktioniert die Authentifizierung unabhängig davon, welchen Weg das Gateway bewertet.

## Speech-to-text

The integration can transcribe voice commands using the gateway's audio models.

1. Go to **Settings → Devices & Services → noris AI** and add a **Speech-to-text** entity.
2. Pick an audio model. Only models that can transcribe are listed — today that is
   `vllm/qsu/voxtral-small-24b-2507` (Mistral's Voxtral Small 24B).
3. Go to **Settings → Voice assistants**, open your pipeline and set **Speech-to-text** to the new
   entity.

Supported languages are the ones Voxtral documents: German, English, Spanish, French, Italian,
Dutch, Portuguese and Hindi. Audio is sent as 16 kHz mono PCM wrapped in a WAV container.

> **Note on model detection:** the gateway's `/v1/models` catalog does not report audio capability
> correctly, so the integration recognises audio models by name (Voxtral, Whisper and similar). If
> your gateway gains an audio model that is not listed, open an issue.

## Text-to-speech

The integration can speak through the gateway's speech models.

1. Go to **Settings → Devices & Services → noris AI** and add a **Text-to-speech** entity.
2. Pick a speech model. Two are available today:
   - `Cosyvoice3/release/cosyvoice3-0.5b-rl` — multilingual, handles German and English.
   - `Kokoro-TTS/release/kokoro-tts-german-martin` — a German voice. It reads English
     phonetically, so pick it only for German.
3. Go to **Settings → Voice assistants**, open your pipeline and set **Text-to-speech** to the new
   entity.

Audio comes back as 24 kHz mono WAV. The languages an entity advertises are derived from its model
name, because the gateway's model catalog does not report language support.

> **Note:** the gateway requires a `voice` parameter but ignores its value — each model has exactly
> one voice — so the integration offers no voice picker.

### Reasoning-Modelle und „Gedanken"

Manche Modelle unterstützen **Reasoning** — das Modell stellt vor der eigentlichen Antwort interne Überlegungen an.

- Die Integration erfasst `<think>...</think>`-Blöcke und vLLM-Reasoning-Felder.
- Diese werden als separate **"Gedanken"** in der Nachricht angezeigt (getrennt von der Antwort).
- Nützlich zum Debuggen und zum Verständnis der Modelllogik.

### Token-Budget bei Reasoning-Modellen

Reasoning-Modelle benötigen großzügigere Token-Limits:

- **Conversation:** Standard `3000` Token `max_tokens`.
- **AI Task:** Standard `8000` Token `max_tokens`.

Falls dein Modell `max_tokens` überschreitet oder abbricht, erhöhe diese Werte in den erweiterten Einstellungen.

### Defekte Modelle und Fehlerbehandlung

Gelegentlich ist ein Modell im Gateway vorübergehend nicht nutzbar (typische Fehlermeldung des Gateways: "no keys found").

- Die Integration zeigt in diesem Fall eine **verständliche Fehlermeldung** an, anstatt abzustürzen.
- Wechsle dann einfach über die Rekonfiguration des Subentries auf ein anderes Modell.

### TLS und Sicherheit

- Zertifikate werden über Home Assistants globalen HTTP-Client verifiziert.
- Alle Anfragen an `ai.noris.de` werden über HTTPS gemacht.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Disclaimer

**Dies ist eine Community-Integration.** Sie ist nicht offiziell von der noris network AG unterstützt oder genehmigt. Verwende sie auf eigenes Risiko. Für Fragen oder Fehler kontaktiere bitte den Integration-Betreuer (GitHub Issues) oder die noris Community.
