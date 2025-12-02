# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OrbitLLM is a RAG (Retrieval-Augmented Generation) backend API for air conditioner technical documentation. It provides two LLM backend options:
- **Google Gemini** with Context Caching (via Google AI API)
- **Azure OpenAI** (GPT-4o-mini) with implicit caching

The system ingests markdown documentation from air conditioner product manuals and uses advanced techniques like Map-Reduce, Semantic Sharding, and Agentic Routing to answer technical support questions.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running the Server
```bash
# Standard run
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Environment Variables
Create a `.env` file with:
```bash
GOOGLE_API_KEY=your_google_api_key
AZURE_OPENAI_ENDPOINT=your_azure_endpoint
AZURE_OPENAI_API_KEY=your_azure_api_key
AZURE_DEPLOYMENT_NAME=gpt-4o-mini  # or other model
```

## Architecture

### Core Components

**main.py** (820 lines) - Single-file FastAPI application containing:

1. **Global State Management** (`GlobalState` class, lines 54-68)
   - `cache_names`: List of Google Gemini cache names for shards
   - `azure_shards`: In-memory content shards for Azure (~100k tokens each)
   - `azure_shard_summaries`: Metadata summaries for agentic routing
   - `sessions`: Conversation history keyed by session_id

2. **Knowledge Base Ingestion**
   - `/ingest` (lines 117-215): Gemini endpoint - reads markdown files, shards by token count, creates Google Context Caches
   - `/ingest/azure` (lines 341-444): Azure endpoint - semantic sharding (groups by Series), stores in memory

3. **Question Answering**
   - `/ask` (lines 232-288): Gemini endpoint - Map-Reduce over cached shards
   - `/ask/azure` (lines 540-815): Azure endpoint - Pre-router FAQS check → Agentic Router → Map phase → Reduce/synthesis

### Semantic Sharding Strategy (Azure)

The `SERIES_MAPPING` dictionary (lines 293-327) maps filename prefixes to product series:
```python
"AFLEX-C": "FLEX-C"
"AFLEX-S": "FLEX-S"
"AFLEX-T": "FLEX-T"
"AGO": "GOLD"
# etc.
```

**Key function**: `get_series_from_filename()` (lines 329-339) - Matches longest prefix first to handle specific subseries (e.g., "AFLEX-C" before "AFLEX").

Documents are grouped by series before sharding, enabling the router to select only relevant shards for a query.

### Agentic Routing (Azure)

**Problem**: With 20+ shards, querying all is inefficient.

**Solution**: An LLM router (lines 626-707) analyzes:
- User question
- Conversation history
- Shard summaries (which series each shard contains)

**Router Actions**:
- `search`: Selects specific shards and rewrites query to include context from conversation history
- `clarify`: Asks user for model/series if needed for technical spec questions

**Critical Routing Rules** (lines 647-680):
- For clarification replies (e.g., user says "Virtus" after being asked "which model?"), the router **must** copy the *exact* original question and append the series name
- For generic troubleshooting (e.g., "my AC smells bad"), search all shards - do NOT ask for clarification
- For technical specs (e.g., "what's the cooling capacity?"), clarify which model first

### Pre-Router FAQS Check (Azure)

Before the main agentic router runs (lines 575-621):
1. **Input Classifier** (`is_valid_question()`, lines 517-538): Distinguishes standalone questions from short replies like "Yes" or "Flex-C"
2. **FAQS Priority**: If input is a question, check the FAQS shard first
3. **Fast Exit**: If FAQS has an answer, return immediately without querying other shards

### Conversational Memory

Session history is stored in `global_state.sessions[session_id]` (lines 558-572):
- Keeps last 6 messages (3 conversation turns)
- History is passed to both the router and the shard query functions
- Enables context-aware question interpretation

### Source Citation System

Azure endpoint returns structured sources (lines 447-515, 742-778):
- Each shard query must return JSON with `{"answer": "...", "sources": [{"reference": "Doc - Página X", "excerpt": "..."}]}`
- The excerpt must contain the **exact text** that supports the answer (not document headers or titles)
- Sources are deduplicated and grouped by file in the response

**Prompt Instructions** (lines 472-491):
- Extract specific table rows or text snippets, not generic headers
- Maximum 100 tokens per excerpt
- Return "NOT_FOUND" if information isn't in context

### Map-Reduce Pattern

Both endpoints use parallel shard querying:
1. **Map Phase**: Query selected shards concurrently with `asyncio.gather()`
2. **Reduce Phase**: If multiple valid responses, synthesize with a separate LLM call

## Key Constants

- `MAX_TOKENS_PER_SHARD`: 100,000 tokens
  - Gemini: Targets sub-15s latency (line 136)
  - Azure: Fits within gpt-4o-mini's 128k context window and maximizes 2M TPM quota parallelism (line 358)

## Important Patterns

### Token Counting
- **Gemini**: Uses `genai.GenerativeModel.count_tokens()` - requires API call (lines 155-156)
- **Azure**: Uses `tiktoken` with "cl100k_base" encoding - local/instant (lines 359, 397)

### Temperature Settings
- **Gemini**: 0.2 for all queries
- **Azure**: 0.0 for GPT-4 models, 1.0 for GPT-5 models (lines 501, 684)

### Error Handling
- Missing environment variables generate warnings but don't crash startup (lines 32-36)
- Failed shard queries return empty strings/dicts, not exceptions (lines 228-230, 513-515)

### CORS Configuration
Allows `http://localhost:3000` for frontend integration (lines 80-87)

## Testing the API

See `API_DOCUMENTATION.md` for detailed endpoint examples. Quick test:

```bash
# 1. Ingest knowledge base
curl -X POST http://localhost:8000/ingest/azure

# 2. Ask a question
curl -X POST http://localhost:8000/ask/azure \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué significa el error E9?", "session_id": "test1"}'
```

## Modifying the System

### Adding a New Product Series
1. Add mapping to `SERIES_MAPPING` (lines 293-327)
2. Use specific prefixes before generic ones (e.g., "AFLEX-C" before "AFLEX")
3. Add markdown files to `knowledge_base/` with matching prefix

### Adjusting Shard Size
Modify `MAX_TOKENS_PER_SHARD` in:
- `/ingest` endpoint (line 136)
- `/ingest/azure` endpoint (line 358)

Consider trade-offs:
- Larger shards = fewer shards to query = lower latency/cost, but less parallelism
- Smaller shards = more granular routing = better cache hit rates, but more overhead

### Customizing Router Behavior
Edit the `router_prompt` (lines 634-681) to:
- Change clarification rules
- Adjust when to search vs. clarify
- Modify query rewriting logic

The router output JSON must have:
```json
{"action": "search", "shards": [0, 2], "search_query": "..."}
// or
{"action": "clarify", "message": "..."}
```

### Modifying Source Extraction
The prompt in `query_azure_shard()` (lines 472-491) controls how LLMs extract sources. Key instructions:
- Rule #1: Don't assume information not in context
- Extract exact text snippets, not headers
- Max 100 tokens per excerpt
- Return "NOT_FOUND" if not found
