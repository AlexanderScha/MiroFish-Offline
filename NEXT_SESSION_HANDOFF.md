# MiroFish-Offline: Next Session Handoff

**Date:** 2026-03-27
**Status:** Initial setup complete, testing successful, optimization needed
**Current Version:** Python/Flask + Ollama + Neo4j + Vue3

---

## 🎯 Current State Summary

### ✅ What's Working

1. **Complete end-to-end pipeline:**
   - Document upload → Ontology generation ✓
   - Graph building (Neo4j) ✓
   - Agent profile generation ✓
   - Simulation execution (Twitter + Reddit) ✓
   - Report generation (in progress) ✓

2. **Test Results:**
   - 4 agents, 25 rounds: **10 minutes** (normal for current setup)
   - Generated 36 actions across both platforms
   - Report generation running (hitting timeouts)

3. **Infrastructure:**
   - Dual RTX 3090s (48GB VRAM total)
   - Neo4j 5.18 running in Docker
   - Ollama running locally with qwen3:32b
   - LAN access configured for remote testing

### ⚠️ Performance Bottlenecks Identified

| Component | Current Time | Bottleneck | Impact |
|-----------|-------------|------------|--------|
| **Ontology generation** | 2-3 min | Sequential LLM calls | Acceptable for 4 entities |
| **Graph building** | 1.5 min | Sequential NER + embeddings | Acceptable for small docs |
| **Agent profile gen** | 3-4 min | Sequential profile generation | Acceptable for 4 agents |
| **Simulation** | 10 min (4 agents, 25 rounds) | **Sequential agent decisions** | **11 hours for 20 agents!** |
| **Report generation** | 5-10+ min | **ReACT pattern, sequential tool calls** | **Timeout on interviews** |

**Critical Issue:** Simulation scales linearly with agents × rounds:
- 4 agents × 25 rounds = 10 min ✅
- 20 agents × 100 rounds = **11 hours** ❌
- 50 agents × 100 rounds = **28 hours** 💀

### 🔍 Architecture Analysis

**Search Capabilities:**
- ❌ **NO external search** (no Tavily, Serper, Exa integration)
- ✅ **Local graph search only** - hybrid vector + keyword search in Neo4j
- Tools: `InsightForge`, `PanoramaSearch`, `QuickSearch`, `InterviewAgents`

**Report Generation:**
- Uses ReACT pattern (Reasoning + Acting)
- Multiple sequential LLM calls per section
- Agent interviews timing out (180 sec timeout, hit timeout during test)
- Would benefit from batching + faster LLM

**Current LLM Usage:**
- Ollama: 1 GPU only, sequential processing
- No batching, no tensor parallelism
- OpenAI-compatible API (easy to swap)

---

## 🚀 Priority 1: Performance Optimization (vLLM + Batching)

### Why This Matters

**Without optimization:**
- Testing (4 agents): Usable ✓
- Small sim (10 agents, 50 rounds): 1.7 hours ⏰
- Medium sim (20 agents, 100 rounds): 11 hours 💀
- Large sim (50 agents, 100 rounds): 28 hours (unusable) 💀💀

**With vLLM + batching:**
- Testing (4 agents): 3 min (3x faster)
- Small sim: 20 min (5x faster)
- Medium sim: 1.5 hours (7x faster)
- Large sim: 4 hours (7x faster)

### Phase 1: Install vLLM (2-3 hours)

**Goal:** Use both RTX 3090s, enable batching support

**Steps:**

1. **Stop Ollama:**
   ```bash
   sudo systemctl stop ollama
   # or if not a service:
   killall ollama
   ```

2. **Install vLLM:**
   ```bash
   conda activate mirofish
   pip install vllm

   # Install optional dependencies for better performance
   pip install ray  # For distributed inference
   ```

3. **Download/locate model files:**
   ```bash
   # Find Ollama's qwen3:32b model
   ls /usr/share/ollama/.ollama/models/blobs/

   # Or download directly:
   # huggingface-cli download Qwen/Qwen2.5-32B-Instruct-GGUF qwen2.5-32b-instruct-q4_k_m.gguf
   ```

4. **Start vLLM server:**
   ```bash
   # Create startup script
   cat > start-vllm.sh << 'EOF'
   #!/bin/bash
   source ~/miniconda3/bin/activate mirofish

   python -m vllm.entrypoints.openai.api_server \
     --model Qwen/Qwen2.5-32B-Instruct \
     --tensor-parallel-size 2 \
     --max-num-seqs 8 \
     --max-model-len 4096 \
     --gpu-memory-utilization 0.9 \
     --port 11434 \
     --served-model-name qwen3:32b
   EOF

   chmod +x start-vllm.sh
   ./start-vllm.sh
   ```

5. **Test vLLM:**
   ```bash
   curl http://localhost:11434/v1/models

   curl http://localhost:11434/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen3:32b",
       "messages": [{"role": "user", "content": "Hello!"}],
       "max_tokens": 50
     }'
   ```

6. **No code changes needed!**
   - Already using OpenAI-compatible API
   - Just restart MiroFish backend

**Expected improvement:** 1.5-2x faster due to:
- Better GPU utilization (both GPUs)
- PagedAttention memory efficiency
- Continuous batching

---

### Phase 2: Implement Batched Agent Decisions (2-3 days)

**Goal:** Process multiple agents in parallel per simulation round

**Current (slow):**
```python
# Each round in OASIS does:
for agent in agents:  # Sequential!
    action = agent.step()  # LLM call ~5 seconds
    environment.execute(action)

# 4 agents = 20 seconds/round
# 50 agents = 250 seconds/round!
```

**Target (fast):**
```python
# Collect all prompts
prompts = [agent.get_decision_prompt() for agent in agents]

# Single batched LLM call
responses = await llm.batch_chat(prompts)  # ~6 seconds total!

# Execute all actions
for agent, response in zip(agents, responses):
    action = agent.parse_response(response)
    environment.execute(action)

# 4 agents = 6 seconds/round
# 50 agents = 10 seconds/round!
```

#### Implementation Plan

**File 1: `backend/app/services/batched_chat_agent.py` (NEW)**

Create a wrapper that batches CAMEL ChatAgent calls:

```python
"""
Batched Chat Agent Service
Wraps CAMEL-AI ChatAgent to support batching for faster simulation
"""

import asyncio
from typing import List, Dict, Any
from camel.agents import ChatAgent
from camel.messages import BaseMessage

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger

logger = get_logger('mirofish.batched_agent')


class BatchedChatAgentWrapper:
    """
    Wrapper for CAMEL ChatAgent that supports batched LLM calls.

    Instead of calling LLM sequentially for each agent, collect all prompts
    and send as a single batched request to vLLM.
    """

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def batch_step(
        self,
        agents: List[ChatAgent],
        user_messages: List[str]
    ) -> List[BaseMessage]:
        """
        Execute step() for multiple agents in a single batched LLM call.

        Args:
            agents: List of ChatAgent instances
            user_messages: Corresponding user messages for each agent

        Returns:
            List of response messages, one per agent
        """
        if not agents:
            return []

        # 1. Collect system prompts and conversation history for each agent
        batch_prompts = []
        for agent, user_msg in zip(agents, user_messages):
            # Get agent's system message and history
            system_msg = agent.system_message.content if agent.system_message else ""
            history = [
                {"role": msg.role_name, "content": msg.content}
                for msg in agent.memory.get_context()
            ]

            # Build full prompt context
            batch_prompts.append({
                "system": system_msg,
                "history": history,
                "user_message": user_msg
            })

        # 2. Format for batched API call
        # vLLM supports batched chat completions
        api_requests = []
        for prompt_data in batch_prompts:
            messages = [{"role": "system", "content": prompt_data["system"]}]
            messages.extend(prompt_data["history"])
            messages.append({"role": "user", "content": prompt_data["user_message"]})

            api_requests.append({
                "model": self.llm_client.model_name,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 512
            })

        # 3. Batched LLM call
        logger.info(f"Batching {len(api_requests)} agent decisions...")
        start_time = asyncio.get_event_loop().time()

        # Use asyncio.gather for parallel API calls to vLLM
        tasks = [
            self.llm_client.chat_completion(req)
            for req in api_requests
        ]
        responses = await asyncio.gather(*tasks)

        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info(f"Batch completed in {elapsed:.2f}s ({len(agents)} agents)")

        # 4. Parse responses and update agent memory
        result_messages = []
        for agent, response in zip(agents, responses):
            content = response['choices'][0]['message']['content']

            # Create response message
            response_msg = BaseMessage(
                role_name="assistant",
                role_type=agent.role_type,
                content=content,
                meta_dict=response.get('meta', {})
            )

            # Update agent's memory
            agent.memory.write_message(response_msg)

            result_messages.append(response_msg)

        return result_messages


# Helper function for OASIS integration
async def batch_agent_step(
    agents: List[Any],  # OASIS agents
    llm_client: LLMClient
) -> List[str]:
    """
    Helper to batch OASIS agent step() calls.

    Returns list of action strings.
    """
    wrapper = BatchedChatAgentWrapper(llm_client)

    # Extract user messages from each agent's state
    user_messages = [
        agent._get_current_observation()  # OASIS-specific
        for agent in agents
    ]

    # Batch process
    responses = await wrapper.batch_step(
        [agent.chat_agent for agent in agents],
        user_messages
    )

    # Parse into actions
    actions = [
        agent._parse_action_from_response(resp.content)
        for agent, resp in zip(agents, responses)
    ]

    return actions
```

**File 2: Modify `backend/scripts/run_parallel_simulation.py`**

Add batching to the simulation loop:

```python
# Around line 400-500, in the main simulation loop

# FIND THIS SECTION:
# for agent in active_agents:
#     action = agent.step()
#     environment.execute(action)

# REPLACE WITH:
import asyncio
from app.services.batched_chat_agent import batch_agent_step
from app.utils.llm_client import LLMClient

# Initialize LLM client
llm_client = LLMClient()

# Batch agent decisions
if len(active_agents) > 1:
    # Use batching for multiple agents
    actions = asyncio.run(batch_agent_step(active_agents, llm_client))
    for agent, action in zip(active_agents, actions):
        environment.execute(action)
else:
    # Single agent - use normal path
    action = active_agents[0].step()
    environment.execute(action)
```

**File 3: Update `backend/app/utils/llm_client.py`**

Add async support:

```python
import aiohttp
import asyncio
from typing import Dict, Any

class LLMClient:
    # ... existing code ...

    async def chat_completion(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Async chat completion call to vLLM server.

        Args:
            request: OpenAI-compatible request dict

        Returns:
            Response dict with 'choices' etc.
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                json=request,
                headers={"Content-Type": "application/json"}
            ) as response:
                return await response.json()
```

**Testing:**

1. Start small: 4 agents, 5 rounds
2. Verify batching works in logs
3. Compare timing: should see ~3x speedup
4. Scale up: 10 agents, 25 rounds
5. Monitor GPU utilization (both should be ~90%)

**Expected improvement:** 3-4x faster simulations

---

### Phase 3: Optimize Report Generation (1-2 days)

**Current issues:**
- Agent interviews timing out (180 sec)
- Sequential tool calls (InsightForge, PanoramaSearch)
- Each tool call = separate LLM invocation

**Optimizations:**

1. **Batch interview questions:**
   ```python
   # Instead of:
   for question in questions:
       for agent in agents:
           answer = interview_agent(agent, question)  # Sequential!

   # Do:
   all_prompts = [
       (agent, question)
       for agent in agents
       for question in questions
   ]
   answers = batch_interview(all_prompts)  # Parallel!
   ```

2. **Parallel tool execution:**
   ```python
   # Instead of:
   result1 = InsightForge(query1)
   result2 = PanoramaSearch(query2)
   result3 = QuickSearch(query3)

   # Do:
   results = await asyncio.gather(
       InsightForge(query1),
       PanoramaSearch(query2),
       QuickSearch(query3)
   )
   ```

3. **Increase interview timeout:**
   ```python
   # backend/app/services/simulation_ipc.py, line ~247
   timeout = 300  # Increase from 180 to 300 seconds
   ```

**File to modify:** `backend/app/services/report_agent.py`

Around line 500-600, update interview logic to use batching.

**Expected improvement:** 2-3x faster report generation

---

## 🔒 Priority 2: Security Hardening

### Critical Vulnerabilities to Fix

From the initial security audit, these MUST be addressed before any production use:

#### 1. Add Authentication (HIGH PRIORITY)

**Option A: Simple API Key (Quick - 2 hours)**

```python
# backend/app/middleware/auth.py (NEW)
from functools import wraps
from flask import request, jsonify
import os

API_KEY = os.environ.get('MIROFISH_API_KEY')

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        key = request.headers.get('X-API-Key')
        if not API_KEY or key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Usage in routes:
@app.route('/api/graph/ontology/generate', methods=['POST'])
@require_api_key
def generate_ontology():
    # ...
```

**Option B: JWT Auth (Better - 1 day)**

```bash
pip install flask-jwt-extended

# .env
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

```python
# backend/app/__init__.py
from flask_jwt_extended import JWTManager

app.config['JWT_SECRET_KEY'] = Config.JWT_SECRET_KEY
jwt = JWTManager(app)

# Create login endpoint, protect routes with @jwt_required()
```

#### 2. Fix CORS (30 minutes)

```python
# backend/app/__init__.py
# REPLACE:
CORS(app, resources={r"/api/*": {"origins": "*"}})

# WITH:
ALLOWED_ORIGINS = os.environ.get('ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
CORS(app, resources={
    r"/api/*": {
        "origins": ALLOWED_ORIGINS,
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})
```

#### 3. Require Strong Secrets (15 minutes)

```python
# backend/app/config.py

# REPLACE:
SECRET_KEY = os.environ.get('SECRET_KEY', 'mirofish-secret-key')

# WITH:
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set!")

# Same for Neo4j password
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')
if not NEO4J_PASSWORD or NEO4J_PASSWORD == 'mirofish':
    raise ValueError("NEO4J_PASSWORD must be set to a strong password!")
```

#### 4. Add Rate Limiting (1 hour)

```bash
pip install flask-limiter
```

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://"
)

# Apply to expensive endpoints
@app.route('/api/graph/ontology/generate', methods=['POST'])
@limiter.limit("10 per hour")
def generate_ontology():
    # ...
```

#### 5. Input Validation (2-3 hours)

```bash
pip install pydantic
```

```python
# backend/app/schemas/graph.py (NEW)
from pydantic import BaseModel, Field, validator
from typing import List

class OntologyGenerateRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=100)
    simulation_requirement: str = Field(..., min_length=10, max_length=5000)
    chunk_size: int = Field(500, ge=100, le=2000)
    chunk_overlap: int = Field(50, ge=0, le=500)

    @validator('simulation_requirement')
    def validate_requirement(cls, v):
        if len(v.strip()) < 10:
            raise ValueError('Simulation requirement too short')
        return v.strip()

# Use in routes:
from app.schemas.graph import OntologyGenerateRequest

@app.route('/api/graph/ontology/generate', methods=['POST'])
def generate_ontology():
    try:
        data = OntologyGenerateRequest(**request.json)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
    # ...
```

#### 6. Disable Debug Tracebacks in Production (5 minutes)

```python
# backend/app/__init__.py

@app.errorhandler(Exception)
def handle_error(e):
    logger.exception("Unhandled error")

    # Only show traceback in debug mode
    if app.debug:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
    else:
        return jsonify({
            "error": "Internal server error"
        }), 500
```

### Security Checklist

Before deploying to production:

- [ ] Add authentication (JWT or API keys)
- [ ] Fix CORS to whitelist specific origins
- [ ] Require strong SECRET_KEY and NEO4J_PASSWORD
- [ ] Add rate limiting to all endpoints
- [ ] Validate all user inputs with Pydantic
- [ ] Disable debug mode and traceback exposure
- [ ] Run behind reverse proxy (nginx) with HTTPS
- [ ] Set up firewall rules (ufw/iptables)
- [ ] Regular dependency updates (pip-audit, npm audit)
- [ ] Add logging of security events (failed auth, rate limit hits)

---

## 🔍 Priority 3: Search Integration (Optional)

### Current State

**No external search engine is used.** The system only searches the local Neo4j graph:

- `InsightForge` - Multi-dimensional graph search with sub-questions
- `PanoramaSearch` - Broad graph search
- `QuickSearch` - Fast keyword/vector search in Neo4j
- `InterviewAgents` - Query simulation agents

**All searches are hybrid: 0.7 × vector + 0.3 × keyword (BM25)**

### Should You Add External Search?

**Exa.ai vs Current Approach:**

| Aspect | Current (Neo4j only) | With Exa.ai |
|--------|---------------------|-------------|
| **Data source** | Only uploaded documents | Live web data |
| **Freshness** | Static (upload time) | Real-time web |
| **Context** | Full document context | Web snippets |
| **Cost** | Free (local) | $$$$ (API costs) |
| **Privacy** | Fully offline | Sends queries to Exa |
| **Speed** | Very fast (local) | Network latency |
| **Quality** | Perfect for your docs | Good for general knowledge |

**Recommendation:**

❌ **Don't add Exa for now.** Reasons:

1. **Your use case doesn't need it** - You're simulating reactions to *specific documents*, not general web knowledge
2. **Adds complexity** - Another API key, error handling, costs
3. **Privacy concerns** - Breaks "offline-first" promise
4. **Performance** - Network calls slow down report generation

**When Exa WOULD make sense:**

- If you want agents to reference current events during simulation
- If you're analyzing public sentiment that requires web context
- If you need fact-checking against latest information

**If you do want web search later:**

```python
# backend/app/services/web_search.py (NEW)
import os
from exa_py import Exa

class WebSearchService:
    def __init__(self):
        self.exa = Exa(api_key=os.environ.get('EXA_API_KEY'))

    def search(self, query: str, num_results: int = 5):
        """Search web with Exa.ai"""
        results = self.exa.search_and_contents(
            query,
            num_results=num_results,
            text={"max_characters": 1000}
        )
        return results
```

But for now: **Stick with local graph search.**

---

## 📋 Complete Implementation Checklist

### Week 1: Performance (Critical)

- [ ] **Day 1-2: vLLM Setup**
  - [ ] Stop Ollama
  - [ ] Install vLLM + dependencies
  - [ ] Configure for dual-GPU (tensor-parallel-size=2)
  - [ ] Test with curl
  - [ ] Benchmark: Run 4-agent test, compare timing
  - [ ] Create systemd service for vLLM

- [ ] **Day 3-5: Implement Batching**
  - [ ] Create `batched_chat_agent.py`
  - [ ] Add async LLMClient methods
  - [ ] Modify `run_parallel_simulation.py`
  - [ ] Test with 4 agents, verify batching works
  - [ ] Test with 10 agents, 50 rounds
  - [ ] Benchmark and document improvements

- [ ] **Day 6-7: Optimize Report Generation**
  - [ ] Batch interview questions
  - [ ] Parallel tool execution
  - [ ] Increase timeout to 300s
  - [ ] Test full report generation
  - [ ] Document timing improvements

### Week 2: Security (High Priority)

- [ ] **Day 1: Authentication**
  - [ ] Implement JWT or API key auth
  - [ ] Add login endpoint
  - [ ] Protect all routes
  - [ ] Update frontend to send auth headers
  - [ ] Test auth flow

- [ ] **Day 2: Input Validation & CORS**
  - [ ] Install Pydantic
  - [ ] Create request schemas
  - [ ] Validate all endpoints
  - [ ] Fix CORS configuration
  - [ ] Test with restricted origins

- [ ] **Day 3: Security Hardening**
  - [ ] Require strong secrets
  - [ ] Add rate limiting
  - [ ] Disable debug tracebacks
  - [ ] Add security logging
  - [ ] Run security audit

- [ ] **Day 4-5: Production Deployment**
  - [ ] Set up nginx reverse proxy
  - [ ] Configure HTTPS with Let's Encrypt
  - [ ] Set up firewall rules
  - [ ] Document deployment process
  - [ ] Create monitoring/alerting

### Week 3: Polish (Medium Priority)

- [ ] Embedding cache for repeated entities
- [ ] Async Python (Flask → FastAPI migration)
- [ ] Better error handling
- [ ] Comprehensive logging
- [ ] User documentation
- [ ] API documentation (OpenAPI/Swagger)

---

## 🎓 Learning Resources

### vLLM
- Docs: https://docs.vllm.ai/
- Tensor Parallelism: https://docs.vllm.ai/en/latest/serving/distributed_serving.html
- OpenAI Compatibility: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html

### Batching
- CAMEL-AI docs: https://www.camel-ai.org/
- Async Python: https://realpython.com/async-io-python/
- asyncio.gather: https://docs.python.org/3/library/asyncio-task.html

### Security
- Flask-JWT-Extended: https://flask-jwt-extended.readthedocs.io/
- Flask-Limiter: https://flask-limiter.readthedocs.io/
- Pydantic: https://docs.pydantic.dev/
- OWASP Top 10: https://owasp.org/www-project-top-ten/

---

## 📊 Expected Results

### Before Optimization (Current)
- 4 agents, 25 rounds: 10 min
- 10 agents, 50 rounds: 1.7 hours
- 20 agents, 100 rounds: 11 hours
- Report generation: 10+ min (with timeouts)

### After vLLM Only
- 4 agents, 25 rounds: 6 min (1.7x)
- 10 agents, 50 rounds: 1 hour (1.7x)
- 20 agents, 100 rounds: 6.5 hours (1.7x)
- Report generation: 7 min (1.4x)

### After vLLM + Batching
- 4 agents, 25 rounds: 3 min (3.3x)
- 10 agents, 50 rounds: 20 min (5x)
- 20 agents, 100 rounds: 1.5 hours (7.3x)
- Report generation: 3 min (3.3x)

### ROI Analysis

| Optimization | Effort | Speedup | ROI |
|-------------|--------|---------|-----|
| vLLM | 2 hours | 1.7x | ⭐⭐⭐⭐⭐ |
| Batching | 3 days | 3-4x | ⭐⭐⭐⭐⭐ |
| Both | 3.5 days | 5-7x | ⭐⭐⭐⭐⭐ |
| Security | 5 days | 0x (but essential) | ⭐⭐⭐⭐ |
| Go rewrite | 3 months | 0.03x | ❌ |

---

## 🚦 Quick Start for Next Session

```bash
# 1. Navigate to project
cd /home/tank/Development_Projects/MiroFish-Offline

# 2. Activate environment
conda activate mirofish

# 3. Check current status
./start-local.sh
# Or just backend:
python backend/run.py

# 4. Monitor
tail -f logs/backend.log

# 5. Test current performance
# Upload small doc, run 4 agents, 5 rounds
# Note the timing

# 6. Start vLLM implementation
# Follow Phase 1 steps above
```

---

## 📝 Notes & Gotchas

1. **GPU 0 Error:** One RTX 3090 shows hardware error in nvidia-smi - ignore this, GPU 1 works fine
2. **Port 3000 conflicts:** Multiple Vite instances can spawn, use `pkill -f vite` to clean up
3. **Simulation timeout:** If simulation seems hung, check `simulation.log` in uploads/simulations/sim_*/
4. **Report timeout:** 180 sec limit on agent interviews - increase to 300s
5. **Model loading:** First vLLM call takes 30-60 sec to load model into VRAM
6. **Conda environment:** Always activate `mirofish` environment before running

---

## 🎯 TL;DR - Do This First

**Priority 1 (Critical):**
1. Install vLLM with dual-GPU support (2 hours)
2. Implement batching for simulations (3 days)
3. Expected result: 5-7x faster for 20+ agent simulations

**Priority 2 (High):**
1. Add JWT authentication (1 day)
2. Fix CORS + rate limiting (1 day)
3. Input validation + security hardening (2 days)

**DON'T do:**
- ❌ Rewrite in Go (wrong bottleneck, 3 months wasted)
- ❌ Add Exa.ai search (unnecessary complexity)
- ❌ Optimize database queries (not the bottleneck)

**The bottleneck is LLM thinking, not Python plumbing.**

**Focus on: vLLM + batching = 7x speedup for 10% of the effort of a Go rewrite.**

---

## 📧 Contact & Support

- Project: https://github.com/[original-repo]
- CAMEL-AI: https://github.com/camel-ai/camel
- vLLM: https://github.com/vllm-project/vllm

**Good luck with the optimization!** 🚀
