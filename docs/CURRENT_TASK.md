# CURRENT_TASK

## Stage

Add configurable LLM provider for the close-summary agent.

## Current task

**Complete.** The close-summary agent now supports Anthropic (default) and any OpenAI-compatible provider (e.g. Ollama Cloud). Added `CLOSE_SUMMARY_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `CLOSE_SUMMARY_MODEL` env vars. Added `langchain-openai` dependency and tests. Full suite: 151 tests pass.

## Branch

`feature/close-assistant-build`

## Next step

Commit the changes and push to `feature/close-assistant-build`.
