# MiroFish-Offline: Next Session Handoff

**Date:** 2026-03-28
**Status:** vLLM + security complete. Next: simulation enhancements.
**Current Version:** Python/Flask + vLLM (dual GPU) + Ollama (embeddings) + Neo4j + Vue3
**Fork:** https://github.com/DrFrankieD-AI/MiroFish-Offline

---

## ✅ What's Been Done (Sessions 1-2)

| Phase | Status | Result |
|-------|--------|--------|
| Repository setup & security audit | ✅ | 13 vulnerabilities identified |
| vLLM dual-GPU tensor parallelism | ✅ | 5-63x simulation speedup |
| Batched agent decisions | ✅ | Free — OASIS already had asyncio.gather |
| Report optimization (timeouts) | ✅ | 180s → 300s |
| Security hardening | ✅ | API key auth, CORS, rate limiting, error handler |
| Git fork + upstream PR branches | ✅ | 3 branches ready for PRs |

**Performance now:**
- Single LLM call: 0.37s (was 5s)
- 4-agent round: 0.7s (was 20s)
- 25-round simulation: ~8s (was 510s)

---

## 🎯 Next Session Plan: Simulation Enhancements

### Roadmap items addressed (from ROADMAP.md)

| Roadmap Item | Version | Priority | Effort |
|---|---|---|---|
| Agent memory persistence across rounds | v0.6.0 | **HIGH** | 3 days |
| Custom agent archetypes | v0.6.0 | **HIGH** | 2 days |
| Model router (fast NER, large reports) | v0.5.0 | MEDIUM | 1 day |
| Export simulation transcripts as JSON | v0.6.0 | MEDIUM | 0.5 day |
| /api/status endpoint | v0.3.0 | LOW | 2 hours |
| Configurable hybrid search weights | v0.4.0 | LOW | 0.5 day |

---

### Priority 1: Agent Memory Persistence (3 days)

**Problem:** Agents have no memory between simulation rounds or across runs. Each round they start fresh — only the LLM prompt + current observation drives behavior. This makes multi-day simulations feel shallow.

**Current architecture:**
- Agent state lives in OASIS `OasisEnv` — ephemeral, in-memory only
- No `.save_state()` or `.memory` attribute on OASIS agents
- `GraphMemoryUpdater` already captures actions to Neo4j (but agents can't read them back)
- Agent interviews already inject graph context into prompts

**Recommended approach: LLM-summarized memory via Neo4j (Option C from research)**

This avoids patching OASIS and leverages existing infrastructure:

```
After each round:
  1. Collect all agent actions from that round (from actions.jsonl)
  2. For each agent that acted: query Neo4j for their accumulated facts
  3. Ask LLM: "Summarize what [Agent] knows after round N" (100-200 tokens)
  4. Store summary as agent memory node in Neo4j

Before each round:
  1. For each active agent: retrieve their memory summary from Neo4j
  2. Inject into the agent's system prompt prefix
  3. Agent now "remembers" what happened in previous rounds
```

**Files to modify:**

1. **`backend/app/services/agent_memory_persistence.py`** (NEW)
   ```python
   class AgentMemoryService:
       """Persist agent memory summaries to Neo4j between rounds"""

       def save_round_memories(self, graph_id, simulation_id, round_num, agent_actions):
           """After each round: summarize and store agent memories"""
           for agent_id, actions in agent_actions.items():
               # Build context from actions + existing memory
               existing_memory = self.get_agent_memory(graph_id, agent_id)
               new_actions = format_actions(actions)

               # Ask LLM: "Update this agent's memory summary"
               updated_memory = self.llm.summarize(
                   f"Agent: {agent_name}\n"
                   f"Previous memory: {existing_memory}\n"
                   f"New actions this round: {new_actions}\n"
                   f"Write an updated memory summary (200 tokens max)."
               )

               # Store in Neo4j as agent memory node
               self.storage.upsert_agent_memory(graph_id, agent_id, updated_memory, round_num)

       def get_agent_memory(self, graph_id, agent_id) -> str:
           """Retrieve agent's accumulated memory for prompt injection"""
           # Query Neo4j for latest memory node
           return self.storage.get_agent_memory(graph_id, agent_id)
   ```

2. **`backend/scripts/run_parallel_simulation.py`** (~lines 1253-1275)
   - After `await result.env.step(actions)`, call `memory_service.save_round_memories()`
   - Before building `actions` dict, inject memory into agent prompts

3. **`backend/app/storage/neo4j_storage.py`**
   - Add `upsert_agent_memory()` and `get_agent_memory()` methods
   - New node type: `(:AgentMemory {agent_id, simulation_id, round_num, summary})`

4. **`backend/app/storage/neo4j_schema.py`**
   - Add schema for AgentMemory nodes and indexes

**Key challenge:** OASIS agents don't expose a way to modify their system prompt mid-simulation. Options:
- a) Monkey-patch agent's `system_message` before each round (fragile but works)
- b) Prepend memory to the observation/environment state that agents receive
- c) Use OASIS's `ManualAction` to inject a "memory update" message

Option (b) is cleanest — modify `get_active_agents_for_round()` to inject memory context into agent observations.

**Expected result:** Agents reference their past actions and positions, creating more coherent multi-day narratives.

---

### Priority 2: Custom Agent Archetypes (2 days)

**Problem:** All agents are generated from a single LLM prompt with entity context. No way to define reusable personality templates (e.g., "aggressive trader", "cautious academic", "viral influencer") that shape behavior independently of the source document.

**Current architecture:**
- `oasis_profile_generator.py` (850+ lines)
- Two generation methods: LLM-based (default) and rule-based (fallback)
- Entity types classified as INDIVIDUAL vs GROUP (lines 154-178)
- Rule-based templates are hardcoded per entity type (lines 718-789)
- No user-facing way to define custom archetypes

**Implementation plan:**

1. **`backend/app/services/archetypes.py`** (NEW) — Archetype definition system
   ```python
   @dataclass
   class AgentArchetype:
       name: str                    # e.g., "Aggressive Trader"
       description: str             # Human-readable description
       personality_traits: List[str]  # e.g., ["risk-taking", "data-driven", "impatient"]
       mbti_pool: List[str]         # e.g., ["ENTJ", "ESTP", "ENTP"]
       age_range: Tuple[int, int]   # e.g., (28, 55)
       activity_level: float        # 0.0-1.0
       sentiment_bias: float        # -1.0 to 1.0
       stance_tendency: str         # "supportive", "opposing", "neutral", "contrarian"
       speaking_style: str          # e.g., "Short, punchy, uses financial jargon"
       prompt_modifier: str         # Injected into persona generation prompt

   # Built-in archetypes
   BUILTIN_ARCHETYPES = {
       "aggressive_trader": AgentArchetype(
           name="Aggressive Trader",
           personality_traits=["risk-taking", "data-driven", "fast-reacting"],
           mbti_pool=["ENTJ", "ESTP"],
           sentiment_bias=0.3,
           stance_tendency="contrarian",
           speaking_style="Short, data-heavy, uses $TICKER format",
           prompt_modifier="This agent reacts strongly to market signals..."
       ),
       "cautious_academic": AgentArchetype(...),
       "viral_influencer": AgentArchetype(...),
       "corporate_pr": AgentArchetype(...),
       "concerned_citizen": AgentArchetype(...),
       "investigative_journalist": AgentArchetype(...),
       "tech_enthusiast": AgentArchetype(...),
       "policy_analyst": AgentArchetype(...),
   }
   ```

2. **Modify `oasis_profile_generator.py`**
   - Accept optional `archetype` parameter per entity
   - Inject archetype's `prompt_modifier` and traits into persona generation prompt
   - Use archetype's `mbti_pool`, `age_range`, `activity_level` as defaults
   - Fall back to current behavior if no archetype specified

3. **`backend/app/api/archetypes.py`** (NEW) — REST API for archetypes
   ```
   GET  /api/archetypes              — List available archetypes
   GET  /api/archetypes/:name        — Get archetype details
   POST /api/archetypes              — Create custom archetype
   PUT  /api/archetypes/:name        — Update archetype
   ```

4. **Modify simulation create/prepare API**
   - Accept `archetype_assignments: {entity_uuid: archetype_name}` in prepare request
   - Frontend can show archetype picker per entity during env setup

5. **Store custom archetypes**
   - Save to `backend/uploads/archetypes/` as JSON files
   - Built-in archetypes in code, custom ones on disk
   - No database needed (simple file storage)

**Expected result:** Users can assign "Aggressive Trader" to some agents and "Cautious Academic" to others, creating more diverse and realistic simulation dynamics.

---

### Priority 3: Model Router (1 day)

**Problem:** The 32B model is used for everything — NER extraction, ontology generation, agent profiles, simulation, reports. Some of these (NER, embeddings) don't need a 32B model and would be faster with a smaller one.

**Current architecture:**
- Single `LLM_MODEL_NAME` in .env used everywhere
- `LLMClient` class reads from Config
- OASIS/CAMEL reads `OPENAI_API_BASE_URL` and uses whatever model is served

**Implementation:**

1. **Update `.env`:**
   ```bash
   # Model routing
   LLM_MODEL_FAST=qwen2.5:7b          # For NER, ontology, embeddings
   LLM_MODEL_LARGE=qwen2.5:32b        # For simulation, reports, interviews
   ```

2. **Update `config.py`:**
   ```python
   LLM_MODEL_FAST = os.environ.get('LLM_MODEL_FAST', LLM_MODEL_NAME)
   LLM_MODEL_LARGE = os.environ.get('LLM_MODEL_LARGE', LLM_MODEL_NAME)
   ```

3. **Update `llm_client.py`:**
   ```python
   def get_client(task_type: str = "default") -> LLMClient:
       if task_type in ("ner", "ontology", "profile_generation"):
           return LLMClient(model=Config.LLM_MODEL_FAST)
       else:
           return LLMClient(model=Config.LLM_MODEL_LARGE)
   ```

4. **vLLM multi-model:** vLLM 0.18 supports serving multiple models. Update `start-vllm.sh` to optionally serve both:
   ```bash
   # Or: run two vLLM instances on separate ports
   # Port 8000: 32B model (GPU 0+1, TP=2)
   # Port 8001: 7B model (CPU or separate GPU)
   ```

   Simpler alternative: serve one model on vLLM, keep Ollama for the fast model:
   ```bash
   LLM_MODEL_FAST=qwen2.5:7b           # Served by Ollama (port 11434)
   LLM_MODEL_LARGE=qwen2.5:32b         # Served by vLLM (port 8000)
   LLM_BASE_URL_FAST=http://localhost:11434/v1
   LLM_BASE_URL_LARGE=http://localhost:8000/v1
   ```

**Expected result:** NER and ontology generation 3-5x faster (7B vs 32B), while keeping full quality for simulation and reports.

---

### Priority 4: Export Simulation Transcripts (0.5 day)

**Quick win.** Add an API endpoint to export simulation data as structured JSON.

1. **`GET /api/simulation/:id/export`**
   ```json
   {
     "simulation_id": "sim_xxx",
     "config": {...},
     "agents": [...],
     "rounds": [
       {
         "round": 1,
         "simulated_hour": 0,
         "twitter_actions": [...],
         "reddit_actions": [...]
       }
     ],
     "summary": {
       "total_rounds": 25,
       "total_actions": 36,
       "most_active_agent": "Apple Inc.",
       "sentiment_trend": [...]
     }
   }
   ```

2. **Files:** Add export endpoint to `backend/app/api/simulation.py`, read from existing `actions.jsonl` files.

---

### Priority 5: /api/status Endpoint (2 hours)

Quick win. Replace the basic `/health` with a comprehensive status check.

```json
GET /api/status
{
  "status": "ok",
  "services": {
    "neo4j": {"connected": true, "uri": "bolt://localhost:7687"},
    "vllm": {"connected": true, "model": "qwen2.5:32b", "gpu_count": 2},
    "ollama": {"connected": true, "embedding_model": "nomic-embed-text"}
  },
  "gpu": [
    {"index": 0, "name": "RTX 3090", "memory_used": "21.3GB", "memory_total": "24GB"},
    {"index": 1, "name": "RTX 3090", "memory_used": "21.3GB", "memory_total": "24GB"}
  ],
  "disk_free": "1.5TB",
  "active_simulations": 1
}
```

---

## 📋 Implementation Checklist

### Week 1: Agent Memory + Archetypes

- [ ] **Day 1-2: Agent Memory Persistence**
  - [ ] Create `agent_memory_persistence.py` service
  - [ ] Add Neo4j schema for AgentMemory nodes
  - [ ] Add `upsert_agent_memory()` / `get_agent_memory()` to storage
  - [ ] Modify `run_parallel_simulation.py` to save memories after each round
  - [ ] Modify agent prompt injection to include memory context
  - [ ] Test: run 25-round simulation, verify agents reference past events

- [ ] **Day 3-4: Custom Archetypes**
  - [ ] Create `archetypes.py` with built-in archetype definitions
  - [ ] Create `/api/archetypes` REST endpoints
  - [ ] Modify `oasis_profile_generator.py` to accept archetype parameter
  - [ ] Modify simulation prepare API to accept archetype assignments
  - [ ] Test: assign different archetypes to entities, verify diverse behavior

- [ ] **Day 5: Model Router + Quick Wins**
  - [ ] Add model routing to `config.py` and `llm_client.py`
  - [ ] Configure Ollama for fast model, vLLM for large model
  - [ ] Add `/api/status` endpoint
  - [ ] Add `/api/simulation/:id/export` endpoint
  - [ ] Test full pipeline with model routing

### Week 2: Polish + Upstream PRs

- [ ] Create proper GitHub fork (when cooldown expires)
- [ ] Submit 3 PRs to nikmcfly/MiroFish-Offline
- [ ] Configurable hybrid search weights (v0.4.0)
- [ ] Input validation with Pydantic schemas
- [ ] Update all documentation

---

## 🚦 Quick Start for Next Session

```bash
cd /home/tank/Development_Projects/MiroFish-Offline
conda activate mirofish

# Start services
docker-compose up -d neo4j
nohup bash start-vllm.sh > logs/vllm.log 2>&1 &
sleep 60
./start-local.sh

# Verify
curl http://localhost:8000/v1/models   # vLLM
curl http://localhost:5001/health      # Backend
nvidia-smi                             # Both GPUs loaded

# Access from office
# http://192.168.1.153:3000
```

## Architecture (Current)

```
Office Browser (192.168.1.153:3000)
    │
    ▼
Vite Dev Server (:3000)  ──proxy──▶  Flask API (:5001)
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              vLLM (:8000)      Ollama (:11434)      Neo4j (:7687)
              qwen2.5:32b       nomic-embed-text     Graph DB
              GPU 0 + GPU 1     CPU/minimal GPU      Docker
              TP=2, AWQ         Embeddings only
              16K context
```

## Key Files

| File | Purpose |
|------|---------|
| `start-vllm.sh` | vLLM startup (dual GPU, auto-detect) |
| `start-local.sh` / `stop-local.sh` | Backend + frontend lifecycle |
| `.env` | All configuration (vLLM, Ollama, Neo4j, security) |
| `backend/app/middleware/` | Auth, rate limiting |
| `backend/app/services/graph_memory_updater.py` | Existing graph memory (actions → Neo4j) |
| `backend/app/services/oasis_profile_generator.py` | Agent profile generation (850+ lines) |
| `backend/app/services/simulation_config_generator.py` | Simulation parameters (850+ lines) |
| `backend/scripts/run_parallel_simulation.py` | Core simulation loop (line 1253 = agent step) |
| `IMPROVEMENT_RESULTS.md` | Session 2 results and benchmarks |

## Known Issues

1. **GPU 0 intermittent:** Fixed by reseating, but may recur — `start-vllm.sh` auto-falls back to TP=1
2. **Zombie Vite processes:** Use `pkill -f vite` if port 3000 is occupied
3. **GitHub fork cooldown:** Can't create proper fork yet — repo exists as independent copy
4. **OASIS Python 3.12+:** Still requires Python 3.11 (camel-oasis constraint)
