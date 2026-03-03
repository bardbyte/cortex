# Examples

## verify_setup.py

One script, 5 checks. If all pass, your environment is ready.

```bash
# Setup
cp .env.example .env                          # Fill in credentials
pip install -e ".[dev]"
pip install langchain-core==0.3.83 --force-reinstall

# Terminal 1: Start MCP Toolbox
source .env
export LOOKER_INSTANCE_URL LOOKER_CLIENT_ID LOOKER_CLIENT_SECRET
./toolbox --tools-file config/tools.yaml

# Terminal 2: Verify
python examples/verify_setup.py
```

### What it checks

| # | Check | What it proves |
|---|-------|---------------|
| 1 | Environment variables | .env has all required credentials |
| 2 | langchain-core version | Pinned to 0.3.83 (SafeChain requirement) |
| 3 | SafeChain config | CIBIS auth resolves via ee_config |
| 4 | MCP tools | Toolbox server reachable, Looker tools load |
| 5 | Gemini LLM call | Full stack: auth → model → tool call → response |

### MCP Toolbox download

```bash
# macOS ARM
curl -L -o toolbox https://github.com/googleapis/genai-toolbox/releases/latest/download/toolbox-darwin-arm64 && chmod +x toolbox

# Linux x86_64
curl -L -o toolbox https://github.com/googleapis/genai-toolbox/releases/latest/download/toolbox-linux-amd64 && chmod +x toolbox
```

The `toolbox` binary reads `LOOKER_*` from shell env (not .env), so `source .env && export` before starting.
