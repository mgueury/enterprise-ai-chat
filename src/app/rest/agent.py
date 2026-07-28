from langchain_openai import ChatOpenAI
from langchain_oci import ChatOCIGenAI
from langgraph.prebuilt import create_react_agent
from langgraph.graph import StateGraph
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
import asyncio
import os
import pprint
import re
import httpx
import oci_openai 
from typing import Any
from config import DEFAULT_AGENT_PROMPT, config
from search import get_oci_tools

def build_llm_openai():
    auth = oci_openai.OciInstancePrincipalAuth()
    return ChatOpenAI(
        model="xai.grok-4-fast-reasoning",
        api_key="OCI",
        base_url="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com/20231130/actions/v1",
        http_client=httpx.Client(
            auth=auth,
            headers={"CompartmentId": config("COMPARTMENT_OCID")}
        ),
    )

def inference_region_for_model(model_id: str, default_region: str) -> str:
    """Use the endpoint OCID's region when the model is a dedicated endpoint."""
    match = re.match(r"^ocid1\.generativeaiendpoint\.oc1\.([a-z0-9-]+)\.", model_id)
    return match.group(1) if match else default_region


def build_llm(model_id: str) -> ChatOCIGenAI:
    auth_type = "API_KEY" if config("AUTH_TYPE") == "CONFIG_FROM_FILE" else config("AUTH_TYPE")
    region = inference_region_for_model(model_id, config("REGION"))
    return ChatOCIGenAI(
        auth_type="API_KEY" if "LIVELABS" in os.environ else auth_type,
        auth_profile=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"),
        auth_file_location=os.getenv("OCI_CONFIG_FILE", "~/.oci/config"),
        model_id=model_id,
        # model_id="meta.llama-4-scout-17b-16e-instruct",
        # model_id="cohere.command-a-03-2025",
        service_endpoint="https://inference.generativeai." + region + ".oci.oraclecloud.com",
        # model_id="xai.grok-4.3",
        # service_endpoint="https://inference.generativeai.us-chicago-1.oci.oraclecloud.com",
        compartment_id=config("COMPARTMENT_OCID"),
        is_stream=False,
        model_kwargs={"temperature": 0}
    )


def remove_empty_parameter_names(args: dict[str, Any] | None) -> dict[str, Any]:
    """Remove tool arguments whose parameter name is empty or only whitespace."""
    if not args:
        return {}

    return {
        key: value
        for key, value in args.items()
        if isinstance(key, str) and key.strip()
    }

async def inject_user_context(
    request: MCPToolCallRequest,
    handler,
):
    """Clean MCP arguments and turn MCP failures into agent-visible results.

    MCP credentials are set on the per-request server connection. Never replace
    those headers here with REST endpoint credentials or static configuration.
    """
    cleaned_args = remove_empty_parameter_names(request.args)
    modified_request = request.override(args=cleaned_args)
    try:
        return await handler(modified_request)
    except Exception as first_error:
        message = str(first_error)
        print(f"<inject_user_context> tool call failed: {message}", flush=True)

        # Retry once only for likely transient errors.
        transient_markers = ["timeout", "temporar", "connection reset", "503", "502", "429"]
        if any(marker in message.lower() for marker in transient_markers):
            print("<inject_user_context> retrying transient tool error once", flush=True)
            await asyncio.sleep(0.5)
            try:
                return await handler(modified_request)
            except Exception as second_error:
                message = str(second_error)
                print(f"<inject_user_context> retry failed: {message}", flush=True)

        # For validation/format errors, return structured payload instead of raising,
        # so the agent can reason on the error and try a corrected tool call.
        return {
            "status": "tool_error",
            "retryable_by_agent": True,
            "error": message,
            "guidance": "Tool call failed. Adjust parameters based on this error and retry with corrected values.",
        }

async def init(
    agent_name: str,
    prompt: str,
    model_id: str,
    vector_store_ids: tuple[str, ...],
    semantic_store_ids: tuple[str, ...],
    code_interpreter_enabled: bool,
    mcp_servers: tuple[tuple[str, str, str | None], ...],
    callback_handler=None,
) -> StateGraph:

    # Build the graph once at process startup; app.py streams runs from this object.
    # Waiting is important, since after reboot the MCP server could start afterwards.
    delay = 10
    client = None
    agent_tools = list(get_oci_tools(model_id, vector_store_ids, semantic_store_ids, code_interpreter_enabled))
    llm = build_llm(model_id)
    if not mcp_servers:
        print("No MCP tools supplied by the Responses request; starting agent without MCP tools")
        return create_react_agent(
            model=llm,
            tools=agent_tools,
            prompt=prompt,
            name=agent_name
        )

    for attempt in range(1, 10):
        try:
            print(f"Connecting to MCP {attempt}...")
            client = MultiServerMCPClient(
                {
                    label: {
                        "transport": "streamable_http",
                        "url": url,
                        **({"headers": {"Authorization": bearer_token}} if bearer_token else {}),
                    }
                    for label, url, bearer_token in mcp_servers
                },
                tool_interceptors=[inject_user_context],
            )
            tools = await client.get_tools()
            print( "-- tools ------------------------------------------------------------")
            pprint.pprint( tools )
            agent_tools = [*agent_tools, *tools]
            print( "-- agent_tools ------------------------------------------------------")
            pprint.pprint( agent_tools )
            break
        except Exception as e:
            print(f"Connection failed {attempt}: {e}")            
            print(f"Waiting for {delay} seconds before the next attempt...")
            await asyncio.sleep(delay)

    if client==None:
        raise RuntimeError("ERROR: connection to MCP Failed")

    agent = create_react_agent(
        model=llm,
        tools=agent_tools,
        prompt=prompt,
        name=agent_name
    ) 
    return agent    

async def build_agent(
    model_id: str,
    vector_store_ids: tuple[str, ...],
    semantic_store_ids: tuple[str, ...],
    code_interpreter_enabled: bool,
    mcp_servers: tuple[tuple[str, str, str | None], ...],
) -> StateGraph:
    return await init(
        "agent",
        config("AGENT_PROMPT") or DEFAULT_AGENT_PROMPT,
        model_id,
        vector_store_ids,
        semantic_store_ids,
        code_interpreter_enabled,
        mcp_servers,
    )


class AgentRuntime:
    def __init__(self):
        self._graphs: dict[tuple[str, tuple[str, ...], tuple[str, ...], bool, tuple[tuple[str, str, str | None], ...]], StateGraph] = {}
        self._reload_lock = asyncio.Lock()

    async def astream(
        self,
        *args,
        model_id: str,
        vector_store_ids: tuple[str, ...],
        semantic_store_ids: tuple[str, ...],
        code_interpreter_enabled: bool,
        mcp_servers: tuple[tuple[str, str, str | None], ...],
        **kwargs,
    ):
        async with self._reload_lock:
            graph_key = (model_id, vector_store_ids, semantic_store_ids, code_interpreter_enabled, mcp_servers)
            graph = self._graphs.get(graph_key)
            if graph is None:
                graph = await build_agent(model_id, vector_store_ids, semantic_store_ids, code_interpreter_enabled, mcp_servers)
                self._graphs[graph_key] = graph
        async for state in graph.astream(*args, **kwargs):
            yield state

    async def reload(self) -> None:
        async with self._reload_lock:
            self._graphs.clear()


agent = AgentRuntime()


async def reload_agent_config() -> None:
    await agent.reload()
