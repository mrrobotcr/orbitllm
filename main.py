import os
import glob
import datetime
import logging
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
from google.generativeai import caching
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
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_DEPLOYMENT_NAME = os.getenv("AZURE_DEPLOYMENT_NAME", "gpt-4o-mini") # Default or from env

if not GOOGLE_API_KEY:
    logger.warning("GOOGLE_API_KEY not found in environment variables.")

if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
    logger.warning("Azure OpenAI credentials not found in environment variables.")

# Configure Gemini
genai.configure(api_key=GOOGLE_API_KEY)

# Configure Azure OpenAI
azure_client = None
if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
    azure_client = AsyncOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        base_url=AZURE_OPENAI_ENDPOINT
    )

import asyncio

# ... (imports remain the same, ensure asyncio is imported)

# Global state for cache names
class GlobalState:
    _instance = None
    cache_names: List[str] = []
    cache_names: List[str] = []
    cache_names: List[str] = []
    azure_shards: List[str] = [] # Store content in memory for Azure (Implicit Caching)
    azure_shard_summaries: List[str] = [] # Store summaries for Agentic Routing
    sessions: dict = {} # Store session history: {session_id: [{"role": "user", "content": "..."}]}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
        return cls._instance

global_state = GlobalState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic can go here if needed
    logger.info("Server starting up...")
    yield
    # Shutdown logic
    logger.info("Server shutting down...")

app = FastAPI(title="OrbitLLM Backend", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# --- Pydantic Models ---

class IngestResponse(BaseModel):
    message: str
    cache_names: List[str]
    document_count: int
    total_chars: int
    total_tokens: int
    shards_created: int

class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

class PageDetail(BaseModel):
    reference: str
    excerpt: str

class SourceItem(BaseModel):
    file: str
    pages: List[PageDetail]

class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem] = []

# --- Endpoints ---

@app.post("/ingest", response_model=IngestResponse)
async def ingest_knowledge_base():
    """
    Reads all .md files, shards them if necessary, and creates multiple Google Context Caches.
    """
    kb_dir = "./knowledge_base"
    if not os.path.exists(kb_dir):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Directory '{kb_dir}' not found.")

    md_files = glob.glob(os.path.join(kb_dir, "*.md"))
    if not md_files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No .md files found in '{kb_dir}'.")

    model_name = 'models/gemini-2.5-flash-lite'
    # Use a separate model instance for token counting to avoid confusion
    count_model = genai.GenerativeModel(model_name)
    
    # Constants
    # REDUCED LIMIT: 100k tokens to target sub-15s latency.
    MAX_TOKENS_PER_SHARD = 100000 
    
    shards = []
    current_shard_content = ""
    current_shard_tokens = 0
    total_tokens_processed = 0
    total_chars_processed = 0
    
    logger.info(f"Starting ingestion of {len(md_files)} files...")

    for file_path in md_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                filename = os.path.basename(file_path)
                formatted_content = f"\n\n--- DOCUMENTO: {filename} ---\n\n{content}"
                
                # Count tokens for this file
                # Note: This might add latency. For production, consider estimating or batching.
                file_token_count = count_model.count_tokens(formatted_content).total_tokens
                
                if current_shard_tokens + file_token_count > MAX_TOKENS_PER_SHARD:
                    # Current shard is full, push it and start a new one
                    if current_shard_content:
                        shards.append(current_shard_content)
                    
                    current_shard_content = formatted_content
                    current_shard_tokens = file_token_count
                else:
                    # Add to current shard
                    current_shard_content += formatted_content
                    current_shard_tokens += file_token_count
                
                total_tokens_processed += file_token_count
                total_chars_processed += len(formatted_content)

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")

    # Add the last shard if it has content
    if current_shard_content:
        shards.append(current_shard_content)

    if not shards:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No content to cache.")

    # Create caches for each shard
    created_caches = []
    try:
        for i, shard_content in enumerate(shards):
            logger.info(f"Creating cache for shard {i+1}/{len(shards)}...")
            cache = caching.CachedContent.create(
                model=model_name,
                display_name=f'knowledge_base_v1_shard_{i}',
                system_instruction=(
                    "You are an expert assistant. Use the provided context to answer questions accurately. "
                    "RULE #1: Do NOT assume information that is not within the current context."
                ),
                contents=[shard_content],
                ttl=datetime.timedelta(minutes=60),
            )
            created_caches.append(cache.name)
            logger.info(f"Shard {i+1} cached: {cache.name}")

        # Update global state
        global_state.cache_names = created_caches

        return IngestResponse(
            message="Knowledge base ingested and cached successfully.",
            cache_names=created_caches,
            document_count=len(md_files),
            total_chars=total_chars_processed,
            total_tokens=total_tokens_processed,
            shards_created=len(created_caches)
        )

    except Exception as e:
        logger.error(f"Failed to create cache: {e}")
        # In a real scenario, we might want to cleanup created caches here
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create cache: {str(e)}")

async def query_shard(cache_name: str, question: str) -> str:
    """Helper function to query a single cache shard."""
    try:
        model = genai.GenerativeModel.from_cached_content(
            cached_content=caching.CachedContent(name=cache_name)
        )
        response = await model.generate_content_async(
            question,
            generation_config=genai.GenerationConfig(temperature=0.2)
        )
        return response.text
    except Exception as e:
        logger.error(f"Error querying shard {cache_name}: {e}")
        return ""

@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Answers a question using Map-Reduce over multiple cached shards.
    """
    if not global_state.cache_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Knowledge Base not loaded. Please call /ingest first."
        )

    try:
        # MAP PHASE: Query all shards in parallel
        logger.info(f"Querying {len(global_state.cache_names)} shards...")
        tasks = [query_shard(name, request.question) for name in global_state.cache_names]
        shard_responses = await asyncio.gather(*tasks)
        
        # Filter out empty responses
        valid_responses = [r for r in shard_responses if r.strip()]

        if not valid_responses:
            return AskResponse(answer="I could not find any relevant information in the knowledge base.")

        # REDUCE PHASE: Synthesize if multiple responses, or just return if one
        if len(valid_responses) == 1:
            return AskResponse(answer=valid_responses[0])
        
        logger.info("Synthesizing responses from multiple shards...")
        # Use a standard model (no cache) for synthesis
        synthesis_model = genai.GenerativeModel('models/gemini-2.5-flash-lite')
        
        synthesis_prompt = f"""
        The user asked: "{request.question}"
        
        Here are partial answers found in different sections of the knowledge base:
        
        {''.join([f'--- PARTIAL ANSWER {i+1} ---\n{resp}\n\n' for i, resp in enumerate(valid_responses)])}
        
        Please synthesize a single, coherent, and complete answer based on these partial responses. 
        Ignore any "I don't know" or irrelevant parts if better information is available in other partial answers.
        RESPONDE SIEMPRE EN ESPAÑOL.
        RULE #1: Do NOT assume information that is not within the partial responses.
        """
        
        final_response = await synthesis_model.generate_content_async(
            synthesis_prompt,
            generation_config=genai.GenerationConfig(temperature=0.2)
        )

        return AskResponse(answer=final_response.text)

    except Exception as e:
        logger.error(f"Error generating response: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating response: {str(e)}"
        )

# --- Azure Endpoints ---

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

@app.post("/ingest/azure", response_model=IngestResponse)
async def ingest_knowledge_base_azure():
    """
    Reads all .md files, shards them (<100k tokens), and stores them in memory for Azure Implicit Caching.
    Uses Semantic Sharding (grouping by Series) and Metadata Summaries for Agentic Routing.
    """
    kb_dir = "./knowledge_base"
    if not os.path.exists(kb_dir):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Directory '{kb_dir}' not found.")

    md_files = glob.glob(os.path.join(kb_dir, "*.md"))
    if not md_files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No .md files found in '{kb_dir}'.")

    # Constants for Azure
    # REDUCED LIMIT: 100k tokens to fit within gpt-4o-mini's 128k context window
    # and maximize parallelism with 2M TPM quota.
    MAX_TOKENS_PER_SHARD = 100000 
    encoding = tiktoken.get_encoding("cl100k_base") # Standard for GPT-4/3.5
    
    shards = []
    current_shard_content = ""
    current_shard_tokens = 0
    total_tokens_processed = 0
    total_chars_processed = 0
    
    summaries = [] # To store summaries
    
    logger.info(f"Starting Azure ingestion of {len(md_files)} files with Semantic Sharding...")

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
                        # Series shard full, save it
                        if current_series_content:
                            shards.append(current_series_content)
                            # Create Metadata Summary (Instant)
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

        # Add remaining content for this series
        if current_series_content:
            shards.append(current_series_content)
            summary = f"SERIES: {series}\nFILES: {', '.join(current_series_filenames)}"
            summaries.append(summary)

    if not shards:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No content to cache.")

    # Store shards and summaries in global state
    global_state.azure_shards = shards
    global_state.azure_shard_summaries = summaries
    
    logger.info(f"Azure ingestion complete. {len(shards)} shards created.")

    return IngestResponse(
        message="Knowledge base ingested for Azure successfully.",
        cache_names=[f"azure_shard_{i}" for i in range(len(shards))], # Virtual names
        document_count=len(md_files),
        total_chars=total_chars_processed,
        total_tokens=total_tokens_processed,
        shards_created=len(shards)
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
        response = await azure_client.chat.completions.create(
            model=AZURE_DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "Classify if the user input is a valid question/request or just a short reply/confirmation. Return JSON: {\"is_question\": true/false}"},
                {"role": "user", "content": text}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        import json
        result = json.loads(response.choices[0].message.content)
        return result.get("is_question", False)
    except Exception as e:
        logger.error(f"Error in input classifier: {e}")
        return True # Fallback to treating as question

@app.post("/ask/azure", response_model=AskResponse)
async def ask_question_azure(request: AskRequest):
    """
    Answers a question using Azure OpenAI with Map-Reduce over in-memory shards.
    """
    if not global_state.azure_shards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Azure Knowledge Base not loaded. Please call /ingest/azure first."
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
                        file_name = f"{doc_name}.pdf"
                        
                        if file_name not in source_map: source_map[file_name] = []
                        source_map[file_name].append(PageDetail(reference=ref, excerpt=excerpt))
                    
                    final_sources = [SourceItem(file=f, pages=d) for f, d in source_map.items()]
                    return AskResponse(answer=faqs_response["answer"], sources=final_sources)
                else:
                    logger.info("Pre-Router: No relevant answer in FAQS. Proceeding to Router.")

        # --- FAQS FIRST STRATEGY REMOVED ---
        # We now include FAQS shard dynamically in the search phase below.


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
           - **EXACT MATCHING:** If the user mentions a specific subseries (e.g., "FLEX-C", "AFLEX-C"), select ONLY shards for that exact subseries (FLEX-C), NOT related subseries (FLEX-T, FLEX-S).
           - **Example:** 
             - History: User: "¿Error E9?", Assistant: "¿Qué modelo?"
             - Current Input: "Aflex"
             - **Output:** `{{"action": "search", "shards": [...], "search_query": "Significado del error E9 en la serie Aflex"}}` (Do NOT just search for "Aflex")
        2. **Clarify:** ONLY if the question is about **Technical Specifications** or **Model-Specific Data** AND the History does NOT clarify which Series/Model.
           - **Examples of when to CLARIFY:**
             - "What is the cooling capacity?" (Varies by model)
             - "What is the max current?" (Varies by model)
             - "What voltage does it use?" (Varies by model)
             - "Error E6" (Meaning might vary significantly between series)
             - "Max temperature in Cooling mode?" (Operational limit)
           - **IMPORTANT:** In your message, list the available Series found in the Shards context to help the user.
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
        - If clarifying: {{"action": "clarify", "message": "Para poder ayudarte mejor, ¿podrías especificar la Serie o el Modelo de tu equipo? Las series disponibles son: GOLD, FREEDOM, ALEF, etc."}}
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
            clarification_msg = router_output.get("message", "¿Podrías especificar el modelo?")
            # Add assistant response to history
            global_state.sessions[session_id].append({"role": "assistant", "content": clarification_msg})
            return AskResponse(answer=clarification_msg)

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
                
            file_name = f"{doc_name}.pdf"
            
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
