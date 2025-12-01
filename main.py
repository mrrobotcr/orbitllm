import os
import glob
import datetime
import logging
from typing import Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
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
    azure_shards: List[str] = [] # Store content in memory for Azure (Implicit Caching)

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

class AskResponse(BaseModel):
    answer: str

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
                    "You are an expert assistant. Use the provided context to answer questions accurately."
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

@app.post("/ingest/azure", response_model=IngestResponse)
async def ingest_knowledge_base_azure():
    """
    Reads all .md files, shards them (<400k tokens), and stores them in memory for Azure Implicit Caching.
    """
    kb_dir = "./knowledge_base"
    if not os.path.exists(kb_dir):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Directory '{kb_dir}' not found.")

    md_files = glob.glob(os.path.join(kb_dir, "*.md"))
    if not md_files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"No .md files found in '{kb_dir}'.")

    # Constants for Azure
    # REDUCED LIMIT: 250k tokens based on error message (limit is ~272k).
    MAX_TOKENS_PER_SHARD = 400000 
    encoding = tiktoken.get_encoding("cl100k_base") # Standard for GPT-4/3.5
    
    shards = []
    current_shard_content = ""
    current_shard_tokens = 0
    total_tokens_processed = 0
    total_chars_processed = 0
    
    logger.info(f"Starting Azure ingestion of {len(md_files)} files...")

    for file_path in md_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                filename = os.path.basename(file_path)
                formatted_content = f"\n\n--- DOCUMENTO: {filename} ---\n\n{content}"
                
                # Count tokens using tiktoken
                file_tokens = len(encoding.encode(formatted_content))
                
                if current_shard_tokens + file_tokens > MAX_TOKENS_PER_SHARD:
                    # Current shard is full
                    if current_shard_content:
                        shards.append(current_shard_content)
                    
                    current_shard_content = formatted_content
                    current_shard_tokens = file_tokens
                else:
                    current_shard_content += formatted_content
                    current_shard_tokens += file_tokens
                
                total_tokens_processed += file_tokens
                total_chars_processed += len(formatted_content)

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")

    if current_shard_content:
        shards.append(current_shard_content)

    if not shards:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No content to cache.")

    # Store shards in global state
    global_state.azure_shards = shards
    logger.info(f"Azure ingestion complete. {len(shards)} shards created.")

    return IngestResponse(
        message="Knowledge base ingested for Azure successfully.",
        cache_names=[f"azure_shard_{i}" for i in range(len(shards))], # Virtual names
        document_count=len(md_files),
        total_chars=total_chars_processed,
        total_tokens=total_tokens_processed,
        shards_created=len(shards)
    )

async def query_azure_shard(shard_content: str, question: str) -> str:
    """Helper function to query a single Azure shard."""
    if not azure_client:
        return "Azure Client not configured."
        
    try:
        # Construct messages. The long context (shard_content) goes first to trigger caching.
        messages = [
            {
                "role": "user", 
                "content": f"Context information is below.\n---------------------\n{shard_content}\n---------------------\nGiven the context information and not prior knowledge, answer the query.\nQuery: {question}\nAnswer:"
            }
        ]
        
        response = await azure_client.chat.completions.create(
            model=AZURE_DEPLOYMENT_NAME,
            messages=messages,
            temperature=1 # Low temp for factual answers
        )
        
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error querying Azure shard: {e}")
        return ""

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
        # MAP PHASE: Query shards in parallel (TPM increased to 1M)
        logger.info(f"Querying {len(global_state.azure_shards)} Azure shards in parallel...")
        tasks = [query_azure_shard(shard, request.question) for shard in global_state.azure_shards]
        shard_responses = await asyncio.gather(*tasks)
        
        valid_responses = [r for r in shard_responses if r.strip()]

        if not valid_responses:
            return AskResponse(answer="I could not find any relevant information in the knowledge base.")

        # REDUCE PHASE
        if len(valid_responses) == 1:
            return AskResponse(answer=valid_responses[0])
        
        logger.info("Synthesizing Azure responses...")
        
        synthesis_prompt = f"""
        The user asked: "{request.question}"
        
        Here are partial answers found in different sections of the knowledge base:
        
        {''.join([f'--- PARTIAL ANSWER {i+1} ---\n{resp}\n\n' for i, resp in enumerate(valid_responses)])}
        
        Please synthesize a single, coherent, and complete answer based on these partial responses. 
        Ignore any "I don't know" or irrelevant parts if better information is available in other partial answers.
        """
        
        final_response = await azure_client.chat.completions.create(
            model=AZURE_DEPLOYMENT_NAME,
            messages=[{"role": "user", "content": synthesis_prompt}],
        )

        return AskResponse(answer=final_response.choices[0].message.content)

    except Exception as e:
        logger.error(f"Error generating Azure response: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating response: {str(e)}"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
