import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import aiohttp
import uvicorn
from aiocache import SimpleMemoryCache, cached
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent import agent, reload_agent_config
from config import config_router, set_agent_reload_callback

app = FastAPI(title="LangGraph Agent")
set_agent_reload_callback(reload_agent_config)
app.include_router(config_router)

# Minimal user object passed through LangGraph runtime config to agent.py.
@dataclass
class AuthUser:
    identity: str
    auth_header: str
    email: str = "spam@oracle.com"
    is_authenticated: bool = True

    def dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity,
            "auth_header": self.auth_header,
            "email": self.email,
            "is_authenticated": self.is_authenticated,
        }


# In-memory thread store used by the FastAPI replacement for langgraph dev.
@dataclass
class ThreadState:
    messages: list[Any] = field(default_factory=list)
    next_message_id: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_accessed: float = field(default_factory=time.time)


threads: dict[str, ThreadState] = {}

# The Responses API has a response id as well as an optional conversation id.
# Keeping this small index lets a later request using ``previous_response_id``
# continue the same in-memory conversation.  As with ``threads``, it is local
# to one process and is deliberately not presented as durable storage.
response_threads: dict[str, ThreadState] = {}


# Bearer tokens are validated against IDCS and cached briefly to avoid
# repeated userinfo lookups during a chat session.
@cached(cache=SimpleMemoryCache, ttl=3600)
async def get_username_from_auth_header(auth_header: str) -> str:
    idcs_url = os.getenv("IDCS_URL")
    if not idcs_url:
        raise HTTPException(status_code=401, detail="IDCS_URL is not configured")

    userinfo_url = f"{idcs_url}oauth2/v1/userinfo"
    async with aiohttp.ClientSession() as session:
        async with session.get(userinfo_url, headers={"Authorization": auth_header}) as response:
            if response.status >= 400:
                raise HTTPException(status_code=401, detail="Invalid JWT Token")
            data = await response.json()
            username = data.get("sub")
            if not username:
                raise HTTPException(status_code=401, detail="Invalid JWT Token")
            return username


async def get_current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    # Local REST/MCP integration intentionally runs without endpoint
    # authentication unless explicitly enabled. OCI model authentication remains
    # independently configured in agent.py.
    if os.getenv("REST_AUTH_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return AuthUser(identity="local", auth_header="", is_authenticated=False)

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")

    try:
        scheme, token = authorization.split(maxsplit=1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header") from None

    if scheme == "Bearer":
        token = await get_username_from_auth_header(authorization)
    elif scheme != "User":
        raise HTTPException(status_code=401, detail="Access Denied")

    return AuthUser(identity=token, auth_header=authorization)


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(jsonable_encoder(payload))}\r\n\r\n"


def content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        content_type = content.get("type")
        if content_type in {"input_text", "output_text", "text"}:
            return str(content.get("text", ""))
        return json.dumps(jsonable_encoder(content))
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"}:
                parts.append(str(item.get("text", "")))
            else:
                parts.append(json.dumps(jsonable_encoder(item)))
        return "\n".join(part for part in parts if part)
    return str(content)


def responses_content_to_chat_oci(content: Any) -> Any:
    """Convert Responses content parts to ChatOCIGenAI/LangChain content.

    The chat UI sends OpenAI/OCI Responses parts (``input_text`` and
    ``input_image``). ChatOCIGenAI expects LangChain's multimodal vocabulary:
    ``text`` and ``image_url`` with the URL nested in an object.
    """
    if not isinstance(content, list):
        return content

    converted: list[Any] = []
    for part in content:
        if not isinstance(part, dict):
            converted.append(part)
            continue

        part_type = part.get("type")
        if part_type == "input_text":
            converted.append({"type": "text", "text": str(part.get("text", ""))})
            continue

        if part_type == "input_image":
            image_url = part.get("image_url")
            if isinstance(image_url, dict):
                image_url = image_url.get("url")
            if isinstance(image_url, str) and image_url:
                converted.append({"type": "image_url", "image_url": {"url": image_url}})
            continue

        converted.append(part)

    return converted


def message_from_payload(message: dict[str, Any]) -> Any:
    role = message.get("role") or message.get("type")
    content = message.get("content", "")

    if role in {"human", "user"}:
        return HumanMessage(content=responses_content_to_chat_oci(content))
    if role in {"ai", "assistant"}:
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    if role == "tool":
        return ToolMessage(
            content=content,
            tool_call_id=message.get("tool_call_id") or message.get("id") or "",
            name=message.get("name"),
        )

    raise HTTPException(status_code=400, detail=f"Unsupported message role: {role}")


def messages_from_payload(payload: dict[str, Any]) -> list[Any]:
    input_payload = payload.get("input") or {}
    raw_messages = input_payload.get("messages") or payload.get("messages") or []
    if not isinstance(raw_messages, list) or not raw_messages:
        raise HTTPException(status_code=400, detail="Missing input.messages")
    return [message_from_payload(message) for message in raw_messages]


def responses_messages_from_payload(payload: dict[str, Any]) -> list[Any]:
    """Translate the subset of Responses input used by the chat proxy.

    OCI accepts a string, a list of ``message`` input items, or a list of
    input content parts.  The LangGraph agent only needs the equivalent
    LangChain messages.  Unsupported continuation items are represented as a
    user message instead of being silently discarded, which makes this safe
    to extend when client-side tool continuations are wired to this service.
    """
    messages: list[Any] = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions:
        messages.append(SystemMessage(content=instructions))

    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        messages.append(HumanMessage(content=raw_input))
    elif isinstance(raw_input, list):
        if not raw_input:
            raise HTTPException(status_code=400, detail="Missing input")
        if all(isinstance(item, dict) and item.get("type") == "message" for item in raw_input):
            messages.extend(
                message_from_payload({
                    "role": item.get("role"),
                    "content": item.get("content", ""),
                    "tool_call_id": item.get("call_id"),
                    "id": item.get("id"),
                    "name": item.get("name"),
                })
                for item in raw_input
            )
        else:
            messages.append(HumanMessage(content=responses_content_to_chat_oci(raw_input)))
    else:
        raise HTTPException(status_code=400, detail="Missing input")

    if not any(isinstance(message, HumanMessage) for message in messages):
        # Function-call and approval continuations intentionally do not carry a
        # new user message.  The current LangGraph graph has already executed
        # its configured tools, so retain such continuation data as context for
        # the next turn rather than rejecting a valid Responses request.
        continuation = content_to_text(raw_input)
        if not continuation:
            raise HTTPException(status_code=400, detail="Responses input must contain content")
        messages.append(HumanMessage(content=f"Continuation result:\n{continuation}"))
    return messages


def vector_store_ids_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    """Read vector stores from standard Responses ``file_search`` tools."""
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return ()

    ids: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "file_search":
            continue
        configured_ids = tool.get("vector_store_ids")
        if not isinstance(configured_ids, list):
            continue
        ids.extend(
            vector_store_id.strip()
            for vector_store_id in configured_ids
            if isinstance(vector_store_id, str) and vector_store_id.strip()
        )
    return tuple(dict.fromkeys(ids))


def semantic_store_ids_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    """Read request-selected NL2SQL semantic stores from ``semantic_store`` tools."""
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return ()

    ids: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "semantic_store":
            continue
        configured_ids = tool.get("semantic_store_ids")
        if isinstance(configured_ids, str):
            configured_ids = [configured_ids]
        if not isinstance(configured_ids, list):
            continue
        ids.extend(
            semantic_store_id.strip()
            for semantic_store_id in configured_ids
            if isinstance(semantic_store_id, str) and semantic_store_id.strip()
        )
    return tuple(dict.fromkeys(ids))


def code_interpreter_enabled_from_payload(payload: dict[str, Any]) -> bool:
    tools = payload.get("tools")
    return isinstance(tools, list) and any(
        isinstance(tool, dict) and tool.get("type") == "code_interpreter"
        for tool in tools
    )


def bearer_token_from_mcp_tool(tool: dict[str, Any]) -> str | None:
    """Extract only a bearer credential supplied on one Responses MCP tool."""
    headers = tool.get("headers")
    authorization = None
    if isinstance(headers, dict):
        authorization = next(
            (value for name, value in headers.items() if isinstance(name, str) and name.lower() == "authorization"),
            None,
        )
    # OCI's OAuth MCP form uses a top-level access token rather than headers.
    if authorization is None:
        authorization = tool.get("authorization")
    if not isinstance(authorization, str) or not authorization.strip():
        return None

    authorization = authorization.strip()
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return f"Bearer {token}" if token else None
    # ``authorization`` in the OCI tool form is the raw bearer access token.
    return f"Bearer {authorization}"


def mcp_servers_from_payload(payload: dict[str, Any]) -> tuple[tuple[str, str, str | None], ...]:
    """Read MCP endpoints and their optional per-server bearer credentials."""
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return ()

    servers: list[tuple[str, str, str | None]] = []
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "mcp":
            continue
        label = tool.get("server_label")
        url = tool.get("server_url")
        if not isinstance(label, str) or not label.strip() or not isinstance(url, str):
            continue
        url = url.strip()
        if url.startswith(("http://", "https://")):
            servers.append((label.strip(), url, bearer_token_from_mcp_tool(tool)))
    return tuple(dict.fromkeys(servers))


def message_to_payload(message: Any) -> dict[str, Any]:
    message_type = getattr(message, "type", None)
    payload: dict[str, Any] = {
        "type": message_type or "ai",
        "content": content_to_text(getattr(message, "content", "")),
    }

    name = getattr(message, "name", None)
    if name:
        payload["name"] = name

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        payload["tool_calls"] = jsonable_encoder(tool_calls)

    artifact = getattr(message, "artifact", None)
    if artifact is not None:
        payload["artifact"] = jsonable_encoder(artifact)

    return payload


def append_messages_event(thread: ThreadState, messages: list[Any]) -> str:
    # The UI consumes LangGraph-style SSE payloads keyed by monotonic message ids.
    payload: dict[str, Any] = {"messages": {}}
    for message in messages:
        payload["messages"][str(thread.next_message_id)] = message_to_payload(message)
        thread.next_message_id += 1
    return sse_event(payload)


def agent_config(auth_user: AuthUser) -> dict[str, Any]:
    # agent.py reads this config to forward the original auth header to MCP tools.
    return {
        "configurable": {
            "user_id": auth_user.identity,
            "langgraph_auth_user": auth_user,
        }
    }


def get_thread_for_run(thread_id: str, payload: dict[str, Any]) -> ThreadState:
    if payload.get("assistant_id") not in {None, "agent"}:
        raise HTTPException(status_code=404, detail="Unknown assistant")

    thread = threads.get(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Unknown thread")

    return thread


def run_output_payload(messages: list[Any]) -> dict[str, Any]:
    return {"messages": [message_to_payload(message) for message in messages]}


def responses_sse_event(payload: dict[str, Any], event: str | None = None) -> str:
    prefix = f"event: {event}\r\n" if event else ""
    return f"{prefix}data: {json.dumps(jsonable_encoder(payload))}\r\n\r\n"


def response_item(
    response_id: str,
    text: str,
    status: str = "completed",
    annotations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"msg_{response_id}",
        "type": "message",
        "status": status,
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": annotations or []}],
    }


async def run_responses_agent(
    thread: ThreadState,
    new_messages: list[Any],
    auth_user: AuthUser,
    model_id: str,
    vector_store_ids: tuple[str, ...],
    semantic_store_ids: tuple[str, ...],
    code_interpreter_enabled: bool,
    mcp_servers: tuple[tuple[str, str, str | None], ...],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """Run the agent and persist only its final assistant message.

    The agent can emit intermediate tool-call messages while it executes MCP
    tools.  They are intentionally kept server-side here: this compatibility
    endpoint exposes a completed Responses message and does not claim to
    implement OCI's native MCP approval/function-call protocol.
    """
    input_messages = [*thread.messages, *new_messages]
    final_messages = input_messages
    final_text = ""
    file_search_results: list[dict[str, Any]] = []
    code_interpreter_results: list[dict[str, Any]] = []
    mcp_tool_results: list[dict[str, str]] = []
    seen_file_search_results: set[str] = set()
    seen_code_interpreter_results: set[str] = set()
    seen_mcp_results: set[tuple[str, str]] = set()
    # MCP tool names are unique for this local sample service. Use the label
    # supplied by the chat request so activity chips match the UI server name.
    mcp_server_label = mcp_servers[0][0] if len(mcp_servers) == 1 else "McpServer"

    async for state in agent.astream(
        {"messages": input_messages},
        config=agent_config(auth_user),
        stream_mode="values",
        model_id=model_id,
        vector_store_ids=vector_store_ids,
        semantic_store_ids=semantic_store_ids,
        code_interpreter_enabled=code_interpreter_enabled,
        mcp_servers=mcp_servers,
    ):
        messages = list(state.get("messages", []))
        if messages:
            final_messages = messages
            for message in messages:
                if not isinstance(message, ToolMessage):
                    continue
                raw_result = content_to_text(message.content)
                try:
                    result = json.loads(raw_result)
                except json.JSONDecodeError:
                    continue
                if getattr(message, "name", None) == "search_vector_store" and isinstance(result, dict) and raw_result not in seen_file_search_results:
                    file_search_results.append(result)
                    seen_file_search_results.add(raw_result)
                if getattr(message, "name", None) == "code_interpreter" and isinstance(result, dict) and raw_result not in seen_code_interpreter_results:
                    code_interpreter_results.append(result)
                    seen_code_interpreter_results.add(raw_result)
                tool_name = getattr(message, "name", None)
                if tool_name and tool_name not in {"search_vector_store", "code_interpreter"}:
                    result_key = (str(tool_name), raw_result)
                    if result_key not in seen_mcp_results:
                        mcp_tool_results.append({
                            "name": str(tool_name),
                            "server_label": mcp_server_label,
                            "output": raw_result,
                        })
                        seen_mcp_results.add(result_key)
            assistant_messages = [message for message in messages if isinstance(message, AIMessage)]
            if assistant_messages:
                final_text = content_to_text(assistant_messages[-1].content)

    thread.messages = final_messages
    thread.next_message_id = max(thread.next_message_id, len(final_messages))
    thread.last_accessed = time.time()
    return final_text, file_search_results, code_interpreter_results, mcp_tool_results


def file_citation_from_search_result(citation: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "file_citation",
        "file_id": citation.get("file_id"),
        "filename": citation.get("file_name"),
        "url": citation.get("url"),
        "score": citation.get("score"),
        "pages": citation.get("pages") or [],
        "chunk_id": citation.get("chunk_id"),
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/responses", response_model=None)
@app.post("/openai/v1/responses", include_in_schema=False, response_model=None)
@app.post("/v1/responses", include_in_schema=False, response_model=None)
async def create_response(
    payload: dict[str, Any] = Body(default_factory=dict),
    auth_user: AuthUser = Depends(get_current_user),
) -> StreamingResponse | JSONResponse:
    """Responses-compatible facade for the LangGraph agent.

    This is intentionally compatible with the request made by the chat
    application's OCI proxy: ``input``, ``instructions``, ``conversation``,
    ``previous_response_id`` and ``stream`` are accepted.  It emits standard
    Responses SSE event names, so the proxy can later replace its OCI request
    with this service without changing its event parser. File-search vector
    stores come from the request's ``tools`` list. Native OCI tool events and
    token usage are not emulated, so this service may produce fewer SSE chunks.
    """
    new_messages = responses_messages_from_payload(payload)
    previous_response_id = payload.get("previous_response_id")
    conversation_id = payload.get("conversation")

    # Match OCI's continuation precedence: previous_response_id wins when a
    # client accidentally includes both it and a conversation id.
    if isinstance(previous_response_id, str) and previous_response_id:
        thread = response_threads.get(previous_response_id)
        if thread is None:
            raise HTTPException(status_code=404, detail="Unknown previous_response_id")
    elif isinstance(conversation_id, str) and conversation_id:
        thread = threads.setdefault(f"response-conversation:{conversation_id}", ThreadState())
    else:
        thread = ThreadState()

    response_id = f"resp_{uuid.uuid4().hex}"
    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise HTTPException(status_code=400, detail="Missing model")
    model = model.strip()
    vector_store_ids = vector_store_ids_from_payload(payload)
    semantic_store_ids = semantic_store_ids_from_payload(payload)
    code_interpreter_enabled = code_interpreter_enabled_from_payload(payload)

    mcp_servers = mcp_servers_from_payload(payload)

    async def run() -> tuple[str, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
        async with thread.lock:
            text, file_search_results, code_interpreter_results, mcp_tool_results = await run_responses_agent(
                thread,
                new_messages,
                auth_user,
                model,
                vector_store_ids,
                semantic_store_ids,
                code_interpreter_enabled,
                mcp_servers,
            )
            response_threads[response_id] = thread
            annotations = [
                file_citation_from_search_result(citation)
                for result in file_search_results
                for citation in result.get("citations", [])
                if isinstance(citation, dict)
            ]
            item = response_item(response_id, text, annotations=annotations)
            file_search_items = [
                {
                    "id": f"fs_{response_id}_{index}",
                    "type": "file_search_call",
                    "status": "completed",
                    "queries": [result["query"]] if result.get("query") else [],
                    "results": result.get("results") or [],
                }
                for index, result in enumerate(file_search_results)
            ]
            response = {
                "id": response_id,
                "object": "response",
                "status": "completed",
                "model": model,
                # Include completed file-search calls so consumers of the final
                # Response object can render the same citations as SSE clients.
                "output": [item, *file_search_items],
            }
            if isinstance(conversation_id, str) and conversation_id:
                response["conversation"] = conversation_id
            return text, response, file_search_results, code_interpreter_results, mcp_tool_results

    if payload.get("stream", True) is False:
        try:
            _text, response, _file_search_results, _code_interpreter_results, _mcp_tool_results = await run()
            return JSONResponse(response)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Agent run failed") from exc

    async def event_stream() -> AsyncIterator[str]:
        created_response = {
            "id": response_id,
            "object": "response",
            "status": "in_progress",
            "model": model,
        }
        if isinstance(conversation_id, str) and conversation_id:
            created_response["conversation"] = conversation_id
        yield responses_sse_event({"type": "response.created", "response": created_response})

        item_id = f"msg_{response_id}"
        yield responses_sse_event({
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {"id": item_id, "type": "message", "status": "in_progress", "role": "assistant"},
        })
        try:
            text, response, file_search_results, code_interpreter_results, mcp_tool_results = await run()
            for index, result in enumerate(mcp_tool_results):
                mcp_item = {
                    "id": f"mcp_{response_id}_{index}",
                    "type": "mcp_call",
                    "status": "completed",
                    "name": result["name"],
                    "server_label": result["server_label"],
                    "output": result["output"],
                    "arguments": "{}",
                }
                yield responses_sse_event({
                    "type": "response.output_item.added",
                    "output_index": index,
                    "item": {**mcp_item, "status": "in_progress"},
                })
                yield responses_sse_event({
                    "type": "response.output_item.done",
                    "output_index": index,
                    "item": mcp_item,
                })
            for index, result in enumerate(file_search_results):
                search_id = f"fs_{response_id}_{index}"
                query = result.get("query") or ""
                file_search_item = {
                    "id": search_id,
                    "type": "file_search_call",
                    "status": "completed",
                    "queries": [query] if query else [],
                    # Keep the OCI file-search result shape.  Citations can be
                    # empty when the model did not annotate its prose, even
                    # though the search itself returned matching chunks.
                    "results": result.get("results") or [],
                }
                yield responses_sse_event({
                    "type": "response.output_item.added",
                    "output_index": 1 + index,
                    "item": {**file_search_item, "status": "in_progress"},
                })
                yield responses_sse_event({
                    "type": "response.output_item.done",
                    "output_index": 1 + index,
                    "item": file_search_item,
                })
            for index, result in enumerate(code_interpreter_results):
                interpreter_id = f"ci_{response_id}_{index}"
                interpreter_item = {
                    "id": interpreter_id,
                    "type": "code_interpreter_call",
                    "status": "completed",
                    "code": result.get("code") or "",
                    "outputs": [{"logs": result.get("output") or ""}],
                }
                yield responses_sse_event({
                    "type": "response.output_item.added",
                    "output_index": len(file_search_results) + index,
                    "item": {**interpreter_item, "status": "in_progress"},
                })
                yield responses_sse_event({
                    "type": "response.output_item.done",
                    "output_index": len(file_search_results) + index,
                    "item": interpreter_item,
                })
            if text:
                yield responses_sse_event({
                    "type": "response.output_text.delta",
                    "item_id": item_id,
                    "output_index": 0,
                    "content_index": 0,
                    "delta": text,
                })
            yield responses_sse_event({
                "type": "response.output_text.done",
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "text": text,
            })
            yield responses_sse_event({
                "type": "response.output_item.done",
                "output_index": 0,
                "item": response["output"][0],
            })
            yield responses_sse_event({"type": "response.completed", "response": response})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Keep the client error redacted, but record the exception type for
            # local service diagnostics without logging prompts or tool args.
            print(f"<responses> agent run failed: {type(exc).__name__}: {exc}", flush=True)
            # The chat proxy recognizes an SSE ``error`` event and turns it
            # into its normal terminal NDJSON error object.  Do not expose
            # exception details, tool arguments, or credentials to the client.
            yield responses_sse_event(
                {"error": {"message": "Agent run failed", "type": "server_error"}},
                event="error",
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        reload=False,
    )
