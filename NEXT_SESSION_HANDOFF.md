# MiroFish-Offline: Next Session Handoff

**Date:** 2026-03-30
**Status:** Full pipeline proven (23 agents, 72 rounds, 119 min). Needs optimization and hardening.
**Fork:** https://github.com/DrFrankieD-AI/MiroFish-Offline

---

## ✅ What's Been Done

### Infrastructure (Sessions 1-2)
- vLLM 0.18.0 dual-GPU tensor parallelism (Qwen2.5-32B-Instruct-AWQ)
- Security: API key auth, CORS, rate limiting, error handler
- Interview timeouts raised to 300s, tool-choice support added
- SQLite permission fix (umask before OASIS DB creation)

### Features (Sessions 3-4)
- Agent memory persistence (LLM-summarized, Neo4j storage, prompt injection)
- Memory optimization (accumulate actions, flush every 5 rounds)
- Custom archetypes system (11 built-in, REST API, profile generator integration)
- vLLM systemd service file
- Frontend defensive parsing (17 fixes across 5 components)
- Report chat response parsing fix

### Full Pipeline Test: Meridian Health PR (23 agents, 72 rounds)
```
Phase 1 (Ontology):         167s    (2.8 min)    2%
Phase 2 (Graph Build):      580s    (9.7 min)    8%
Phase 3 (Agent Profiles):   ~420s   (~7 min)     6%
Phase 4 (Simulation):       4301s   (71.7 min)   60%  ← biggest bottleneck
Phase 5 (Report):           ~1680s  (~28 min)    24%
─────────────────────────────────────────────────
TOTAL:                      ~7148s  (~119 min / ~2 hrs)

Output: 371 actions, 23 agent memories, 4-section report
```

---

## 🐛 Known Bugs (Must Fix)

### 1. Memory summarization exceeds 16K context
**Severity:** Medium — causes warning, some memories fail to update
**Cause:** When an agent accumulates many actions over 5 rounds, the summarization prompt (previous memory + all new actions) exceeds vLLM's 16K max context.
**Fix:** Truncate the prompt input:
```python
# In agent_memory_persistence.py, before building prompt:
# Truncate previous memory to 500 words
if previous_memory and len(previous_memory.split()) > 500:
    previous_memory = ' '.join(previous_memory.split()[:500]) + '...'
# Truncate new actions to 20 most recent
if len(action_lines) > 20:
    action_lines = action_lines[-20:]
```
**Effort:** 30 minutes

### 2. Ollama embeddings fail when vLLM uses too much GPU
**Severity:** Medium — graph search degrades to BM25-only (no vector search)
**Cause:** vLLM `--gpu-memory-utilization 0.85` leaves no room for Ollama's embedding model
**Fix:** Lower to 0.75 in `start-vllm.sh` and `vllm.service`:
```bash
--gpu-memory-utilization 0.75
```
**Trade-off:** Slightly less KV cache headroom for vLLM (still plenty for 16 concurrent seqs)
**Effort:** 5 minutes

### 3. Frontend fragility — silent failures
**Severity:** Low-Medium — errors show in console but UI appears hung
**Examples encountered:**
- Report chat response was nested object, not string (fixed)
- Simulation status 500 during state transition (transient)
- getSimulation 500 when navigating before prep complete
**Fix:** Add loading states and error toasts to UI
**Effort:** 1 day

### 4. Simulation subprocess dies silently
**Severity:** Medium — no recovery mechanism, user sees stale status
**Cause:** OOM or unhandled exception in OASIS subprocess
**Fix:**
- Add heartbeat file (subprocess writes timestamp every 30s)
- Backend monitors heartbeat, marks simulation as failed if stale
- Add process memory monitoring
**Effort:** 2-3 hours

---

## 🔧 Performance Optimization Plan

### Simulation Loop (71.7 min → ~25 min)

| Optimization | Savings | Effort | How |
|-------------|---------|--------|-----|
| **Parallel memory summaries** | -17 min | 2 hrs | Use `asyncio.gather()` for all agent summary LLM calls instead of sequential |
| **Memory interval 5→10** | -7 min | 5 min | Change `DEFAULT_SUMMARIZE_INTERVAL = 10` in agent_memory_persistence.py |
| **Truncate memory prompts** | -5 min | 30 min | Cap previous_memory at 500 words, new_actions at 20 items |
| **Total sim savings** | **~29 min** | | **71.7 → ~43 min** |

### Graph Build (9.7 min → ~2 min)

| Optimization | Savings | Effort | How |
|-------------|---------|--------|-----|
| **Parallel NER extraction** | -8 min | 1 day | Fire all 8 batch NER prompts concurrently to vLLM via asyncio |
| **Total build savings** | **~8 min** | | **9.7 → ~2 min** |

### Report Generation (28 min → ~10 min)

| Optimization | Savings | Effort | How |
|-------------|---------|--------|-----|
| **Parallel tool calls** | -10 min | 2 hrs | Run InsightForge + PanoramaSearch + QuickSearch concurrently |
| **Parallel section generation** | -5 min | 4 hrs | Generate independent sections in parallel |
| **Reduce interview rounds** | -3 min | config | Interview 3 agents instead of 5 per section |
| **Total report savings** | **~18 min** | | **28 → ~10 min** |

### Other

| Optimization | Savings | Effort |
|-------------|---------|--------|
| GPU memory for embeddings (0.85→0.75) | fixes embedding failures | 5 min |
| Agent profile parallelism ×10 | -4 min | 10 min |

### Summary: 119 min → ~55 min (2.2x faster)

---

## 🏗️ Resilience Hardening Plan

### Why it feels fragile

Every run has uncovered bugs because:
1. **No error boundaries in UI** — API errors cause silent failures or cryptic console errors
2. **Subprocess isolation** — simulation runs as a separate process with file-based IPC (fragile)
3. **State transitions** — UI polls APIs during state changes, gets transient 500s
4. **GPU memory contention** — vLLM + Ollama + OASIS fight for GPU memory
5. **No health monitoring** — if a subprocess dies, nothing notices

### Hardening Checklist (Priority Order)

#### A. Process Management (1 day)
- [ ] Subprocess heartbeat monitoring (write timestamp every 30s, detect stale)
- [ ] Auto-restart failed simulations with backoff
- [ ] GPU memory monitoring (warn if <2GB free before starting sim)
- [ ] Clean process tree teardown on simulation stop

#### B. Error Handling in UI (1 day)
- [ ] Global axios error interceptor with user-friendly toast notifications
- [ ] Loading spinners during all API calls (no silent hangs)
- [ ] Retry logic with exponential backoff on transient 500s
- [ ] Graceful degradation messages ("Report search limited — embedding service unavailable")

#### C. State Machine Hardening (0.5 day)
- [ ] Backend: validate state transitions (can't start simulation if not in READY state)
- [ ] Frontend: disable buttons during invalid states
- [ ] Race condition protection on concurrent API calls

#### D. Resource Management (0.5 day)
- [ ] vLLM GPU memory allocation: 0.85 → 0.75 (leave room for embeddings)
- [ ] Memory summarization prompt truncation (prevent 16K overflow)
- [ ] SQLite connection pooling / timeout handling
- [ ] Temp file cleanup after simulation completes

#### E. Observability (1 day)
- [ ] `/api/status` endpoint (Neo4j, vLLM, Ollama, GPU, disk, active sims)
- [ ] Structured JSON logging (replace print statements)
- [ ] Simulation timing metrics (per-phase duration logged)
- [ ] Error rate tracking

---

## 💰 LLM Backend Options

### Current: Local vLLM (Free)
- ✅ No per-call cost
- ✅ Full privacy
- ✅ Both GPUs utilized
- ❌ 119 min for full pipeline
- ❌ GPU memory contention with embeddings

### Option: OpenRouter (Pay-per-call)
- ✅ Faster models available (GPT-4o, Claude, etc.)
- ✅ No GPU management
- ❌ **Cost concern:** ~$3 per full simulation run at current scale
  - Simulation: ~400 calls × ~2K tokens × $0.003/1K = ~$2.40
  - Memory: ~100 calls × ~1K tokens = ~$0.30
  - Report: ~40 calls × ~3K tokens = ~$0.36
  - **Per-run total: ~$3**
- ❌ Privacy: document content sent to external API
- ❌ Cost unpredictable with testing/development iterations

**Recommendation:** Keep local vLLM for development and testing (free iterations). Consider OpenRouter only for production with:
- Per-client cost tracking
- Hard spending cap ($50/day default)
- Environment variable toggle: `LLM_BACKEND=local|openrouter`
- Pass costs through to client billing

### Option: Second vLLM instance for embeddings
- Overkill — `nomic-embed-text` is 274MB, runs fine on CPU
- Better fix: lower vLLM GPU utilization to 0.75

### Option: Dedicated embedding on CPU
```python
# In embedding_service.py, add CPU fallback:
# Use sentence-transformers directly (already installed)
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('nomic-ai/nomic-embed-text-v1', device='cpu')
```
- Eliminates GPU contention entirely
- ~50ms per embedding (fast enough)
- No Ollama dependency for embeddings

---

## 📋 Next Session Priority

### Quick Fixes (< 1 hour total)
1. [ ] Memory prompt truncation (500 word cap) — 30 min
2. [ ] vLLM GPU util 0.85 → 0.75 — 5 min
3. [ ] Memory interval 5 → 10 — 5 min
4. [ ] Commit and push — 5 min

### Performance (1-2 days)
5. [ ] Parallel memory summaries (asyncio.gather) — 2 hrs
6. [ ] Parallel NER in graph build — 1 day
7. [ ] Parallel report tool calls — 2 hrs

### Resilience (2 days)
8. [ ] Subprocess heartbeat monitoring — 3 hrs
9. [ ] UI error toasts and loading states — 1 day
10. [ ] `/api/status` endpoint — 2 hrs
11. [ ] State machine validation — 4 hrs

### Features (when stable)
12. [ ] Custom archetypes UI in frontend
13. [ ] Export simulation transcript as JSON
14. [ ] Branded PDF report template
15. [ ] OpenRouter backend option (with cost tracking)

---

## 🚦 Quick Start

```bash
cd /home/tank/Development_Projects/MiroFish-Offline
conda activate mirofish

# Start services
docker-compose up -d neo4j
# Ollama auto-starts via systemd
nohup bash start-vllm.sh > logs/vllm.log 2>&1 &  # ~60s model load
./start-local.sh

# Or install vLLM as systemd service:
sudo cp vllm.service /etc/systemd/system/mirofish-vllm.service
sudo systemctl daemon-reload
sudo systemctl enable --now mirofish-vllm.service

# Verify
nvidia-smi                             # Both GPUs loaded
curl http://localhost:8000/v1/models   # vLLM
curl http://localhost:5001/health      # Backend

# Access from office: http://192.168.1.153:3000
```

## Architecture

```
Office Browser → Vite (:3000) → Flask (:5001) → vLLM (:8000) [2×RTX 3090, TP=2]
                                              → Ollama (:11434) [embeddings]
                                              → Neo4j (:7687) [Docker]
                                              ↓
                                    Simulation subprocess
                                    (OASIS/CAMEL, SQLite, IPC)
                                              ↓
                                    Agent Memory (Neo4j)
```

## Key Files

| File | Purpose |
|------|---------|
| `start-vllm.sh` / `vllm.service` | vLLM lifecycle |
| `start-local.sh` / `stop-local.sh` | Backend + frontend |
| `.env` | All configuration |
| `backend/app/services/agent_memory_persistence.py` | Memory system |
| `backend/app/services/archetypes.py` | 11 archetype definitions + manager |
| `backend/app/api/archetypes.py` | Archetype REST API |
| `backend/app/middleware/` | Auth, rate limiting |
| `backend/scripts/run_parallel_simulation.py` | Core simulation loop |
| `docs/private/STRATEGIC_ANALYSIS.md` | Business strategy (gitignored) |
| `test_data/press_release_meridian_health.txt` | Test document |

## Known Issues

1. **GPU memory:** vLLM at 0.85 starves Ollama embeddings → lower to 0.75
2. **Memory overflow:** Summaries exceed 16K context → truncate prompt
3. **Process management:** Simulation subprocess dies silently → add heartbeat
4. **UI fragility:** Silent errors, no loading states → error toasts
5. **Report speed:** 28 min due to sequential ReACT pattern → parallelize
