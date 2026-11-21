# Plan: Merge upstream rebuild (fsippel/noris-ai 0.2.11) — re-port STT/TTS platforms

**Date:** 2026-11-21
**Repo:** `~/sy17b.ha/noris-ai` (fork `phreatom/noris-ai`, upstream `fsippel/noris-ai`)

## Goal

Merge `upstream/main` (11 commits: full rebuild with streaming, reasoning toggle,
`models.py`, diagnostics, i18n, openai-3.x/probatio fixes) into our fork's `main`,
**preserving our STT and TTS platforms** and **our timeout fix**. Result: one
integration with upstream's architecture + our platforms, deployed to the
production HA instance (2026.11.1) after verification.

## Context an engineer must know

- **Two divergent lines from merge-base `bb9b99b`:**
  - **Our side** (phreatom): STT platform (`stt.py`), TTS platform (`tts.py`),
    shared helpers (`helpers.py`), timeout fix (PR #3: `REQUEST_TIMEOUT=60`,
    `CONNECT_TIMEOUT=5`, `MAX_RETRIES=1`), openai-3.x/httpx2 fix (`2a6aff8`),
    probatio tool-schema fix (`13c1dc3`). 102 tests. Docs: `docs/specs+plans/`
    for STT/TTS (historical records — keep, do not rewrite).
  - **Upstream side** (fsippel, v0.2.11): ground-up rebuild — streaming
    conversation with think-tag routing, non-streaming AI-task path, reasoning
    disabled by default (per-subentry toggle), `models.py` catalog module,
    `diagnostics.py`, en/de translations, 25 tests. Same probatio fix as ours
    (`4eab0b0`, probatio.to_openapi — convergent evolution, their approach
    mirrors HA core's Anthropic agent).
- **CRITICAL: upstream's rebuild does NOT contain our timeout fix.** Their
  `_create_client` = `AsyncOpenAI(base_url, api_key, http_client=get_async_client(hass))`
  — no explicit timeout/max_retries → SDK default 600 s + 2 retries. That is the
  exact code that let a stalled gateway hang the voice satellite for 451 s
  (production incident 2026-08-18, fixed by our PR #3). **Our client creation
  must survive the merge.**
- **Production dependencies on naming:** the HA instance has live subentries —
  STT (`stt.noris_ai_speech_to_text`), TTS (`tts.noris_ai_text_to_speech_2`,
  note the `_2`), conversation (LCARS prompt "Computer of the Fischer
  residence", model `vllm/release/gpt-oss-120b`, `llm_hass_api: [assist]`).
  Entity IDs derive from the subentry-type slugs — the string values of
  `STT_SUBENTRY_TYPE` / `TTS_SUBENTRY_TYPE` / `CONVERSATION_SUBENTRY_TYPE` in
  `const.py` must not change, or the "Computer" pipeline breaks. Verify, don't
  assume.
- **Auth:** our client authenticates via the gateway's custom `x-bf-vk` header
  (`default_headers={AUTH_HEADER: api_key}`); upstream's uses plain Bearer
  (`api_key=`). Both work; ours is the production-verified combination
  (verified live 2026-11-21). Keep ours.
- **Gateway state (2026-11-21):** STT (voxtral) and LLM (gpt-oss-120b) work;
  TTS is blocked at the gateway (403 `policy_provider_blocked` for access
  profile `adfs_users`; zero TTS models in the catalog — Kokoro/CosyVoice
  gone). The TTS *platform* must still work code-wise; only its model picker
  will show "no speech models" until noris re-enables TTS. User is clarifying
  with noris — do not "fix" the 403.
- **Test environment:** repo-local `.venv` (Python 3.14.10,
  `pytest-homeassistant==2026.11.1` — the official, release-matched package;
  upstream's tests were written against the deprecated
  `pytest-homeassistant-custom-component`, whose import path is
  `pytest_homeassistant_custom_component` → rewrite to
  `pytest_homeassistant.common`). Run tests with `.venv/bin/pytest`, not
  `pytest`. ffmpeg is installed (brew) for one STT test.
- Upstream's `config_flow.py` has a shared `NorisAISubentryFlowHandler`
  base class (with `async_step_init` → `async_step_advanced` → `_async_finish`)
  and only two subentry types (conversation, ai_task). Ours has four subentry
  flows (conversation, ai_task, STT, TTS) built on the OLD architecture —
  STT/TTS flows must be re-ported as `SttFlowHandler`/`TtsFlowHandler`
  subclasses of upstream's base. Bonus: upstream's conversation flow allows
  **model switching via reconfigure** (our old flow pinned the model) — the
  user wanted exactly this.
- `git merge-tree --write-tree main upstream/main` reports **16 conflicted
  files**: `.gitignore`, `README.md`, `custom_components/noris_ai/{__init__,
  config_flow, const, entity, manifest.json, strings.json,
  translations/de.json, translations/en.json}`, `requirements_test.txt`,
  `tests/{conftest, test_ai_task, test_config_flow, test_conversation,
  test_init}.py`. Auto-merged clean: `conversation.py`, `ai_task.py`, `hacs.json`,
  `pytest.ini` (identical on both sides), plus each side's exclusive files
  arrive untouched (ours: `stt.py`, `tts.py`, `helpers.py`, `ruff.toml`,
  `.github/workflows/ci.yml`, `docs/*`, `tests/test_{stt,tts,helpers,entity}.py`;
  theirs: `models.py`, `diagnostics.py`,
  `tests/test_{models,diagnostics,entity_stream,translations}.py`).

## Strategy decisions (already made — do not re-litigate)

1. **Merge, not rebase.** `main` is published on GitHub; a merge preserves both
   histories and git's future merge tracking. Rebase would rewrite public
   history (force-push) and lose the PR-merge topology.
2. **One merge commit.** The merge state spans Tasks 2–5 and is committed only
   in Task 6, after the full suite is green. This is inherent to `git merge` —
   conflicts are resolved in the working tree before the single commit.
3. **Client creation: ours.** `_create_client` keeps the `x-bf-vk` header,
   `httpx2.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT)`, `max_retries=
   MAX_RETRIES`, `http_client=get_async_client(hass)`. Everything else in
   `__init__.py` is upstream's structure (their `_validate_api_key` with
   `with_options(timeout=10.0)` is kept).
4. **manifest.json: upstream's requirements** (`openai>=2.21.0` unbound —
   resolves cleanly against HA 2026.11's pinned `openai==3.26.0` and survives
   future HA openai bumps; `voluptuous-openapi>=0.0.13` still used by their
   AI-task structure path). Version → `0.6.0`.
5. **requirements_test.txt: ours verbatim** (pinned, release-matched superset
   of both sides' needs: `pytest-homeassistant==2026.11.1`, `openai==3.26.0`,
   `hassil`, `home-assistant-intents`, `PyTurboJPEG`, `gazetteer-matcher`,
   `voluptuous-openapi==0.4.1`, `mutagen`, `ha-ffmpeg`, `ruff`).
6. **entity.py: upstream's streaming code + our `NorisAISubentryEntity`**
   appended (stt.py/tts.py import it; upstream has no equivalent base class).
7. **Model filtering stays name-pattern-based** (`AUDIO_MODEL_PATTERN`,
   `TTS_MODEL_PATTERN` in const.py). The gateway catalog's modality metadata is
   provably wrong (voxtral declares text-only input but transcribes audio;
   image models declare text output) — the patterns are load-bearing. Re-probed
   and confirmed 2026-11-21; do not "simplify" to modality metadata.

## Tasks

### Task 1 — Branch + baseline

Work in a worktree per the using-git-worktrees skill if other work shares this
repo; the repo-local `.venv` (Python 3.14 + `pytest-homeassistant==2026.11.1`)
lives in the main checkout, so a worktree must invoke it by absolute path
(`~/sy17b.ha/noris-ai/.venv/bin/pytest`). If nothing else touches the repo, a
plain branch in the main checkout is equivalent — either way, do the merge in
exactly one place and stay there until Task 6 commits it.

```bash
cd ~/sy17b.ha/noris-ai
git status --short            # expect only .DS_Store noise; no modified tracked files
git checkout -b merge/upstream-rebuild
.venv/bin/pytest -q           # baseline: 102 passed
```

Abort if the baseline is not 102/102 — fix the environment first, nothing else
matters. (`.DS_Store`/`docs/.DS_Store` are untracked junk; ignore, never commit.)

**Proof:** baseline test output shows 102 passed on the branch.

### Task 2 — Start merge, resolve the mechanical files

```bash
git merge upstream/main --no-ff --no-commit   # 16 conflicts expected (see list above)
```

Resolve, in this order:

- **`.gitignore`** — union of both sides' entries (both added patterns; no
  semantic conflict).
- **`requirements_test.txt`** — take OUR side verbatim (`git checkout --ours
  requirements_test.txt`). Documented rationale: pinned superset; both test
  suites' imports are covered by it.
- **`README.md`** — hand-merge: upstream's structure/feature descriptions
  (streaming, reasoning toggle, advanced options, diagnostics) + our STT/TTS
  sections (from our side) + a "This fork adds speech-to-text and
  text-to-speech platforms" note at the top. Keep it honest and short; this is
  the fork's front door.

`git add` each file as resolved. **Do not commit yet** (merge commit lands in
Task 6). Never run `git merge --abort` past this point without starting the plan
over.

**Proof:** `git status --short` shows the remaining package/test conflicts
(the `custom_components/*` and `tests/*` files from the conflict list) and no
longer the three resolved files.

### Task 3 — Core package resolution (the semantic heart)

For each file: upstream's version is the base; our deltas are re-added
explicitly. Resolve:

- **`__init__.py`**
  - Take upstream's structure (their `_validate_api_key`, their entry
    setup/unload, `type NorisAIConfigEntry = ConfigEntry[AsyncOpenAI]`).
  - Replace their `_create_client` body with OURS:
    `AsyncOpenAI(base_url=BASE_URL, api_key=api_key,
    default_headers={AUTH_HEADER: api_key}, http_client=get_async_client(hass),
    timeout=httpx2.Timeout(REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT),
    max_retries=MAX_RETRIES)` — with our docstring explaining the 600 s SDK
    default hazard. This is the timeout fix; it must not be "cleaned up".
  - `PLATFORMS = [Platform.AI_TASK, Platform.CONVERSATION, Platform.STT,
    Platform.TTS]`.
- **`const.py`** — semantic union. Keep upstream's constants verbatim; re-add
  ours that they lack: `AUTH_HEADER` ("x-bf-vk"), `REQUEST_TIMEOUT = 60.0`,
  `CONNECT_TIMEOUT = 5.0`, `MAX_RETRIES = 1`, `AUDIO_MODEL_PATTERN`,
  `TTS_MODEL_PATTERN`, `STT_SUBENTRY_TYPE`, `TTS_SUBENTRY_TYPE`,
  `STT_SUPPORTED_LANGUAGES`, `TTS_LANGUAGES_BY_PATTERN`, `TTS_VOICE`,
  `STT_TIMEOUT`. Deduplicate shared keys (`DOMAIN`, `BASE_URL`, `LOGGER`,
  `CONF_PROMPT`, subentry-type constants for conversation/ai_task — keep the
  upstream value if both sides define the same constant; if values differ,
  STOP and re-check the production-entity naming rule above before choosing).
- **`entity.py`** — upstream's file (streaming, `_ThinkTagFilter`, their
  probatio fix, their `NorisAIEntity`), then append our
  `NorisAISubentryEntity` class (from our `entity.py:211`) unchanged. Our
  `NorisAIEntity(NorisAISubentryEntity)` and old internals are dropped —
  upstream's entity replaces them; STT/TTS only need the subentry base.
- **`manifest.json`** — upstream's file with `"version": "0.6.0"` and
  requirements `["openai>=2.21.0", "voluptuous-openapi>=0.0.13"]`.

After resolving, syntax-check each file and assert the invariants:

```bash
cd custom_components/noris_ai
VENV=~/sy17b.ha/noris-ai/.venv/bin
for f in __init__.py const.py entity.py; do $VENV/python -c "import ast; ast.parse(open('$f').read())" || exit 1; done
grep -q "REQUEST_TIMEOUT\|CONNECT_TIMEOUT\|MAX_RETRIES" const.py      # timeout fix present
grep -q "httpx2.Timeout" __init__.py                                 # client fix present
grep -q "Platform.STT\|Platform.TTS" __init__.py                      # platforms registered
grep -q "class NorisAISubentryEntity" entity.py                       # stt/tts import target exists
```

`git add` the four files.

**Proof:** the four greps above pass; `git status --short` shows only
`config_flow.py`, `strings.json`, `translations/*`, and the five test files
still conflicted.

### Task 4 — Config flow re-port + models.py + translations

- **`models.py`** (arrived from upstream, no conflict — edit in place): add
  two catalog helpers alongside upstream's `async_get_model_options`, using
  OUR patterns:
  - `async_get_audio_model_options(client) -> list[SelectOptionDict]` —
    `client.models.list()` filtered by `AUDIO_MODEL_PATTERN`.
  - `async_get_speech_model_options(client) -> list[SelectOptionDict]` —
    filtered by `TTS_MODEL_PATTERN`.
  - Reuse upstream's `model_label`/`sort_key`/`default_model` helpers for the
    option values (DRY: no second labeling implementation). Unit-test
  -able in isolation; covered by Task 5 tests.
- **`config_flow.py`** — upstream's file as base; re-port from our old
  `config_flow.py`:
  - `SttFlowHandler(NorisAISubentryFlowHandler)` and
    `TtsFlowHandler(NorisAISubentryFlowHandler)`, registered in the
    `async_get_supported_subentry_types` classmethod on
    `NorisAIConfigFlow` (upstream `config_flow.py:64-69`) under
    `STT_SUBENTRY_TYPE` / `TTS_SUBENTRY_TYPE`.
  - The type slugs are `STT_SUBENTRY_TYPE = "stt"` and
    `TTS_SUBENTRY_TYPE = "tts"` (const.py:35, :93) — keep these exact string
    values; the production subentries are keyed by them.
  - STT flow: model dropdown from `async_get_audio_model_options`; name
    field; reconfigure step (only model + name — STT has no prompt/advanced
    options).
  - TTS flow: model dropdown from `async_get_speech_model_options`; name
    field; **abort with `no_speech_models`** when the catalog has no speech
    models (the noris 403 block — still the correct behavior); reconfigure.
  - Neither flow offers prompt/advanced options (upstream's base class handles
    those for chat subentries only — check the base class and, if the base
    forces them on all subclasses, override to hide them for STT/TTS).
- **`strings.json`** + **`translations/de.json`** + **`translations/en.json`**
  — merge keys: upstream's new flow strings (conversation/ai_task, advanced
  options) + our STT/TTS subentry strings (both languages; ours are keyed by
  the subentry-type slugs and must keep their exact keys). Hand-merge JSON —
  no tooling; verify with `python -m json.tool <file>` per file afterwards.

`git add` everything in this task.

**Proof:** `json.tool` parses all three translation files; the two new
`models.py` helpers appear in `git diff --cached --stat`; `git status --short`
shows only the five test files still conflicted.

### Task 5 — Test reconciliation (suite must be fully green)

- **`tests/conftest.py`** — OUR base (official `pytest_homeassistant.common`
  imports), extended with upstream's fixtures ported from their conftest
  (rewrite every `pytest_homeassistant_custom_component` import to
  `pytest_homeassistant`; fixture names and bodies otherwise unchanged —
  their five new test files import from this conftest, so keep its API).
- **`tests/test_stt.py`, `test_tts.py`, `test_helpers.py`** (ours, auto-merged
  in) — adjust only if conftest fixture names changed; these pin the platform
  behavior (entity identity, WAV conversion, language derivation,
  never-raises guarantee).
- **`tests/test_init.py`** — merge: upstream's init tests + **our
  client-creation/timeout regression tests** (the ones pinning
  `REQUEST_TIMEOUT=60` / `CONNECT_TIMEOUT=5` / `MAX_RETRIES=1` / `x-bf-vk`
  header survive the merge). These are the guard rails for decision 3.
- **`tests/test_config_flow.py`** — merge: upstream's conversation/ai_task
  flow tests + our STT/TTS flow tests, both adapted to the merged flow code.
  Add one new test pinning the **conversation reconfigure offers the model
  dropdown** (upstream behavior, the feature the user asked for; make sure the
  merged flow keeps it).
- **`tests/test_conversation.py`** — merge: upstream's streaming tests +
  preserve our regression intent
  (`test_conversation_payload_serializes`: model_args serialize via the SDK's
  own `openapi_dumps`) — re-anchor it to upstream's entity code path (their
  `_safe_convert`/`probatio.to_openapi`); if their `test_entity_stream.py`
  already covers the serialization, keep ours anyway as the explicit
  regression pin for the 2026-11-21 incident.
- **`tests/test_ai_task.py`** — upstream's version + re-add any of our
  structure-output tests that still apply.
- **`tests/test_entity.py`** (ours — old entity internals) vs
  **`test_entity_stream.py`** (theirs) — resolve: drop `test_entity.py` if
  every behavior it pins is covered by `test_entity_stream.py` (check: think-tag
  splitting precedence, `MAX_TOOL_ITERATIONS` bound, tool-call loop);
  port any test that is NOT covered. Do not keep duplicate coverage.
- **`tests/test_models.py`, `test_diagnostics.py`, `test_translations.py`**
  (theirs — auto-merged in) — keep; extend `test_translations.py` with our
  STT/TTS keys if it asserts full key parity between strings/translations.
- **Add** coverage for the new `models.py` helpers (audio/speech filtering) in
  `test_models.py` — pattern filtering is load-bearing (see decision 7).

Then the full gate:

```bash
.venv/bin/pytest -q          # ALL tests pass — iterate until they do
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

`git add` all resolved test files.

**Proof:** `pytest -q` ends with 0 failures (expected total ≥ 120: our ~100
portable tests + their ~25 + new pins, minus dropped duplicates); ruff exits 0.

### Task 6 — Commit the merge

Final verification checklist before the commit (evidence before assertions):

```bash
git status --short | grep -c '^UU\|^AA'   # 0 unresolved conflicts
.venv/bin/pytest -q                       # green
git diff main -- custom_components/noris_ai/const.py | grep -E '^\+.*(REQUEST_TIMEOUT|STT_SUBENTRY_TYPE|AUDIO_MODEL_PATTERN)'  # our constants survived
git show main:custom_components/noris_ai/const.py | grep -E 'SUBENTRY_TYPE\s*='  # compare slug values with merged const.py — MUST match
```

Commit the merge with a message documenting the semantic resolutions:

```
merge: upstream 0.2.11 rebuild, keeping STT/TTS platforms and the chat timeout fix

Merges fsippel/noris-ai's ground-up rebuild (streaming, reasoning toggle,
models.py catalog, diagnostics, i18n, probatio tool-schema fix) into our fork.

Deliberate resolutions:
- _create_client: kept our explicit httpx2 timeout (60 s / 5 s connect) and
  max_retries=1 (PR #3) — upstream's rebuild lost them; the SDK default of
  600 s hung the voice satellite in production on 2026-08-18.
- STT/TTS platforms re-ported onto upstream's subentry flow base class;
  subentry type slugs unchanged (production entity IDs depend on them).
- Model filtering stays name-pattern-based; the gateway's modality metadata
  is wrong for audio models (re-probed 2026-11-21).
- manifest: upstream requirements (openai>=2.21.0, voluptuous-openapi>=0.0.13),
  version 0.6.0.
```

### Task 7 — Post-merge polish (normal commits)

1. **`.github/workflows/ci.yml`** — verify it still matches the merged repo
   (it runs pytest + ruff on our pinned env; the job bound and passable per our
   `cc684cb` history). Adjust only if it references files that no longer exist.
2. **`hacs.json`** — auto-merged from upstream; verify no stale version/name
   fields contradict `manifest.json` 0.6.0.
3. **Version discipline** — `manifest.json` version 0.6.0 (done in Task 3);
   check `README.md` badges/mentions if any reference a version.
4. Commit (`chore: post-merge housekeeping (ci, hacs metadata)`) and push:
   `git push origin merge/upstream-rebuild`.

### Task 8 — Deploy + production verification (needs user approval for restart)

Deploy and restart are physical/disruptive — ask the user before `ha core restart`.

```bash
cd custom_components && tar czf - --exclude='__pycache__' --exclude='.DS_Store' noris_ai \
  | ssh root@ha.home.phreatom.de 'rm -rf /config/custom_components/noris_ai && tar xzf - -C /config/custom_components/'
```

Then (after user-approved `ha core restart`, wait for API up):

1. **Entities:** all three noris entities present with stable IDs
   (`conversation.noris_ai_conversation_agent`, `stt.noris_ai_speech_to_text`,
   `tts.noris_ai_text_to_speech_2`) — an ID shift means the pipeline reference
   breaks; if shifted, fix naming and redeploy before proceeding.
2. **Boot log:** `ha core logs -n 3000` grep `noris` — no setup errors, no
   requirements-not-found.
3. **Conversation E2E incl. tools:** WS `conversation/process` with the LCARS
   agent asking something that needs the HA API tools, e.g. "Wie ist das
   Wetter draußen?" — exercises upstream's streaming path + probatio tool
   schemas against the live gateway (the exact path that 500'd before
   `13c1dc3`). Expect a real answer, no 500, no `_Unsupported` in logs.
4. **Reasoning toggle note:** upstream defaults reasoning OFF — the LCARS agent
   answers ~3× faster now; re-enable per subentry in the UI if deeper reasoning
   is wanted. Tell the user; it changes agent behavior.
5. **STT entity:** registered + `unknown` idle state. Gateway STT already
   verified 2026-11-21 (voxtral transcribed real speech verbatim); the entity
   code path (platform → client) is covered by ported tests.
6. **TTS entity:** registered; a pipeline run will 403 at the gateway
   (expected — noris block, user is clarifying; do not "fix").
7. **Timeout guard:** confirm no 600 s hangs: the conversation call above
   should complete in seconds; check `entity.py` on the box contains the
   timeout constants (`grep -E 'REQUEST_TIMEOUT|MAX_RETRIES'
   /config/custom_components/noris_ai/const.py`).

**Proof:** verification transcript (entities, log grep, conversation answer).

### Task 9 — Closeout

1. Update `~/sy17b.ha/CLAUDE.md` (project memory): fork now at 0.6.0 =
  upstream 0.2.11 rebuild + STT/TTS re-ported; timeout fix preserved (watch
  for upstream regressions in future merges — grep for the constants);
  reasoning default OFF for the LCARS agent; conversation model now
  switchable via reconfigure (the feature the user asked for on 2026-11-21).
2. Optional follow-up (ask user): PR the STT/TTS platforms against
  upstream's NEW architecture (`fsippel/noris-ai`), so the platforms get a
  maintained upstream home instead of living only in this fork. The merged
  code is the natural PR source; upstream's repo has no STT/TTS and our
  original PRs #1/#2 predate their rebuild.
