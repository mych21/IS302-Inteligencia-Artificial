# Foundry Local Agent (Responses Protocol)

This agent runs exclusively on your Windows PC using Microsoft Agent Framework
and the OpenAI-compatible endpoint of Foundry Local. No Azure subscription, cloud model deployment, API key,
or Azure sign-in is required. There is no cloud fallback.

The local `ResponsesHostServer` keeps the HTTP interface on
`http://localhost:8088` for Foundry Toolkit Agent Inspector. This server interface
does not mean that model inference is hosted in Azure.

## Prerequisites

- Python 3.13 or later.
- [Foundry Local](https://learn.microsoft.com/azure/foundry-local/get-started)
  installed on Windows.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed.
- For F5 debugging: VS Code, Python Debugger, and Foundry Toolkit extensions.

## Set up (PowerShell)

From the workspace root:

```powershell
Set-Location .\src\agent-framework-agent-basic-responses
uv sync --frozen
foundry model list
foundry model load phi-4-mini
```

Model acquisition may need internet access on first use. After the model and
runtime components are cached, inference runs locally.
Microsoft Learn MCP requires internet access even when the model is cached.

On startup, the agent uses `foundry server start`, loads the configured model,
and discovers the current daemon port with `foundry server status --output json`.
Only loopback HTTP endpoints are accepted. `OpenAIChatCompletionClient` talks to
this local endpoint, not to OpenAI or Azure. The older `FoundryLocalClient`
package uses legacy CLI commands incompatible with the installed Foundry CLI.

## Configuration

The agent reads [.env](src/agent-framework-agent-basic-responses/.env) next to
[main.py](src/agent-framework-agent-basic-responses/main.py):

```dotenv
FOUNDRY_LOCAL_MODEL=phi-4-mini-reasoning
```

Choose another supported local chat model from `foundry model list` by changing
this value. An existing process environment value takes precedence over `.env`.
A missing or empty value is an error, not a switch to a cloud provider.

Function calling and structured output support depend on the selected model.
Cloud-hosted tools such as Foundry web search and code interpreter are not
available through the local client.

## Microsoft Learn MCP

The agent connects to the official public Streamable HTTP MCP endpoint:
`https://learn.microsoft.com/api/mcp`. No authentication, API key, or Azure
subscription is needed.

Only these read-only documentation tools are exposed to the model:

- `microsoft_docs_search`: search Microsoft documentation.
- `microsoft_docs_fetch`: read a documentation article.
- `microsoft_code_sample_search`: find official code examples.

The agent keeps its MCP session open for the lifetime of the HTTP server and
closes it on normal shutdown. A failed MCP connection prevents startup;
tool errors are not replaced with fabricated documentation.

Model inference remains on your PC. Tool arguments (search queries and article
URLs) are sent to Microsoft Learn and results return to the local model.
Do not include secrets or private source code in documentation queries.
There is no offline documentation fallback.

Try this in Agent Inspector:
`Use Microsoft Learn to explain Foundry Local and include the official source URL.`
Inspect the tool calls as well as the final answer; a plausible answer alone
does not prove that the model used MCP. Tool calling reliability depends on the
selected local model.

Reference: [Microsoft Learn MCP Server](https://learn.microsoft.com/training/support/mcp).

## Run and test

Press **F5** from the workspace root to start the agent with its own virtual
environment and open Agent Inspector.

Or, from the agent source directory:

```powershell
uv run --frozen python main.py
```

Open **Foundry Toolkit: Open Agent Inspector** from the Command Palette and
connect to port `8088`. Send a message to test local inference.

This project uses local-only model inference with a remote documentation MCP.
The Azure deployment manifest and cloud container
definition have been removed; `azd deploy` is not part of this workflow.

## Configuration tests

From the agent source directory:

```powershell
uv run --frozen python -m unittest discover -s tests -v
```
