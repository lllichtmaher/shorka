"""Claude streaming + tool-use loop.

Each user utterance triggers `handle()`, which runs a multi-turn loop:
  - Stream a Claude turn; narrate text deltas as they arrive (via Narrator).
  - When a tool_use block completes, execute the tool synchronously.
  - Append tool_result; loop again.
  - Stop when Claude returns a turn with no tool_use blocks.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from anthropic import AsyncAnthropic

from .config import settings
from .middleware import confirm as confirm_mw
from .narrator import Narrator
from .session import Session
from .tools import claude_schemas, get_tool


SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")
MAX_TURNS = 6


async def _q_iter(q: asyncio.Queue) -> AsyncIterator[str]:
    while True:
        v = await q.get()
        if v is None:
            return
        yield v


class Brain:
    def __init__(self, narrator: Narrator, session: Session) -> None:
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.narrator = narrator
        self.session = session

    async def handle(self, user_text: str) -> None:
        self.session.messages.append({"role": "user", "content": user_text})
        self.session.interrupted = False

        try:
            for _ in range(MAX_TURNS):
                assistant_blocks = await self._stream_one_turn()
                if not assistant_blocks:
                    return
                self.session.messages.append({"role": "assistant", "content": assistant_blocks})
                tool_calls = [b for b in assistant_blocks if b.get("type") == "tool_use"]
                if not tool_calls:
                    return
                tool_results = await self._run_tools(tool_calls)
                self.session.messages.append({"role": "user", "content": tool_results})
        except (asyncio.CancelledError, Exception):
            # Repair message history so orphaned tool_use blocks don't permanently
            # break the Anthropic API (every tool_use must have a matching tool_result).
            self._repair_messages()
            raise

    async def _stream_one_turn(self) -> list[dict]:
        assistant_blocks: list[dict] = []
        text_q: Optional[asyncio.Queue] = None
        speak_task: Optional[asyncio.Task] = None
        current_text = ""
        current_tool: Optional[dict] = None
        current_tool_input_buf = ""
        current_block_type: Optional[str] = None

        try:
            async with self.client.messages.stream(
                model=settings.claude_model,
                max_tokens=settings.claude_max_tokens,
                system=SYSTEM_PROMPT,
                tools=claude_schemas(),
                messages=self.session.messages,
            ) as stream:
                async for event in stream:
                    et = event.type

                    if et == "content_block_start":
                        block = event.content_block
                        current_block_type = block.type
                        if current_block_type == "text":
                            current_text = ""
                            text_q = asyncio.Queue()
                            speak_task = asyncio.create_task(
                                self.narrator.say_streaming(_q_iter(text_q))
                            )
                        elif current_block_type == "tool_use":
                            current_tool = {"id": block.id, "name": block.name, "input": {}}
                            current_tool_input_buf = ""

                    elif et == "content_block_delta":
                        delta = event.delta
                        dtype = getattr(delta, "type", None)
                        if dtype == "text_delta" and text_q is not None:
                            txt = delta.text
                            current_text += txt
                            await text_q.put(txt)
                        elif dtype == "input_json_delta":
                            current_tool_input_buf += delta.partial_json

                    elif et == "content_block_stop":
                        if current_block_type == "text":
                            if text_q is not None:
                                await text_q.put(None)
                            assistant_blocks.append({"type": "text", "text": current_text})
                            if current_text.strip():
                                print(f"[shorka] {current_text.strip()}", file=sys.stderr)
                                self.session.add_transcript("assistant", current_text)
                            current_text = ""
                            text_q = None
                        elif current_block_type == "tool_use" and current_tool is not None:
                            try:
                                current_tool["input"] = (
                                    json.loads(current_tool_input_buf)
                                    if current_tool_input_buf
                                    else {}
                                )
                            except json.JSONDecodeError:
                                current_tool["input"] = {}
                            assistant_blocks.append(
                                {
                                    "type": "tool_use",
                                    "id": current_tool["id"],
                                    "name": current_tool["name"],
                                    "input": current_tool["input"],
                                }
                            )
                            print(f"[tool] {current_tool['name']}({json.dumps(current_tool['input'], ensure_ascii=False)})", file=sys.stderr)
                            current_tool = None
                            current_tool_input_buf = ""
                        current_block_type = None

                    elif et == "message_stop":
                        break
        except asyncio.CancelledError:
            if speak_task is not None and not speak_task.done():
                speak_task.cancel()
            raise

        if speak_task is not None:
            try:
                await speak_task
            except (asyncio.CancelledError, Exception):
                pass

        return assistant_blocks

    async def _run_tools(self, tool_calls: list[dict]) -> list[dict]:
        results: list[dict] = []
        for call in tool_calls:
            t = get_tool(call["name"])
            tool_input = call.get("input", {})
            if t is None:
                result: Any = {"ok": False, "error": f"unknown tool {call['name']}"}
            else:
                if t.dangerous:
                    allowed = await confirm_mw.gate(call["name"], tool_input, True)
                    if not allowed:
                        result = {"ok": False, "error": "user did not confirm"}
                    else:
                        result = await self._invoke(t, tool_input)
                else:
                    result = await self._invoke(t, tool_input)
            if not isinstance(result, dict):
                result = {"ok": True, "result": result}
            revert = self.session.last_revert
            self.session.last_revert = None
            self.session.add_history(call["name"], tool_input, result, revert=revert)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": json.dumps(result),
                    "is_error": not bool(result.get("ok", True)),
                }
            )
        return results

    @staticmethod
    async def _invoke(t: Any, tool_input: dict) -> Any:
        try:
            return await t.fn(**tool_input)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _repair_messages(self) -> None:
        """Ensure every tool_use block in the last assistant message has a matching tool_result.

        When barge-in cancels handle() mid-tool-use, the session history can end with
        an assistant message containing tool_use blocks but no subsequent user message
        with tool_result blocks.  The Anthropic API rejects this, breaking all future
        requests.  This method patches the history so it's always valid.
        """
        msgs = self.session.messages
        if not msgs:
            return

        # Find the last assistant message
        last_asst_idx = None
        for i in range(len(msgs) - 1, -1, -1):
            if msgs[i].get("role") == "assistant":
                last_asst_idx = i
                break

        if last_asst_idx is None:
            return

        content = msgs[last_asst_idx].get("content", [])
        if not isinstance(content, list):
            return

        tool_use_ids = [
            b["id"] for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if not tool_use_ids:
            return

        # Check if there's already a matching tool_result message right after
        next_idx = last_asst_idx + 1
        existing_result_ids: set[str] = set()
        if next_idx < len(msgs) and msgs[next_idx].get("role") == "user":
            next_content = msgs[next_idx].get("content", [])
            if isinstance(next_content, list):
                for b in next_content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        existing_result_ids.add(b.get("tool_use_id", ""))

        missing = [tid for tid in tool_use_ids if tid not in existing_result_ids]
        if not missing:
            return

        stub_results = [
            {
                "type": "tool_result",
                "tool_use_id": tid,
                "content": json.dumps({"ok": False, "error": "cancelled by user"}),
                "is_error": True,
            }
            for tid in missing
        ]

        if existing_result_ids and next_idx < len(msgs):
            # Append to the existing tool_result message
            msgs[next_idx]["content"].extend(stub_results)
        else:
            # Insert a new user message with the stub results
            msgs.insert(next_idx, {"role": "user", "content": stub_results})
