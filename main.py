import os
import glob
import json
import datetime
import logging
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import tiktoken
from openai import AsyncOpenAI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-mini") # Default or from env

if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
    logger.warning("Azure OpenAI credentials not found in environment variables.")

# Configure Azure OpenAI
azure_client = None
if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
    azure_client = AsyncOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        # base_url=AZURE_OPENAI_ENDPOINT
    )

import asyncio

# Global state for shards
class GlobalState:
    _instance = None
    azure_shards: List[str] = [] # Store content in memory for Azure (Implicit Caching)
    azure_shard_summaries: List[str] = [] # Store summaries for Agentic Routing
    sessions: dict = {} # Store session history: {session_id: [{"role": "user", "content": "..."}]}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
        return cls._instance

global_state = GlobalState()

# --- Cache Configuration ---
CACHE_FILE_PATH = "./shards_cache.json"

def save_shards_to_cache():
    """Saves current shards and summaries to disk as JSON."""
    cache_data = {
        "azure_shards": global_state.azure_shards,
        "azure_shard_summaries": global_state.azure_shard_summaries
    }
    try:
        with open(CACHE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
        logger.info(f"Cache saved to {CACHE_FILE_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")
        return False

def load_shards_from_cache() -> bool:
    """Loads shards and summaries from disk cache. Returns True if successful."""
    if not os.path.exists(CACHE_FILE_PATH):
        logger.info(f"Cache file not found at {CACHE_FILE_PATH}")
        return False

    try:
        with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        global_state.azure_shards = cache_data.get("azure_shards", [])
        global_state.azure_shard_summaries = cache_data.get("azure_shard_summaries", [])

        if global_state.azure_shards:
            logger.info(f"Loaded {len(global_state.azure_shards)} shards from cache")
            return True
        else:
            logger.warning("Cache file was empty or corrupted")
            return False
    except Exception as e:
        logger.error(f"Failed to load cache: {e}")
        return False

async def ingest_knowledge_base_internal() -> bool:
    """Internal function to ingest knowledge base. Returns True if successful."""
    kb_dir = "./knowledge_base"
    if not os.path.exists(kb_dir):
        logger.error(f"Directory '{kb_dir}' not found.")
        return False

    md_files = glob.glob(os.path.join(kb_dir, "*.md"))
    if not md_files:
        logger.error(f"No .md files found in '{kb_dir}'.")
        return False

    MAX_TOKENS_PER_SHARD = 100000
    encoding = tiktoken.get_encoding("cl100k_base")

    shards = []
    total_tokens_processed = 0
    total_chars_processed = 0
    summaries = []

    logger.info(f"Starting ingestion of {len(md_files)} files with Semantic Sharding...")

    # Group files by Series
    files_by_series = {}
    for file_path in md_files:
        filename = os.path.basename(file_path)
        series = get_series_from_filename(filename)
        if series == "OTHER":
            logger.warning(f"File '{filename}' categorized as OTHER")
        if series not in files_by_series:
            files_by_series[series] = []
        files_by_series[series].append(file_path)

    # Process each Series
    for series, series_files in files_by_series.items():
        logger.info(f"Processing Series: {series} ({len(series_files)} files)")

        current_series_content = ""
        current_series_tokens = 0
        current_series_filenames = []

        for file_path in series_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    filename = os.path.basename(file_path)
                    formatted_content = f"\n\n--- DOCUMENTO: {filename} (SERIE: {series}) ---\n\n{content}"

                    file_tokens = len(encoding.encode(formatted_content))

                    if current_series_tokens + file_tokens > MAX_TOKENS_PER_SHARD:
                        if current_series_content:
                            shards.append(current_series_content)
                            summary = f"SERIES: {series}\nFILES: {', '.join(current_series_filenames)}"
                            summaries.append(summary)
                            current_series_filenames = []

                        current_series_content = formatted_content
                        current_series_tokens = file_tokens
                        current_series_filenames.append(filename)
                    else:
                        current_series_content += formatted_content
                        current_series_tokens += file_tokens
                        current_series_filenames.append(filename)

                    total_tokens_processed += file_tokens
                    total_chars_processed += len(formatted_content)

            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")

        if current_series_content:
            shards.append(current_series_content)
            summary = f"SERIES: {series}\nFILES: {', '.join(current_series_filenames)}"
            summaries.append(summary)

    if not shards:
        logger.error("No content to process.")
        return False

    global_state.azure_shards = shards
    global_state.azure_shard_summaries = summaries

    # Save to cache
    save_shards_to_cache()

    logger.info(f"Ingestion complete. {len(shards)} shards created, {total_tokens_processed} tokens processed.")
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load from cache or run ingestion
    logger.info("Server starting up...")

    if load_shards_from_cache():
        logger.info("✓ Knowledge base loaded from cache (instant startup)")
    else:
        logger.info("Cache not found. Running initial ingestion...")
        success = await ingest_knowledge_base_internal()
        if success:
            logger.info("✓ Knowledge base ingested and cached")
        else:
            logger.warning("⚠ Failed to load knowledge base. Call /ingest manually.")

    yield
    # Shutdown logic
    logger.info("Server shutting down...")

app = FastAPI(title="OrbitLLM Backend", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # Must be False when using allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---

class IngestResponse(BaseModel):
    message: str
    shard_names: List[str]
    document_count: int
    total_chars: int
    total_tokens: int
    shards_created: int

class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    series: Optional[str] = None  # Optional: bypass router and search directly in this series

class PageDetail(BaseModel):
    reference: str
    excerpt: str

class SourceItem(BaseModel):
    file: str
    pages: List[PageDetail]

class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem] = []
    needs_clarification: bool = False
    available_series: List[str] = []

# --- Endpoints ---

# Mapping from filename prefix to Series Name
SERIES_MAPPING = {
    "AFLEX-C": "FLEX-C",  # Specific AFLEX-C subseries
    "AFLEX-S": "FLEX-S",  # Specific AFLEX-S subseries
    "AFLEX-T": "FLEX-T",  # Specific AFLEX-T subseries
    "AALEF": "ALEF",
    "AFLEX": "FLEX",  # Generic AFLEX (will only match if not C/S/T)
    "AMAX": "MAXIMA",
    "AVENT": "VENTO",
    "EASY": "EASY FLEX",
    "ONI": "ONIX",
    "VIRTU": "VIRTUS",
    "ADRA": "RESOLUTE",
    "ADA": "ARMOR",
    "ADN": "ADN",
    "ADW": "WINTER",
    "ADZ": "WINTER",
    "AGO": "GOLD",
    "ATI": "TITAN",
    "FREE": "FREEDOM",
    "SP": "ADN",
    "TITAN": "TITAN", # Explicit TITAN
    "VIRTUS": "VIRTUS", # Explicit VIRTUS
    "ONIX": "ONIX", # Explicit ONIX
    "VENTO": "VENTO", # Explicit VENTO
    "FREEDOM": "FREEDOM", # Explicit FREEDOM
    "GOLD": "GOLD", # Explicit GOLD
    "AMAX": "MAXIMA", # Explicit AMAX
    "AFLEX": "FLEX", # Explicit AFLEX
    "AALEF": "ALEF", # Explicit AALEF
    "ONI-C": "ONIX", # Explicit ONI-C
    "AGO-T": "GOLD", # Explicit AGO-T
    "WINTER": "WINTER", # Explicit WINTER
    "MAXIMA": "MAXIMA", # Explicit MAXIMA
    "faqs": "FAQS" # Explicit FAQS
}

def get_series_from_filename(filename: str) -> str:
    """Extracts the Series name from the filename."""
    upper_name = filename.upper()
    # Sort keys by length descending to match specific prefixes first (e.g. "TITAN" before "TI")
    sorted_keys = sorted(SERIES_MAPPING.keys(), key=len, reverse=True)

    for prefix in sorted_keys:
        # Case insensitive check for keys like "faqs"
        if prefix.upper() in upper_name:
            return SERIES_MAPPING[prefix]
    return "OTHER" # Fallback

def get_available_series() -> List[str]:
    """Returns a list of available series from loaded shards, Title Case formatted."""
    series_set = set()
    for summary in global_state.azure_shard_summaries:
        # Extract series from "SERIES: XXX\nFILES: ..."
        if summary.startswith("SERIES: "):
            series_name = summary.split("\n")[0].replace("SERIES: ", "").strip()
            # Exclude FAQS and OTHER from user-facing list
            if series_name not in ("FAQS", "OTHER"):
                series_set.add(series_name.title())
    return sorted(list(series_set))

def find_shards_by_series(series_name: str) -> List[int]:
    """Returns indices of shards that match the given series name (case-insensitive)."""
    indices = []
    series_upper = series_name.upper()
    for i, summary in enumerate(global_state.azure_shard_summaries):
        if summary.startswith("SERIES: "):
            shard_series = summary.split("\n")[0].replace("SERIES: ", "").strip().upper()
            if shard_series == series_upper:
                indices.append(i)
    return indices

@app.post("/ingest", response_model=IngestResponse)
async def ingest_knowledge_base():
    """
    Manually triggers re-ingestion of knowledge base.
    Useful for refreshing cache after adding new documents.
    NOTE: This runs automatically at startup - only call manually to refresh.
    """
    kb_dir = "./knowledge_base"
    md_files = glob.glob(os.path.join(kb_dir, "*.md"))

    success = await ingest_knowledge_base_internal()

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest knowledge base. Check server logs."
        )

    # Calculate stats for response
    encoding = tiktoken.get_encoding("cl100k_base")
    total_tokens = sum(len(encoding.encode(s)) for s in global_state.azure_shards)
    total_chars = sum(len(s) for s in global_state.azure_shards)

    return IngestResponse(
        message="Knowledge base re-ingested and cache updated.",
        shard_names=[f"shard_{i}" for i in range(len(global_state.azure_shards))],
        document_count=len(md_files),
        total_chars=total_chars,
        total_tokens=total_tokens,
        shards_created=len(global_state.azure_shards)
    )

async def query_azure_shard(shard_content: str, question: str, history_str: str = "") -> dict:
    """Helper function to query a single Azure shard. Returns dict with answer and sources."""
    if not azure_client:
        return {"answer": "Azure Client not configured.", "sources": []}
        
    try:
        # Construct messages. The long context (shard_content) goes first to trigger caching.
        prompt_content = f"""Context information is below.
---------------------
{shard_content}
---------------------
"""
        if history_str:
            prompt_content += f"""Conversation History:
{history_str}
"""

        prompt_content += f"""Given the context information and history, answer the query.

CRITICAL CONTEXT INSTRUCTION:
If the 'Query' is short or ambiguous (e.g., just a model name like "Flex-C"), you MUST interpret it as a follow-up to the 'Conversation History'.
Example: If History is "Why does it smell bad?" and Query is "Flex-C", you must treat the query as "Why does Flex-C smell bad?" and answer that specific question using the context. Do NOT simply repeat the interpreted question.

Query: {question}

INSTRUCTIONS:
1. RULE #1: Do NOT assume information that is not within the current context.
2. Answer the question in Spanish.
3. Identify the specific documents and pages used to answer (look for headers like '## DOCUMENT - Página X').
4. For each page cited, extract the EXACT text snippet that supports your answer.
   - **CRITICAL:** Do NOT return document headers, titles, or model names unless they contain the specific answer.
   - If the answer is in a table, extract the specific ROW containing the key and value (e.g., "Compressor Type | Rotary").
   - The excerpt MUST contain the specific value you used in your answer.
5. If the information is NOT present in the context, return "answer": "NOT_FOUND" and empty sources.
6. Do NOT return the interpreted question as the answer. If you cannot find the answer, return "NOT_FOUND".
7. Return ONLY a JSON object with the following format:
{{
  "answer": "Your answer here... (or 'NOT_FOUND')",
  "sources": [
    {{
      "reference": "Document Name - Página X",
      "excerpt": "Exact text and current context from the document that proves the answer... (max 100 tokens)"
    }}
  ]
}}
"""

        messages = [
            {
                "role": "user", 
                "content": prompt_content
            }
        ]
        
        # GPT-5 models don't support temperature=0.0, use default (1.0)
        temp = 1.0 if AZURE_DEPLOYMENT_NAME.lower().startswith("gpt-5") else 0.0
        
        response = await azure_client.chat.completions.create(
            model=AZURE_DEPLOYMENT_NAME,
            messages=messages,
            temperature=temp,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        import json
        return json.loads(content)
    except Exception as e:
        logger.error(f"Error querying Azure shard: {e}")
        return {"answer": "", "sources": []}

async def is_valid_question(text: str) -> bool:
    """
    Classifies if the input is a valid standalone question or a conversational reply.
    Returns True if it's a question, False if it's likely a reply (e.g., "Yes", "Flex-C").
    """
    if not azure_client: return False
    try:
        temp = 1.0 if AZURE_DEPLOYMENT_NAME.lower().startswith("gpt-5") else 0.0
        response = await azure_client.chat.completions.create(
            model=AZURE_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Classify if the user input is a valid question/request or just a short reply/confirmation. Return JSON: {\"is_question\": true/false}"},
                {"role": "user", "content": text}
            ],
            temperature=temp,
            response_format={"type": "json_object"}
        )
        import json
        result = json.loads(response.choices[0].message.content)
        return result.get("is_question", False)
    except Exception as e:
        logger.error(f"Error in input classifier: {e}")
        return True # Fallback to treating as question

@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Answers a question using Azure OpenAI with Map-Reduce over in-memory shards.
    """
    if not global_state.azure_shards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge Base not loaded. Please call /ingest first."
        )
    
    if not azure_client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Azure OpenAI client not initialized. Check environment variables."
        )

    try:
        # --- SESSION MANAGEMENT ---
        session_id = request.session_id or "default"
        if session_id not in global_state.sessions:
            global_state.sessions[session_id] = []
            
        # Add user question to history
        global_state.sessions[session_id].append({"role": "user", "content": request.question})
        
        # Keep history short (last 6 messages = 3 turns) to save tokens
        history = global_state.sessions[session_id][-6:]
        
        # Prepare history string for prompt
        history_str = ""
        for msg in history[:-1]: # Exclude the current question which is added separately
            history_str += f"{msg['role'].upper()}: {msg['content']}\n"

        # --- PRE-ROUTER FAQS CHECK ---
        # Step 1: Classify Input
        is_question = await is_valid_question(request.question)
        logger.info(f"Input Classifier: '{request.question}' -> is_question={is_question}")

        # Step 2: Check FAQS if it is a question
        if is_question:
            faqs_index = -1
            for i, summary in enumerate(global_state.azure_shard_summaries):
                if summary.startswith("SERIES: FAQS"):
                    faqs_index = i
                    break
            
            if faqs_index != -1:
                logger.info("Pre-Router: Checking FAQS shard...")
                # Query ONLY FAQS
                faqs_response = await query_azure_shard(global_state.azure_shards[faqs_index], request.question, history_str)
                
                if faqs_response.get("answer") != "NOT_FOUND" and faqs_response.get("answer", "").strip():
                    logger.info("Pre-Router: Answer found in FAQS. Returning immediately.")
                    # Add to history
                    global_state.sessions[session_id].append({"role": "assistant", "content": faqs_response["answer"]})
                    
                    # Process sources for FAQS response
                    source_map = {}
                    seen_references = set()
                    for src in faqs_response.get("sources", []):
                        ref = src.get("reference", "")
                        excerpt = src.get("excerpt", "")
                        if ref in seen_references: continue
                        seen_references.add(ref)
                        
                        if " - Página" in ref:
                            doc_part = ref.split(" - Página")[0]
                        else:
                            doc_part = ref
                        doc_name = doc_part.strip()
                        if doc_name.endswith('.'): doc_name = doc_name[:-1]
                        file_name = doc_name

                        if file_name not in source_map: source_map[file_name] = []
                        source_map[file_name].append(PageDetail(reference=ref, excerpt=excerpt))
                    
                    final_sources = [SourceItem(file=f, pages=d) for f, d in source_map.items()]
                    return AskResponse(answer=faqs_response["answer"], sources=final_sources)
                else:
                    logger.info("Pre-Router: No relevant answer in FAQS. Proceeding to Router.")

        # --- SERIES BYPASS ---
        # If frontend provides series parameter, skip router and search directly
        search_query = request.question
        valid_indices = []

        if request.series:
            logger.info(f"Series bypass: Searching directly in series '{request.series}'")
            series_indices = find_shards_by_series(request.series)

            if not series_indices:
                logger.warning(f"Series '{request.series}' not found. Fallback to all shards.")
                valid_indices = list(range(len(global_state.azure_shards)))
            else:
                valid_indices = series_indices
        else:
            # --- AGENTIC ROUTING PHASE ---
            logger.info(f"Agentic Router: Analyzing request for session '{session_id}'...")

            # Create a prompt with all summaries
            router_context = ""
            for i, summary in enumerate(global_state.azure_shard_summaries):
                router_context += f"SHARD_ID {i}: {summary}\n\n"

            router_prompt = f"""
            You are an intelligent router for a technical support RAG system for Air Conditioners.

            Available Shards (grouped by Series):
            {router_context}

            Conversation History:
            {history_str}

            Current User Question: "{request.question}"

            Task: Decide the next action.

            Rules:
            1. **Search:** If the user mentions a Series/Model, OR if the Conversation History provides the Series/Model context.
               - **CRITICAL:** You must generate a `search_query` that combines the *original intent* from the history with the *new context*.
               - **CLARIFICATION REPLY:** If the user input is just a Series Name (e.g., "Virtus", "Flex-C") and the previous system message asked for clarification, you **MUST** copy the *EXACT, LITERAL* wording of the preceding user question and append the Series Name. Do NOT summarize, paraphrase, or omit ANY part of the original question (including phrases like "antes de que se detenga por protección", "before it stops", etc.).
               - **EXACT MATCHING:** If the user mentions a specific subseries (e.g., "FLEX-C", "AFLEX-C"), select ONLY shards for that exact subseries (FLEX-C), NOT related subseries (FLEX-T, FLEX-S).
               - **Example 1 (Contextual):**
                 - History: User: "¿Error E9?", Assistant: "¿Qué modelo?"
                 - Current Input: "Aflex"
                 - **Output:** `{{"action": "search", "shards": [...], "search_query": "Significado del error E9 en la serie Aflex"}}` (Do NOT just search for "Aflex")
               - **Example 2 (Clarification Reply - Complex):**
                 - History: User: "¿Cuál es la temperatura máxima en modo Refrigeración para un modelo T1 antes de que se detenga por protección?", Assistant: "¿Qué serie?"
                 - Current Input: "VIRTUS"
                 - **Output:** `{{"action": "search", "shards": [...], "search_query": "¿Cuál es la temperatura máxima en modo Refrigeración para un modelo T1 antes de que se detenga por protección? Serie VIRTUS"}}` (CRITICAL: EXACT copy of original question + series name)
            2. **Clarify:** ONLY if the question is about **Technical Specifications** or **Model-Specific Data** AND the History does NOT clarify which Series/Model.
               - **Examples of when to CLARIFY:**
                 - "What is the cooling capacity?" (Varies by model)
                 - "What is the max current?" (Varies by model)
                 - "What voltage does it use?" (Varies by model)
                 - "Error E6" (Meaning might vary significantly between series)
                 - "Max temperature in Cooling mode?" (Operational limit)
            3. **Generic/Search:** If the question is about **Troubleshooting**, **Usage**, **General Inquiries**, or **Recommendations**.
               - **Examples of when to SEARCH (Do NOT clarify):**
                 - "My AC smells bad." (Common issue)
                 - "Unit making strange noise." (Common issue)
                 - "How to use Sleep Mode?" (Usage)
                 - "Remote not working." (Troubleshooting)
                 - "Where to find large capacity units?" (Recommendation)
               - **Action:** Select ALL relevant shards (or all shards if unsure) to search across the entire knowledge base.
               - **Output:** `{{"action": "search", "shards": [0, 1, 2, ...], "search_query": "Original Question"}}`

            Output JSON format:
            - If searching: {{"action": "search", "shards": [0, 2], "search_query": "Full contextualized question"}}
            - If clarifying: {{"action": "clarify"}}
            """

            # GPT-5 models don't support temperature=0.0, use default (1.0)
            temp = 1.0 if AZURE_DEPLOYMENT_NAME.lower().startswith("gpt-5") else 0.0

            router_response = await azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a precise routing assistant. Output only JSON."},
                    {"role": "user", "content": router_prompt}
                ],
                temperature=temp
            )

            router_output = {}
            try:
                import json
                content = router_response.choices[0].message.content
                # Clean up potential markdown code blocks
                if "```" in content:
                    content = content.split("```")[1].replace("json", "").strip()
                router_output = json.loads(content)
                logger.info(f"Router decision: {router_output}")
            except Exception as e:
                logger.error(f"Router parsing failed: {e}. Fallback to search all.")
                router_output = {"action": "search", "shards": list(range(len(global_state.azure_shards))), "search_query": request.question}

            # --- ACTION HANDLING ---

            if router_output.get("action") == "clarify":
                # Return structured clarification response
                available = get_available_series()
                return AskResponse(
                    answer="",
                    sources=[],
                    needs_clarification=True,
                    available_series=available
                )

            # If action is search (or fallback)
            selected_indices = router_output.get("shards", [])
            search_query = router_output.get("search_query", request.question) # Use rewritten query

            logger.info(f"Executing Search with Query: '{search_query}' on shards {selected_indices}")

            # Validate indices
            valid_indices = [i for i in selected_indices if 0 <= i < len(global_state.azure_shards)]

            if not valid_indices:
                logger.warning("No valid shards selected by router. Fallback to all.")
                valid_indices = list(range(len(global_state.azure_shards)))

        # --- MAP PHASE (Selected Shards Only) ---
        logger.info(f"Querying {len(valid_indices)} selected Azure shards in parallel...")
        tasks = [query_azure_shard(global_state.azure_shards[i], search_query) for i in valid_indices]
        shard_responses = await asyncio.gather(*tasks)
        
        # shard_responses is now a list of dicts: [{"answer": "...", "sources": [...]}, ...]
        valid_responses = [r for r in shard_responses if r.get("answer") != "NOT_FOUND" and r.get("answer", "").strip()]

        if not valid_responses:
            msg = "No pude encontrar información relevante en la base de conocimientos."
            global_state.sessions[session_id].append({"role": "assistant", "content": msg})
            return AskResponse(answer=msg, sources=[])

        # Collect all sources
        all_sources = []
        for r in valid_responses:
            all_sources.extend(r.get("sources", []))
        
        # Group sources by file
        source_map = {}
        seen_references = set()
        
        for src in all_sources:
            # src is now {"reference": "...", "excerpt": "..."}
            ref = src.get("reference", "")
            excerpt = src.get("excerpt", "")
            
            # Skip if we've already seen this exact reference (page)
            if ref in seen_references:
                continue
            seen_references.add(ref)
            
            # Assume format "DocName - Página X"
            if " - Página" in ref:
                doc_part = ref.split(" - Página")[0]
            else:
                doc_part = ref

            # Clean doc_part (remove trailing dot if present)
            doc_name = doc_part.strip()
            if doc_name.endswith('.'):
                doc_name = doc_name[:-1]

            file_name = doc_name

            if file_name not in source_map:
                source_map[file_name] = []
            source_map[file_name].append(PageDetail(reference=ref, excerpt=excerpt))
        
        final_sources = [SourceItem(file=f, pages=d) for f, d in source_map.items()]

        # REDUCE PHASE
        final_answer = ""
        if len(valid_responses) == 1:
            final_answer = valid_responses[0]["answer"]
        else:
            logger.info("Synthesizing Azure responses...")
            
            synthesis_prompt = f"""
            The user asked: "{request.question}"
            
            Here are partial answers found in different sections of the knowledge base:
            
            {''.join([f'--- PARTIAL ANSWER {i+1} ---\n{resp["answer"]}\n\n' for i, resp in enumerate(valid_responses)])}
            
            Please synthesize a single, coherent, and complete answer based on these partial responses. 
            Ignore any "I don't know" or irrelevant parts if better information is available in other partial answers.
            RESPONDE SIEMPRE EN ESPAÑOL.
            RULE #1: Do NOT assume information that is not within the partial responses.
            """
            
            final_response = await azure_client.chat.completions.create(
                model=AZURE_DEPLOYMENT_NAME,
                messages=[{"role": "user", "content": synthesis_prompt}],
            )
            final_answer = final_response.choices[0].message.content

        # Add final answer to history
        global_state.sessions[session_id].append({"role": "assistant", "content": final_answer})
        return AskResponse(answer=final_answer, sources=final_sources)

    except Exception as e:
        logger.error(f"Error generating Azure response: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating response: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
