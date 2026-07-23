"""P0 preflight — one tool-call round trip per configured LLM profile.

Verifies each profile's endpoint + key + model can complete a tool-calling
request (the capability the agent loop depends on). Skips profiles that are not
configured. Run with real credentials in backend/.env:

    cd backend && python -m scripts.smoke_llm
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.llm import LLMClient, LLMConfigError  # noqa: E402

_ECHO_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "record_city",
            "description": "Record the city the user mentioned.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }
]

_MESSAGES = [
    {
        "role": "system",
        "content": "You must call record_city with the city named by the user.",
    },
    {"role": "user", "content": "Log that I'm in Bengaluru."},
]


async def _check(client: LLMClient, profile: str) -> bool:
    try:
        resp = await client.complete_with_tools(profile, _MESSAGES, _ECHO_TOOL)
    except LLMConfigError as exc:
        print(f"  {profile:6s}  SKIP  ({exc})")
        return True  # unconfigured is not a failure
    except Exception as exc:  # noqa: BLE001 — smoke script surfaces anything
        print(f"  {profile:6s}  FAIL  {type(exc).__name__}: {exc}")
        return False

    if resp.tool_calls:
        call = resp.tool_calls[0]
        print(
            f"  {profile:6s}  OK    tool={call.name} args={call.arguments} "
            f"tokens={resp.usage.get('total_tokens')}"
        )
        return True
    print(f"  {profile:6s}  WARN  no tool call; content={resp.content!r}")
    return False


async def main() -> int:
    settings = get_settings()
    client = LLMClient(settings)
    print("LLM profile smoke test (tool-calling round trip):")
    results = [await _check(client, p) for p in ("fast", "smart", "intent")]
    ok = all(results)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
