"""
Agent Memory Persistence Service

Provides persistent memory for OASIS agents across simulation rounds.
Actions are accumulated locally, then summarized by LLM every N rounds
and stored in Neo4j. Before each round, accumulated memories are
injected into agent system prompts.

OASIS agents have no built-in persistence — this service adds it externally
by modifying agent.system_message.content between rounds.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from ..utils.llm_client import LLMClient
from ..storage.neo4j_storage import Neo4jStorage

logger = logging.getLogger('mirofish.agent_memory')

# Marker used to delimit memory section in agent system prompts
MEMORY_MARKER = "\n\n[ACCUMULATED MEMORY]"

# Default: summarize every 5 rounds (not every round) to reduce LLM overhead
DEFAULT_SUMMARIZE_INTERVAL = 5

SUMMARIZE_PROMPT = """You are summarizing an AI agent's experience during a social media simulation.

Agent name: {agent_name}
Agent persona (excerpt): {persona_excerpt}

Previous memory (what the agent already knows):
{previous_memory}

New actions since last update (Rounds {start_round}-{end_round}):
{new_actions}

Write an updated memory summary for this agent. Include:
- Key events and interactions from all rounds so far
- The agent's evolving opinions and positions
- Important relationships or conflicts with other agents
- Any trends the agent has observed

Keep the summary under 200 words. Write in third person.
If there is no previous memory, start fresh from the new actions."""


class AgentMemoryService:
    """Persist and retrieve agent memory summaries via Neo4j.

    Actions are accumulated in memory between summarization intervals.
    LLM summarization only happens every `summarize_interval` rounds,
    reducing overhead by ~80% compared to per-round summarization.
    """

    def __init__(
        self,
        storage: Neo4jStorage,
        llm_client: Optional[LLMClient] = None,
        summarize_interval: int = DEFAULT_SUMMARIZE_INTERVAL,
    ):
        self.storage = storage
        self.llm = llm_client or LLMClient()
        self.summarize_interval = summarize_interval

        # Accumulated actions between summarization rounds
        # {agent_id: [action_dicts]}
        self._pending_actions: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self._last_summarized_round = 0

    def accumulate_actions(
        self,
        agent_actions: Dict[int, List[Dict[str, Any]]],
    ) -> None:
        """Buffer agent actions for later summarization. No LLM call."""
        for agent_id, actions in agent_actions.items():
            self._pending_actions[agent_id].extend(actions)

    def should_summarize(self, round_num: int) -> bool:
        """Check if it's time to run LLM summarization."""
        return (round_num % self.summarize_interval == 0) or len(self._pending_actions) > 0 and round_num > 0

    def flush_memories(
        self,
        simulation_id: str,
        round_num: int,
        agent_names: Dict[int, str],
        agent_personas: Dict[int, str],
        force: bool = False,
    ) -> int:
        """
        Summarize accumulated actions and persist to Neo4j.

        Only runs if enough rounds have passed since last summarization,
        or if force=True (e.g., simulation ending).

        Args:
            simulation_id: Simulation ID
            round_num: Current round number
            agent_names: {agent_id: agent_name}
            agent_personas: {agent_id: persona_excerpt}
            force: Force summarization regardless of interval

        Returns:
            Number of agents whose memories were updated
        """
        if not self._pending_actions:
            return 0

        if not force and (round_num - self._last_summarized_round) < self.summarize_interval:
            return 0

        updated = 0
        start_round = self._last_summarized_round + 1

        for agent_id, actions in self._pending_actions.items():
            if not actions:
                continue

            agent_name = agent_names.get(agent_id, f"Agent_{agent_id}")
            persona = agent_personas.get(agent_id, "")[:500]

            # Format accumulated actions
            action_lines = []
            for a in actions:
                action_type = a.get("action_type", "unknown")
                content = a.get("action_args", {}).get("content", "")
                if content:
                    action_lines.append(f"- {action_type}: \"{content[:200]}\"")
                else:
                    action_lines.append(f"- {action_type}")
            new_actions_text = "\n".join(action_lines)

            # Get existing memory
            previous_memory = self.storage.get_agent_memory(simulation_id, agent_id)
            previous_memory = previous_memory or "No previous memories — this is the start of the simulation."

            prompt = SUMMARIZE_PROMPT.format(
                agent_name=agent_name,
                persona_excerpt=persona,
                previous_memory=previous_memory,
                start_round=start_round,
                end_round=round_num,
                new_actions=new_actions_text,
            )

            try:
                updated_summary = self.llm.chat(
                    messages=[
                        {"role": "system", "content": "You are a concise summarizer. Output only the memory summary, nothing else."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=300,
                )

                self.storage.upsert_agent_memory(
                    simulation_id=simulation_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    summary=updated_summary.strip(),
                    round_num=round_num,
                )
                updated += 1

            except Exception as e:
                logger.warning(f"Failed to update memory for {agent_name}: {e}")

        if updated > 0:
            logger.info(
                f"Rounds {start_round}-{round_num}: Summarized memories for "
                f"{updated}/{len(self._pending_actions)} agents"
            )

        # Clear buffer and update checkpoint
        self._pending_actions.clear()
        self._last_summarized_round = round_num

        return updated

    def get_agent_memory(self, simulation_id: str, agent_id: int) -> Optional[str]:
        """Retrieve an agent's accumulated memory summary."""
        return self.storage.get_agent_memory(simulation_id, agent_id)

    def get_all_memories(self, simulation_id: str) -> Dict[int, str]:
        """Retrieve all agent memories for a simulation."""
        return self.storage.get_all_agent_memories(simulation_id)

    def inject_memories_into_agents(
        self,
        simulation_id: str,
        agents: List[Tuple[int, Any]],
    ) -> int:
        """
        Before a round: inject accumulated memories into agent system prompts.

        Modifies agent.system_message.content in-place by appending/updating
        the [ACCUMULATED MEMORY] section.

        Args:
            simulation_id: Simulation ID
            agents: List of (agent_id, agent_object) tuples

        Returns:
            Number of agents that received memory injection
        """
        memories = self.get_all_memories(simulation_id)
        if not memories:
            return 0

        injected = 0
        for agent_id, agent in agents:
            memory_text = memories.get(agent_id)
            if not memory_text:
                continue

            try:
                sys_msg = getattr(agent, 'system_message', None)
                if sys_msg is None or not hasattr(sys_msg, 'content'):
                    continue

                current_content = sys_msg.content or ""

                # Strip old memory section if present
                if MEMORY_MARKER in current_content:
                    current_content = current_content.split(MEMORY_MARKER)[0]

                # Append updated memory
                sys_msg.content = (
                    f"{current_content}{MEMORY_MARKER}\n"
                    f"Your memories from this simulation so far:\n"
                    f"{memory_text}"
                )
                injected += 1

            except Exception as e:
                logger.warning(f"Failed to inject memory for agent {agent_id}: {e}")

        if injected > 0:
            logger.info(f"Injected memories into {injected}/{len(agents)} agents")

        return injected
