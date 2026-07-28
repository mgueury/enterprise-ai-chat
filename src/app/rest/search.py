import pprint
import traceback
import os
import re
import base64
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import json
import oci
from oci.generative_ai_data import GenerateSqlFromNlJobClient
from oci.generative_ai_data.models import GenerateSqlFromNlDetails
from oci.retry import NoneRetryStrategy

import httpx
from langchain_core.tools import tool
from openai import OpenAI
from oci_genai_auth import OciInstancePrincipalAuth, OciResourcePrincipalAuth, OciUserPrincipalAuth

from config import config, require_config

DEFAULT_RESPONSES_MODEL = "google.gemini-2.5-pro"


def log(message: str) -> None:
    print(message, flush=True)


def build_oci_signer() -> Any:
    if config("AUTH_TYPE") == "RESOURCE_PRINCIPAL":
        return oci.auth.signers.get_resource_principals_signer()
    if config("AUTH_TYPE") == "CONFIG_FROM_FILE":
        config_file = os.getenv("OCI_CONFIG_FILE", "~/.oci/config")
        profile = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
        oci_config = oci.config.from_file(config_file, profile)
        return oci.signer.Signer(
            tenancy=oci_config["tenancy"],
            user=oci_config["user"],
            fingerprint=oci_config["fingerprint"],
            private_key_file_location=oci_config.get("key_file"),
            pass_phrase=oci.config.get_config_value_or_default(oci_config, "pass_phrase"),
            private_key_content=oci_config.get("key_content"),
        )
    return oci.auth.signers.InstancePrincipalsSecurityTokenSigner()


def oci_client_config() -> dict[str, Any]:
    """Return the OCI SDK config required when local config-file auth is used."""
    if config("AUTH_TYPE") == "CONFIG_FROM_FILE":
        return oci.config.from_file(
            os.getenv("OCI_CONFIG_FILE", "~/.oci/config"),
            os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"),
        )
    return {}


def get_semantic_store_query_connection(semantic_store_id: str) -> Any:
    """Resolve a semantic store to its querying OCI Database Tools connection.

    A semantic store has two Database Tools connections: one for enrichment and
    one for query execution.  SQL must use ``querying_connection_id``.
    """
    if not isinstance(semantic_store_id, str) or not semantic_store_id.strip():
        raise ValueError("semantic_store_id is required")

    signer = build_oci_signer()
    genai_client = oci.generative_ai.GenerativeAiClient(
        config=oci_client_config(),
        signer=signer,
        service_endpoint=f"https://generativeai.{config('REGION')}.oci.oraclecloud.com",
    )
    semantic_store = genai_client.get_semantic_store(semantic_store_id.strip()).data
    data_source = getattr(semantic_store, "data_source", None)
    connection_id = getattr(data_source, "querying_connection_id", None)
    if not isinstance(connection_id, str) or not connection_id:
        raise ValueError("Semantic store does not define a Database Tools querying connection")

    database_tools_client = oci.database_tools.DatabaseToolsClient(
        config=oci_client_config(),
        signer=signer,
    )
    return database_tools_client.get_database_tools_connection(connection_id).data


def _read_only_sql(sql: str) -> str:
    """Accept one SELECT/WITH statement only before opening a DB connection."""
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("sql is required")
    normalized = sql.strip().rstrip(";").strip()
    if ";" in normalized or not re.match(r"^(select|with)\b", normalized, re.IGNORECASE):
        raise ValueError("Only one read-only SELECT or WITH statement is allowed")
    return normalized


def _json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def execute_semantic_store_sql(semantic_store_id: str, sql: str) -> dict[str, Any]:
    """Execute one read-only SQL statement via a semantic store's query connection.

    This deliberately uses the Database Tools Runtime API instead of a direct
    database socket. It therefore works with a Database Tools private endpoint
    and does not expose or retrieve the Vault-backed database password.
    """
    statement = _read_only_sql(sql)
    signer = build_oci_signer()
    connection_details = get_semantic_store_query_connection(semantic_store_id)
    connection_id = getattr(connection_details, "id", None)
    runtime_endpoint = getattr(connection_details, "runtime_endpoint", None)
    if not isinstance(connection_id, str) or not connection_id or not isinstance(runtime_endpoint, str) or not runtime_endpoint:
        raise ValueError("Database Tools connection does not support runtime SQL execution")

    runtime_client = oci.database_tools_runtime.DatabaseToolsRuntimeClient(
        config=oci_client_config(),
        signer=signer,
        service_endpoint=runtime_endpoint,
    )
    input_details = oci.database_tools_runtime.models.ExecuteSqlInputStandardDetails(
        statement_text=statement,
        limit=1000,
    )
    request_details = oci.database_tools_runtime.models.ExecuteSqlDatabaseToolsConnectionSynchronousDetails(
        input=input_details,
    )
    response = runtime_client.execute_sql_database_tools_connection(
        connection_id,
        request_details,
        retry_strategy=NoneRetryStrategy(),
    ).data
    item = next(iter(getattr(response, "items", []) or []), None)
    result_set = getattr(item, "result_set", None)
    if result_set is None:
        error = getattr(item, "error", None)
        message = getattr(error, "message", None) if error is not None else None
        raise ValueError(message or "Database Tools Runtime returned no result set")

    columns = [
        (getattr(metadata, "unique_column_name", None) or getattr(metadata, "database_column_name", "")).lower()
        for metadata in (getattr(result_set, "metadata", None) or [])
    ]
    rows = [_json_value(row) for row in (getattr(result_set, "items", None) or [])]
    return {
        "sql": statement,
        "columns": columns,
        "rows": rows,
        "row_count": getattr(result_set, "count", None) if getattr(result_set, "count", None) is not None else len(rows),
        "has_more": bool(getattr(result_set, "has_more", False)),
        "offset": getattr(result_set, "offset", 0),
        "limit": getattr(result_set, "limit", len(rows)),
    }


def close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def responses_model_for_model_id(model_id: str) -> str:
    """Dedicated endpoint OCIDs are not valid ``client.responses.create`` models."""
    if re.match(r"^ocid1\.generativeaiendpoint\.oc1\.[a-z0-9-]+\.", model_id):
        return DEFAULT_RESPONSES_MODEL
    return model_id


def extract_generated_sql(data: Any) -> str | None:
    if isinstance(data, dict):
        print("dict")
        job_output = data.get("job_output") or data.get("jobOutput") or {}
        content = job_output.get("content") if isinstance(job_output, dict) else None
        return str(content) if content else None

    print("not dict")
    job_output = getattr(data, "job_output", None) or getattr(data, "jobOutput", None)
    content = getattr(job_output, "content", None) if job_output is not None else None
    return str(content) if content else None


def responses_get_client() -> OpenAI:
    require_config(["REGION", "PROJECT_OCID", "COMPARTMENT_OCID"])

    if config("AUTH_TYPE") == "RESOURCE_PRINCIPAL":
        auth = OciResourcePrincipalAuth()
    elif config("AUTH_TYPE") == "CONFIG_FROM_FILE":
        auth = OciUserPrincipalAuth(
            config_file=os.getenv("OCI_CONFIG_FILE", "~/.oci/config"),
            profile_name=os.getenv("OCI_CONFIG_PROFILE", "DEFAULT"),
        )
    else:
        auth = OciInstancePrincipalAuth()

    return OpenAI(
        base_url=f"https://inference.generativeai.{config('REGION')}.oci.oraclecloud.com/20231130/openai/v1",
        api_key="unused",
        project=config("PROJECT_OCID"),
        http_client=httpx.Client(
            auth=auth,
            headers={
                "opc-compartment-id": config("COMPARTMENT_OCID"),
            },
        ),
    )


def responses_format(response: Any) -> dict[str, Any] | None:
    log(pprint.pformat(response, indent=2, sort_dicts=True))

    message = next(
        (output for output in getattr(response, "output", []) if getattr(output, "type", None) == "message"),
        None,
    )
    if not message or not getattr(message, "content", None):
        return None

    content = message.content[0]
    text = getattr(content, "text", "")
    file_map: dict[str, dict[str, Any]] = {}
    file_search_results: list[dict[str, Any]] = []

    for item in getattr(response, "output", []):
        if getattr(item, "type", None) != "file_search_call":
            continue

        for result in getattr(item, "results", []) or []:
            attributes = getattr(result, "attributes", None) or {}
            additional_properties = getattr(result, "additional_properties", None) or {}
            normalized_result = {
                "file_id": result.file_id,
                "filename": getattr(result, "filename", None),
                "score": getattr(result, "score", None),
                "text": getattr(result, "text", None),
                "attributes": attributes,
                "vector_store_id": getattr(result, "vector_store_id", None),
                "chunk_id": additional_properties.get("chunk_id"),
                "pages": additional_properties.get("page_numbers") or [],
            }
            file_search_results.append(normalized_result)
            file_map[result.file_id] = {
                "url": attributes.get("customized_url_source"),
                "file_name": getattr(result, "filename", None),
                "score": getattr(result, "score", None),
            }

    citations = []
    for annotation in getattr(content, "annotations", []) or []:
        if getattr(annotation, "type", None) != "file_citation":
            continue

        file_id = annotation.file_id
        metadata = file_map.get(file_id, {})
        additional_properties = getattr(annotation, "additional_properties", None) or {}
        pages = additional_properties.get("page_numbers") or []
        if not isinstance(pages, list):
            pages = [pages]
        url = metadata.get("url")
        if url and pages:
            url = f"{url}#{pages[0]}"

        citations.append(
            {
                "file_id": file_id,
                "file_name": metadata.get("file_name"),
                "url": url,
                "score": metadata.get("score"),
                "pages": pages,
                "chunk_id": additional_properties.get("chunk_id"),
            }
        )

    unique = {}
    for citation in citations:
        key = (citation["file_id"], tuple(citation["pages"]))
        if key not in unique:
            unique[key] = citation

    citations_sorted = sorted(
        unique.values(),
        key=lambda citation: citation["score"] or 0,
        reverse=True,
    )

    log(pprint.pformat(citations_sorted, indent=2, sort_dicts=True))

    return {
        "response": text,
        "citations": citations_sorted,
        "results": file_search_results,
    }


def search_vector_store(
    question: str,
    model_id: str,
    vector_store_ids: list[str],
) -> dict[str, Any] | None:
    """Search the request-selected OCI vector stores with document-backed citations."""
    log("<responses_search>")

    try:
        require_config(["PROJECT_OCID"])

        client = None
        try:
            client = responses_get_client()
            response = client.responses.create(
                model=responses_model_for_model_id(model_id),
                temperature=0.0,
                input=(
                    "Answer using only information from the retrieved documents. "
                    "You may summarize or synthesize information that is explicitly supported by the retrieved text. "
                    "Do not use outside knowledge. If the retrieved documents do not contain enough information to answer, "
                    "say exactly: 'I don't have sufficient information in the documents.'. "
                    f"The question is: {question}"
                ),
                tools=[
                    {
                        "type": "file_search",
                        "vector_store_ids": vector_store_ids,
                        "max_num_results": 10,
                    }
                ],
                extra_headers={"OpenAI-Project": config("PROJECT_OCID")},
                tool_choice="required",
                include=["file_search_call.results"],
            )
        finally:
            if client is not None:
                close_client(client)

        log("<after> client.responses.create")
        result = responses_format(response)
        if result is not None:
            result["query"] = question
            result["vector_store_ids"] = vector_store_ids
        return result
    except Exception as exc:
        log(
            "\n".join(
                (
                    f"<responses_search> failed: {type(exc).__name__}: {exc}",
                    traceback.format_exc(),
                )
            ).rstrip()
        )
        raise


def search_database(question: str, semantic_store_id: str) -> dict[str, Any]:
    """Search in the Oracle Database Tables"""
    log("<search_in_database>")

    client = None
    try:
        require_config(["REGION"])
        service_endpoint = f"https://inference.generativeai.{config('REGION')}.oci.oraclecloud.com"

        signer = build_oci_signer()

        client = GenerateSqlFromNlJobClient(
            config=oci_client_config(),
            signer=signer,
            service_endpoint=service_endpoint,
            retry_strategy=NoneRetryStrategy(),
        )

        details = GenerateSqlFromNlDetails(
            display_name="search_in_database",
            description="Generate SQL from a natural language database question.",
            input_natural_language_query=question,
        )

        resp = client.generate_sql_from_nl(
            details,
            semantic_store_id,
        )

        data = resp.data
        if hasattr(data, "to_dict"):
            data = data.to_dict()

        sql = extract_generated_sql(data)
        if not sql:
            raise ValueError("No SQL was generated for the database search")
        execution = execute_semantic_store_sql(semantic_store_id, str(sql))
        # Preserve the existing tool contract while exposing the Runtime API's
        # richer JSON metadata (columns, pagination, and row count).
        return {**execution, "result": execution["rows"]}
    except Exception as exc:
        log(
            "\n".join(
                (
                    f"<search_database> failed: {type(exc).__name__}: {exc}",
                    traceback.format_exc(),
                )
            ).rstrip()
        )
        raise
    finally:
        if client is not None:
            close_client(client)

def run_code_interpreter(code: str, model_id: str) -> dict[str, Any]:
    """Execute Python code with OCI Code Interpreter and return its output."""
    client = None
    try:
        require_config(["PROJECT_OCID"])
        client = responses_get_client()
        response = client.responses.create(
            model=responses_model_for_model_id(model_id),
            input=f"Run this Python code and report the result:\n```python\n{code}\n```",
            tools=[{"type": "code_interpreter"}],
            tool_choice="required",
            extra_headers={"OpenAI-Project": config("PROJECT_OCID")},
        )
        call = next(
            (item for item in getattr(response, "output", []) if getattr(item, "type", None) == "code_interpreter_call"),
            None,
        )
        outputs = getattr(call, "outputs", None) or getattr(call, "results", None) or []
        output_text = "\n".join(
            str(getattr(output, "logs", None) or getattr(output, "output", None) or getattr(output, "text", None) or "")
            for output in outputs
        ).strip()
        message = next(
            (item for item in getattr(response, "output", []) if getattr(item, "type", None) == "message"),
            None,
        )
        message_content = getattr(message, "content", "") if message else ""
        message_text = "\n".join(
            str(getattr(part, "text", part)) for part in message_content
        ) if isinstance(message_content, list) else str(message_content)
        return {
            "code": getattr(call, "code", None) or getattr(call, "input", None) or code,
            "output": output_text or message_text,
            "response": message_text,
        }
    finally:
        if client is not None:
            close_client(client)


def get_oci_tools(
    model_id: str,
    vector_store_ids: tuple[str, ...],
    semantic_store_ids: tuple[str, ...],
    code_interpreter_enabled: bool,
) -> list[Any]:
    tools = []
    if vector_store_ids:
        @tool("search_vector_store")
        def search_vector_store_for_model(question: str) -> dict[str, Any] | None:
            """Search the request-selected OCI vector stores and return document-backed citations."""
            return search_vector_store(question, model_id, list(vector_store_ids))

        tools.append(search_vector_store_for_model)
    if code_interpreter_enabled:
        @tool("code_interpreter")
        def code_interpreter_for_model(code: str) -> dict[str, Any]:
            """Run Python code in OCI Code Interpreter and return the execution output."""
            return run_code_interpreter(code, model_id)

        tools.append(code_interpreter_for_model)
    if semantic_store_ids:
        semantic_store_id = semantic_store_ids[0]

        @tool("search_database")
        def search_database_for_store(question: str) -> dict[str, Any]:
            """Generate and run read-only SQL against the request-selected semantic store."""
            return search_database(question, semantic_store_id)

        tools.append(search_database_for_store)
    return tools
