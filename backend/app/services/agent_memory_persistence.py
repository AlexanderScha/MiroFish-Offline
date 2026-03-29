"""
Agent Memory Persistence Service

Provides persistent memory for OASIS agents across simulation rounds.
After each round, agent actions are summarized by the LLM and stored in Neo4j.
Before each round, accumulated memories are injected into agent system prompts.

OASIS agents have no built-in persistence — this service adds it externally
by modifying agent.system_message.content between rounds.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

from ..utils.llm_client import LLMClient
from ..storage.neo4j_storage import Neo4jStorage

logger = logging.getLogger('mirofish.agent_memory')

# Marker used to delimit memory section in agent system prompts
MEMORY_MARKER = "\n\n[ACCUMULATED MEMORY]"

SUMMARIZE_PROMPT = """You are summarizing an AI agent's experience during a social media simulation.

Agent name: {agent_name}
Agent persona (excerpt): {persona_excerpt}

Previous memory (what the agent already knows):
{previous_memory}

New actions this round (Round {round_num}):
{new_actions}

Write an updated memory summary for this agent. Include:
- Key events and interactions from all rounds so far
- The agent's evolving opinions and positions
- Important relationships or conflicts with other agents
- Any trends the agent has observed

Keep the summary under 200 words. Write in third person.
If there is no previous memory, start fresh from the new actions."""


class AgentMemoryService:
    """Persist and retrieve agent memory summaries via Neo4j."""

    def __init__(self, storage: Neo4jStorage, llm_client: Optional[LLMClient] = None):
        self.storage = storage
        self.llm = llm_client or LLMClient()

    def save_round_memories(
        self,
        simulation_id: str,
        round_num: int,
        agent_actions: Dict[int, List[Dict[str, Any]]],
        agent_names: Dict[int, str],
        agent_personas: Dict[int, str],
    ) -> int:
        """
        After a round: summarize and persist memories for agents that acted.

        Args:
            simulation_id: Simulation ID
            round_num: Current round number
            agent_actions: {agent_id: [action_dicts]} for agents that acted this round
            agent_names: {agent_id: agent_name} mapping
            agent_personas: {agent_id: persona_text} for context (first 500 chars)

        Returns:
            Number of agents whose memories were updated
        """
        if not agent_actions:
            return 0

        updated = 0
        for agent_id, actions in agent_actions.items():
            if not actions:
                continue

            agent_name = agent_names.get(agent_id, f"Agent_{agent_id}")
            persona = agent_personas.get(agent_id, "")[:500]

            # Format actions as readable text
            action_lines = []
            for a in actions:
                action_type = a.get("action_type", "unknown")
                content = a.get("action_args", {}).get("content", "")
                if content:
                    action_lines.append(f"- {action_type}: \"{content[:200]}\"")
                else:
                    action_lines.append(f"- {action_type}")
            new_actions_text = "\n".join(action_lines) if action_lines else "No significant actions."

            # Get existing memory
            previous_memory = self.storage.get_agent_memory(simulation_id, agent_id)
            previous_memory = previous_memory or "No previous memories — this is the start of the simulation."

            # Ask LLM to update the memory summary
            prompt = SUMMARIZE_PROMPT.format(
                agent_name=agent_name,
                persona_excerpt=persona,
                previous_memory=previous_memory,
                round_num=round_num,
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
                logger.debug(f"Memory updated for {agent_name} (round {round_num})")

            except Exception as e:
                logger.warning(f"Failed to update memory for {agent_name}: {e}")

        if updated > 0:
            logger.info(f"Round {round_num}: Updated memories for {updated}/{len(agent_actions)} agents")

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
