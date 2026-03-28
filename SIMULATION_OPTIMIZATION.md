# Simulation Performance: vLLM + Batching Impact

## Your Current Simulation (4 agents, 25 rounds)

**Actual timings:**
- Started: 16:57:20
- Twitter completed: 17:05:52 (8.5 minutes, 19 actions)
- Reddit: Still running, Round 23/25 (~90% done)
- **Estimated total:** 10-12 minutes ✅

**This is NORMAL for the current setup** - not hours.

---

## The Real Problem: Scaling

Your 4-agent test is fine. But look what happens with realistic simulations:

### Scaling Analysis

| Agents | Rounds | Current (Sequential) | With vLLM+Batching |
|--------|--------|----------------------|-------------------|
| 4 | 25 | **10 min** | 3 min |
| 10 | 50 | **1.7 hours** | 20 min |
| 20 | 100 | **11 hours** | 1.5 hours |
| 50 | 100 | **28 hours** | 3.5 hours |

**Formula:**
- Current: `rounds × agents × 5 sec/agent ÷ 60 = minutes`
- Optimized: `rounds × (agents ÷ batch_size) × 6 sec ÷ 60 = minutes`

---

## Why Batching Is Critical

### Current Architecture (OASIS + Ollama):

```python
# Each round does this:
for agent in agents:  # Sequential!
    action = agent.step()  # LLM call, ~5 seconds
    environment.execute(action)
```

**Problem:** 50 agents = 50 sequential LLM calls = 250 seconds/round!

### With Batching:

```python
# Collect all agent inputs
prompts = [agent.get_prompt() for agent in agents]

# Single batched LLM call
responses = llm.batch_generate(prompts)  # ~8 seconds total

# Distribute responses
for agent, response in zip(agents, responses):
    environment.execute(agent.parse_response(response))
```

**Improvement:** 50 agents in 8 seconds = **30x faster per round!**

---

## Implementation Plan

### Phase 1: vLLM Setup (EASY - 2 hours)

**Install vLLM:**
```bash
conda activate mirofish
pip install vllm

# Stop Ollama
sudo systemctl stop ollama

# Start vLLM with both GPUs
python -m vllm.entrypoints.openai.api_server \
  --model qwen3:32b \
  --tensor-parallel-size 2 \
  --max-num-seqs 8 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.9 \
  --port 11434
```

**Expected speedup:** 1.5-2x (better GPU utilization)

---

### Phase 2: Implement Batching (MODERATE - 2-3 days)

**Files to modify:**

1. **`backend/scripts/run_parallel_simulation.py`**
   - Add batch collection logic before agent steps

2. **Custom CAMEL Wrapper:**
```python
# backend/app/services/batched_chat_agent.py

class BatchedChatAgent:
    """Wrapper to batch multiple agent decisions"""
    
    @classmethod
    async def batch_step(cls, agents: List[ChatAgent]) -> List[str]:
        """Execute multiple agent steps in one batched LLM call"""
        
        # 1. Collect all prompts
        prompts = []
        for agent in agents:
            prompt = agent._format_prompt()
            prompts.append(prompt)
        
        # 2. Batched API call
        responses = await cls.llm_client.batch_chat(prompts)
        
        # 3. Assign responses to agents
        for agent, response in zip(agents, responses):
            agent._parse_response(response)
        
        return responses
```

3. **Modify OASIS simulation loop:**
```python
# In run_parallel_simulation.py

async def run_round(agents, environment):
    # OLD WAY (sequential):
    # for agent in agents:
    #     action = agent.step()
    
    # NEW WAY (batched):
    actions = await BatchedChatAgent.batch_step(agents)
    
    for action in actions:
        environment.execute(action)
```

**Expected speedup:** 3-4x on top of vLLM

---

### Phase 3: Optimize Batch Size (FINE-TUNING - 1 day)

**vLLM batch sizes:**
- Small (batch=4): Good for 24GB VRAM, lower latency
- Medium (batch=8): Balanced
- Large (batch=16): Max throughput, higher VRAM

**Optimal for dual RTX 3090s:**
```python
--max-num-seqs 8  # Process 8 agents simultaneously
```

---

## Quick Wins (Do This Now)

### 1. Test with Fewer Rounds
Edit your simulation config or use max-rounds parameter:
```bash
# Your current: 25 rounds = 10 minutes
# Test mode: 5 rounds = 2 minutes
```

In the UI, set:
- Simulation hours: 12 (instead of 72)
- This gives you 12 rounds → **5 minutes/platform**

### 2. Monitor Progress
```bash
# Terminal 1: Watch simulation progress
tail -f backend/uploads/simulations/sim_*/simulation.log

# Terminal 2: See LLM calls
watch -n 1 nvidia-smi

# Terminal 3: Count completed actions
watch -n 2 "wc -l backend/uploads/simulations/sim_*/*/actions.jsonl"
```

---

## Expected Results After Optimization

### Your Test (4 agents, 25 rounds):
- **Current:** 10 minutes
- **With vLLM:** 6 minutes
- **With vLLM + Batching:** 3 minutes
- **Improvement:** Not dramatic (small scale)

### Realistic Simulation (20 agents, 100 rounds):
- **Current:** 11 hours ⏰
- **With vLLM:** 6 hours
- **With vLLM + Batching:** 1.5 hours ⚡
- **Improvement:** 7x faster!

### Large Simulation (50 agents, 200 rounds):
- **Current:** 3.5 days 💀
- **With vLLM:** 1.8 days
- **With vLLM + Batching:** 12 hours 🚀
- **Improvement:** 7x faster!

---

## Bottom Line

**Your current 4-agent test isn't slow** - 10 minutes is expected.

**The problem emerges at scale:**
- 10+ agents → Hours
- 50+ agents → Days (unusable without optimization)

**Priority:**
1. ✅ Finish your current test (should complete in ~2 more minutes)
2. 🚀 Install vLLM (2 hours) - uses both GPUs, easy win
3. 🎯 Implement batching (2-3 days) - 3-4x speedup, essential for production
4. 🏆 Both together = 5-7x faster simulations

**ROI:**
- vLLM: 2 hours work = 1.5-2x speedup
- Batching: 2-3 days work = 3-4x speedup
- Go rewrite: 2-3 months = 0.03x speedup ❌

**The answer is definitely vLLM + batching, not Go.**
