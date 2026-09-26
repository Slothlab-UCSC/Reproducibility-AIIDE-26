import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from Agent.agent import Agent
from Clusters.cluster import cluster
from Simulation.public_opinion import public_opinion_main
from Simulation.interactions import InteractionEngine
from typing import List, Dict, Any, Optional
import random
import matplotlib.pyplot as plt
import json
from Knowledge_Base.knowledge_base import KnowledgeBase, ObjectOfDiscussion, Topic
from Simulation.interactions import InteractionEngine
from Simulation.config import TOPIC, MASTER_ROOT, MASTER_KB, INFO_PATH, AGENTS, OPINION_AXIS
from Simulation.llm import generate_conversation_with_llm

    
class Simulation:
    """
    Main simulation class for the Lyra system.
    
    Manages a population of agents engaging in discussions over multiple rounds,
    tracking opinion changes, clustering, and knowledge sharing as described in
    the Lyra paper.
    """
    
    def __init__(self, 
                 agents: List[Agent],
                 max_rounds: int = 10,
                 convergence_threshold: float = 0.01,
                 enable_knowledge_sharing: bool = True,
                 knowledge_sharing_probability: float = 0.3):
        """
        Initialize the simulation.
        
        Args:
            agents: List of Agent objects to participate in the simulation
            max_rounds: Maximum number of discussion rounds to run
            convergence_threshold: Threshold for determining convergence (opinion change < threshold)
            enable_knowledge_sharing: Whether agents can share knowledge with each other
            knowledge_sharing_probability: Probability of knowledge sharing per round per agent
        """
        self.agents = agents
        self.max_rounds = max_rounds
        self.convergence_threshold = convergence_threshold
        self.enable_knowledge_sharing = enable_knowledge_sharing
        self.knowledge_sharing_probability = knowledge_sharing_probability
        self.interactions = InteractionEngine(agents)
        
        # History tracking
        self.round_history: List[Dict[str, Any]] = []
        self.current_round = 0
        self.initial_agent_states: List[Dict[str, Any]] = []
        self.opinion_history = {}

    def get_opinions(self):
        return {agent.agent_id: agent.opinion for agent in self.agents}
    
    def log_round(self, round_number):
        """
        Save all agents' opinions for the given round.
        """
        self.opinion_history[round_number] = self.get_opinions()
        
    def run(self) -> Dict[str, Any]:
        """
        Run the complete simulation.
        
        Returns:
            Dictionary containing simulation results and history
        """
        # Store initial agent states before simulation starts
        self.initial_agent_states = [agent.get_state_summary() for agent in self.agents]
        
        print(f"Starting simulation with {len(self.agents)} agents for up to {self.max_rounds} rounds")
        print("=" * 80)
        
        for round_num in range(1, self.max_rounds + 1):
            self.log_round(round_num)
            self.current_round = round_num
            print(f"\n--- Round {round_num} ---")
            
            # Run one round of the simulation
            round_result = self._run_round(round_num)
            self.round_history.append(round_result)
            
            # Terminate if public opinion has formed
            if round_result['public_opinion_formed']:
                print(f"\nPublic opinion formed at round {round_num} - simulation complete")
                break
        
        return self._generate_results()
    
    def _run_round(self, round_num: int) -> Dict[str, Any]:
        """
        Execute one round of the simulation.
        
        Per the paper:
        1. Cluster agents by their expressed opinions using Jenks Natural Breaks
        2. Determine if public opinion has formed (k <= 3 clusters)
        3. Update agent opinions/attitudes based on clustering and public opinion strength
        4. Optionally share knowledge between agents
        
        Args:
            round_num: Current round number
            
        Returns:
            Dictionary containing round results
        """
        # Step 1: Cluster agents by their opinions
        print("\nClustering agents by opinions...")
        c = cluster(self.agents).cluster_by_jenks()
        

        # Step 2: Interactions
        if self.enable_knowledge_sharing:
            self._share_knowledge(round_num)
        
        self.interactions.update_inner_cluster(c)
        
        # Log conversations for this round
        # Reset conversation counter for each round (start from 0 for each round)
        events, _ = run_sequential_conversations(
            engine=self.interactions,
            clusters=c,
            topic=TOPIC,  # Use topic from config
            start_conv_index=0,
            max_turns_per_cluster=random.randint(10, 15),
            round_num=round_num,
        )

        # Step 3: Get number of clusters
        num_clusters = c.k if c.k else 0
        print(f"Number of clusters: {num_clusters}")

        # Step 4: Update agent opinions and attitudes
        # public_opinion_main returns whether public opinion has formed (k <= 3 clusters)
        if(round_num > 1):
            public_opinion_formed = public_opinion_main(self.agents, c, round_num, self.get_opinions(), self.opinion_history[round_num-1], events)
        else:
            public_opinion_formed = public_opinion_main(self.agents, c, round_num, self.get_opinions(), None, events)

        print(f"Public opinion formed: {public_opinion_formed}")

        
        # Record round state
        # Deduplicate agent states by agent_id (keep first occurrence)
        agent_states_dict = {}
        for agent in self.agents:
            state = agent.get_state_summary()
            agent_id = state['agent_id']
            if agent_id not in agent_states_dict:
                agent_states_dict[agent_id] = state
        
        round_result = {
            'round': round_num,
            'num_clusters': num_clusters,
            'public_opinion_formed': public_opinion_formed,
            'cluster_assignments': c.as_assignments(),
            'agent_states': list(agent_states_dict.values()),
            'cluster_stats': self._get_cluster_stats(c),
            'events': events,  # Include conversation events
        }
        
        return round_result
    
    def _share_knowledge(self, round_num: int) -> None:
        """
        Simulate knowledge sharing between agents.
        
        Agents can share objects of discussion from their knowledge bases
        with other agents, allowing knowledge to spread through the population.
        
        Args:
            round_num: Current round number
        """
        if not self.agents:
            return
        
        print("\nKnowledge sharing phase...")
        shared_count = 0
        
        for agent in self.agents:
            if random.random() < self.knowledge_sharing_probability:
                # Select a random other agent to share with
                other_agent = random.choice([a for a in self.agents if a != agent])
                
                # Get a random object of discussion from this agent's knowledge base
                obj = agent.knowledge_base.get_rand_discussion_obj()
                
                if obj is not None:
                    # Share the knowledge with the other agent
                    other_agent.add_knowledge(obj)
                    shared_count += 1
                    print(f"{agent.agent_id} shared knowledge with {other_agent.agent_id}")
        
        if shared_count == 0:
            print("No knowledge was shared this round")
    
    def _get_cluster_stats(self, c: cluster) -> Dict[int, Dict[str, float]]:
        """
        Get statistics for each cluster.
        
        Args:
            c: Cluster object
            
        Returns:
            Dictionary mapping cluster_id to statistics
        """
        stats = {}
        for cluster_obj in c.clusters:
            stats[cluster_obj.cluster_id] = {
                'mean_opinion': cluster_obj.mean_opinion(),
                'mean_attitude': cluster_obj.mean_attitude(),
                'variance_opinion': cluster_obj.variance_opinion(),
                'size': cluster_obj.size()
            }
        return stats
    
    def _check_convergence(self, round_result: Dict[str, Any]) -> bool:
        """
        Check if the simulation has converged.
        
        Convergence is determined by checking if opinions have changed
        significantly from the previous round.
        
        Args:
            round_result: Results from the current round
            
        Returns:
            True if converged, False otherwise
        """
        if len(self.round_history) < 2:
            return False
        
        # Compare current round with previous round
        prev_round = self.round_history[-2]
        curr_round = round_result
        
        # Calculate average opinion change
        total_change = 0.0
        for i, agent_state in enumerate(curr_round['agent_states']):
            if i < len(prev_round['agent_states']):
                prev_opinion = prev_round['agent_states'][i]['opinion']
                curr_opinion = agent_state['opinion']
                total_change += abs(curr_opinion - prev_opinion)
        
        avg_change = total_change / len(self.agents) if self.agents else 0.0
        
        return avg_change < self.convergence_threshold
    
    def _generate_results(self) -> Dict[str, Any]:
        """
        Generate summary results from the simulation.
        
        Returns:
            Dictionary containing simulation results
        """
        if not self.round_history:
            return {'error': 'No rounds completed'}
        
        # Extract opinion and attitude trajectories (including initial states)
        opinion_trajectories = {}
        attitude_trajectories = {}
        uncertainty_trajectories = {}
        
        for agent in self.agents:
            agent_id = agent.agent_id
            opinion_trajectories[agent_id] = []
            attitude_trajectories[agent_id] = []
            uncertainty_trajectories[agent_id] = []
            
            # Add initial state if available
            if self.initial_agent_states:
                for initial_state in self.initial_agent_states:
                    if initial_state['agent_id'] == agent_id:
                        opinion_trajectories[agent_id].append(initial_state['opinion'])
                        attitude_trajectories[agent_id].append(initial_state['attitude'])
                        uncertainty_trajectories[agent_id].append(initial_state['uncertainty'])
                        break
            
            # Add states from each round
            for round_data in self.round_history:
                for agent_state in round_data['agent_states']:
                    if agent_state['agent_id'] == agent_id:
                        opinion_trajectories[agent_id].append(agent_state['opinion'])
                        attitude_trajectories[agent_id].append(agent_state['attitude'])
                        uncertainty_trajectories[agent_id].append(agent_state['uncertainty'])
                        break
        
        # Calculate final statistics
        final_round = self.round_history[-1]
        
        # Collect all events from all rounds
        all_events = []
        for round_data in self.round_history:
            if 'events' in round_data:
                all_events.extend(round_data['events'])
        
        results = {
            'total_rounds': len(self.round_history),
            'final_num_clusters': final_round['num_clusters'],
            'public_opinion_formed': final_round['public_opinion_formed'],
            'opinion_trajectories': opinion_trajectories,
            'attitude_trajectories': attitude_trajectories,
            'uncertainty_trajectories': uncertainty_trajectories,
            'cluster_evolution': [r['num_clusters'] for r in self.round_history],
            'all_events': all_events,  # Include all conversation events
            'round_history': self.round_history,
            'final_agent_states': final_round['agent_states']
        }
        
        return results
    
    def print_summary(self) -> None:
        """Print a summary of the simulation results."""
        if not self.round_history:
            print("No simulation data to summarize")
            return
        
        print("\n" + "=" * 80)
        print("SIMULATION SUMMARY")
        print("=" * 80)
        
        final_round = self.round_history[-1]
        print(f"\nTotal Rounds: {len(self.round_history)}")
        print(f"Final Number of Clusters: {final_round['num_clusters']}")
        print(f"Public Opinion Formed: {final_round['public_opinion_formed']}")
        
        print("\nCluster Evolution:")
        for i, num_clusters in enumerate([r['num_clusters'] for r in self.round_history], 1):
            print(f"  Round {i}: {num_clusters} clusters")
        
        if self.initial_agent_states:
            print("\nInitial Agent States:")
            for agent_state in self.initial_agent_states:
                print(f"  {agent_state['agent_id']}: "
                      f"opinion={agent_state['opinion']:.2f}, "
                      f"attitude={agent_state['attitude']:.2f}, "
                      f"uncertainty={agent_state['uncertainty']:.2f}")
        
        print("\nFinal Agent States:")
        # Deduplicate by agent_id (keep first occurrence)
        seen_agents = set()
        for agent_state in final_round['agent_states']:
            agent_id = agent_state['agent_id']
            if agent_id not in seen_agents:
                seen_agents.add(agent_id)
                print(f"  {agent_id}: "
                      f"opinion={agent_state['opinion']:.2f}, "
                      f"attitude={agent_state['attitude']:.2f}, "
                      f"uncertainty={agent_state['uncertainty']:.2f}")
        
        print("=" * 80)
    
    def generate_graphs(self, output_dir: str = "graphs") -> None:
        """
        Generate graphs showing agent trajectories for opinion, attitude, and uncertainty.
        
        Args:
            output_dir: Directory to save the graphs (default: "graphs")
        """
        if not self.round_history:
            print("No simulation data to graph")
            return
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Get trajectories (including initial states)
        results = self._generate_results()
        opinion_trajectories = results['opinion_trajectories']
        attitude_trajectories = results['attitude_trajectories']
        uncertainty_trajectories = results['uncertainty_trajectories']
        
        # Determine number of rounds (including initial state)
        num_rounds = len(self.round_history) + (1 if self.initial_agent_states else 0)
        rounds = list(range(num_rounds))
        
        # Get unique colors for each agent
        colors = plt.cm.tab10(range(len(self.agents)))
        
        # Generate Opinion Trajectory Graph
        plt.figure(figsize=(12, 6))
        for i, agent in enumerate(self.agents):
            agent_id = agent.agent_id
            if agent_id in opinion_trajectories and len(opinion_trajectories[agent_id]) > 0:
                plt.plot(rounds[:len(opinion_trajectories[agent_id])], 
                        opinion_trajectories[agent_id], 
                        marker='o', label=agent_id, 
                        color=colors[i], linewidth=2, markersize=6)
        
        plt.xlabel('Round', fontsize=12)
        plt.ylabel('Opinion', fontsize=12)
        plt.title('Agent Opinion Trajectories Over Rounds', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'opinion_trajectories.png'), dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved opinion trajectory graph to {output_dir}/opinion_trajectories.png")
        
        # Generate Attitude Trajectory Graph
        plt.figure(figsize=(12, 6))
        for i, agent in enumerate(self.agents):
            agent_id = agent.agent_id
            if agent_id in attitude_trajectories and len(attitude_trajectories[agent_id]) > 0:
                plt.plot(rounds[:len(attitude_trajectories[agent_id])], 
                        attitude_trajectories[agent_id], 
                        marker='s', label=agent_id, 
                        color=colors[i], linewidth=2, markersize=6)
        
        plt.xlabel('Round', fontsize=12)
        plt.ylabel('Attitude', fontsize=12)
        plt.title('Agent Attitude Trajectories Over Rounds', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'attitude_trajectories.png'), dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved attitude trajectory graph to {output_dir}/attitude_trajectories.png")
        
        # Generate Uncertainty Trajectory Graph
        plt.figure(figsize=(12, 6))
        for i, agent in enumerate(self.agents):
            agent_id = agent.agent_id
            if agent_id in uncertainty_trajectories and len(uncertainty_trajectories[agent_id]) > 0:
                plt.plot(rounds[:len(uncertainty_trajectories[agent_id])], 
                        uncertainty_trajectories[agent_id], 
                        marker='^', label=agent_id, 
                        color=colors[i], linewidth=2, markersize=6)
        
        plt.xlabel('Round', fontsize=12)
        plt.ylabel('Uncertainty', fontsize=12)
        plt.title('Agent Uncertainty Trajectories Over Rounds', fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'uncertainty_trajectories.png'), dpi=300, bbox_inches='tight')
        plt.close()
        print(f"Saved uncertainty trajectory graph to {output_dir}/uncertainty_trajectories.png")

def build_agent_knowldge_base(agents):
    for a in agents:
        a.seed_knowledge_from_master(
            master_kb=MASTER_KB,
            topic=TOPIC,
            info_json_path=INFO_PATH,
            min_sources=2,
            max_sources=5,
        )
        # describe_agent(a, TOPIC)
    
def run_simulation(agents: List[Agent], 
                   max_rounds: int = 10,
                   convergence_threshold: float = 0.01,
                   enable_knowledge_sharing: bool = True,
                   knowledge_sharing_probability: float = 0.3) -> Dict[str, Any]:
    """
    Convenience function to run a simulation.
    
    Args:
        agents: List of Agent objects
        max_rounds: Maximum number of rounds
        convergence_threshold: Convergence threshold
        enable_knowledge_sharing: Whether to enable knowledge sharing
        knowledge_sharing_probability: Probability of knowledge sharing
        
    Returns:
        Simulation results dictionary
    """
    sim = Simulation(
        agents=agents,
        max_rounds=max_rounds,
        convergence_threshold=convergence_threshold,
        enable_knowledge_sharing=enable_knowledge_sharing,
        knowledge_sharing_probability=knowledge_sharing_probability
    )
    
    build_agent_knowldge_base(AGENTS)
    
    results = sim.run()
    sim.print_summary()
    
    # Generate graphs
    sim.generate_graphs()
    
    return results
# ===================== Conversation ========================
def format_conversation_to_text(events):
    """
    Convert conversation event arrays into natural language dialogue.
    
    Args:
        events: List of conversation event dictionaries
        
    Returns:
        Dictionary mapping conversation_id to formatted conversation text
    """
    from collections import defaultdict
    from Simulation.config import OPINION_AXIS
    
    min_label = OPINION_AXIS.get("min_label", "Left")
    max_label = OPINION_AXIS.get("max_label", "Right")
    
    # Group events by conversation_id
    conversations = defaultdict(list)
    for event in events:
        conv_id = event.get('conversation_id', 0)
        conversations[conv_id].append(event)
    
    # Sort events within each conversation by turn
    for conv_id in conversations:
        conversations[conv_id].sort(key=lambda x: x.get('turn', 0))
    
    formatted_conversations = {}
    
    for conv_id, conv_events in conversations.items():
        lines = []
        lines.append(f"\n=== Conversation {conv_id} ===\n")
        
        for event in conv_events:
            speaker = event.get('speaker', 'Unknown')
            target = event.get('target')
            event_type = event.get('type', 'unknown')
            statement_opinion = event.get('statement_opinion')
            source = event.get('source')
            
            # Get opinion direction label
            def get_opinion_label(v):
                if v is None:
                    return None
                if v < -0.33:
                    return f"leaning {min_label}"
                elif v > 0.33:
                    return f"leaning {max_label}"
                else:
                    return "neutral"
            
            # Generate natural language based on type
            if event_type == 'research':
                if source:
                    # Handle source being a dict or string
                    if isinstance(source, dict):
                        source_name = source.get('name', 'an article')
                    else:
                        source_name = source
                    lines.append(f"{speaker}: [Researches '{source_name}']")
                else:
                    lines.append(f"{speaker}: [Does research]")
            
            elif event_type == 'statement':
                opinion_label = get_opinion_label(statement_opinion)
                if target:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker} (to {target}): I think we're looking at a {opinion_label} position on this issue (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker} (to {target}): Let me share my thoughts on this.")
                else:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker}: I'd say the position is {opinion_label} (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker}: I'd like to share my perspective.")
            
            elif event_type == 'agreement':
                opinion_label = get_opinion_label(statement_opinion)
                if target:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker} (to {target}): I agree with you on that, expressing a {opinion_label} view (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker} (to {target}): I agree with what you're saying.")
                else:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker}: I agree, expressing a {opinion_label} position (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker}: I agree.")
            
            elif event_type == 'disagreement':
                opinion_label = get_opinion_label(statement_opinion)
                if target:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker} (to {target}): I have to disagree, taking a {opinion_label} stance (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker} (to {target}): I disagree with that.")
                else:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker}: I disagree, expressing a {opinion_label} view (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker}: I disagree.")
            
            elif event_type == 'support':
                opinion_label = get_opinion_label(statement_opinion)
                if target:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker} (to {target}): I support your position on this with a {opinion_label} argument (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker} (to {target}): I support what you're saying.")
                else:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker}: I support this {opinion_label} position (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker}: I support this position.")
            
            elif event_type == 'challenge':
                opinion_label = get_opinion_label(statement_opinion)
                if target:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker} (to {target}): I have to challenge that view with a {opinion_label} perspective (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker} (to {target}): I challenge what you're saying.")
                else:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker}: I challenge this position from a {opinion_label} standpoint (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker}: I challenge this position.")
            
            elif event_type == 'question':
                if target:
                    lines.append(f"{speaker} (to {target}): What do you think about that?")
                else:
                    lines.append(f"{speaker}: I have a question about this.")
            
            elif event_type == 'response':
                opinion_label = get_opinion_label(statement_opinion)
                if target:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker} (to {target}): To answer your question, I'd say it's a {opinion_label} position (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker} (to {target}): Let me respond to that.")
                else:
                    if statement_opinion is not None and opinion_label:
                        lines.append(f"{speaker}: Here's my response - I see it as a {opinion_label} view (opinion: {statement_opinion:.3f}).")
                    else:
                        lines.append(f"{speaker}: Let me respond.")
            
            else:
                lines.append(f"{speaker}: [{event_type}]")
        
        formatted_conversations[conv_id] = "\n".join(lines)
    
    return formatted_conversations

def cluster_agent_ids(clusters):
    result = []
    for cl in clusters._clusters:
        ids = [a.agent_id for a in cl.agents]
        result.append(ids)
    return result

def run_sequential_conversations(engine, clusters, topic, start_conv_index, max_turns_per_cluster, round_num=None):
    all_events = []
    conv_counter = start_conv_index
    
    # Create Interactions directory for logging
    interactions_dir = os.path.join(ROOT, "Simulation", "Interactions")
    
    # If round_num is provided, organize by round
    if round_num is not None:
        round_dir = os.path.join(interactions_dir, f"round-{round_num}")
        os.makedirs(round_dir, exist_ok=True)
    else:
        round_dir = interactions_dir
        os.makedirs(round_dir, exist_ok=True)

    for cluster_idx, cl in enumerate(clusters._clusters):
        agent_ids = [a.agent_id for a in cl.agents]
        conv_id = cluster_idx
        
        # Determine conversation number for file naming (use current counter, then increment)
        current_conv_num = conv_counter
        conv_counter += 1
        
        # Open JSONL file for this conversation
        log_file_path = os.path.join(round_dir, f"conversation-{current_conv_num}.jsonl")
        
        if len(agent_ids) == 1:
            a = cl.agents[0]
            print(a)
            
            new_oods = a.research_when_isolated(
                master_kb=MASTER_KB,
                topic=topic,
                info_json_path=INFO_PATH,
                min_new=1,
                max_new=3,
            )

            with open(log_file_path, "w", encoding="utf-8") as log_file:
                for ood in new_oods:
                    event = {
                        "round": round_num,
                        "conversation_id": conv_id,
                        "speaker": a.agent_id,
                        "target": None,
                        "type": "research",
                        "statement_opinion": None,
                        "source": ood.name
                    }
                    all_events.append(event)
                    # Write to JSONL file (one JSON object per line)
                    log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
            
            continue

        last_type = None
        outstanding_question = False
        last_speaker_id = None
        question_target_id = None  # Track who was asked a question

        with open(log_file_path, "w", encoding="utf-8") as log_file:
            for t in range(max_turns_per_cluster):
                event = engine.sample_interaction_event(
                    topic=topic,
                    conversation_id=conv_id,
                    cluster_agent_ids=agent_ids,
                    prev_type=last_type,
                    outstanding_question=outstanding_question,
                    last_speaker_id=last_speaker_id,
                    question_target_id=question_target_id,
                )
                if event is None:
                    continue

                last_type = event["type"]
                last_speaker_id = event["speaker"]

                if last_type == "question":
                    outstanding_question = True
                    question_target_id = event.get("target")  # Track who was asked
                elif last_type == "response":
                    outstanding_question = False
                    question_target_id = None  # Question answered

                event["turn"] = t
                # Add round number to event
                if round_num is not None:
                    event["round"] = round_num
                all_events.append(event)
                # Write to JSONL file (one JSON object per line)
                log_file.write(json.dumps(event, ensure_ascii=False) + "\n")
                
                # If the event has a source (OOD presented), make other agents learn it
                if event.get("source") and isinstance(event["source"], dict):
                    source_info = event["source"]
                    speaker_id = event["speaker"]
                    target_id = event.get("target")
                    
                    # Create OOD from source information
                    from Knowledge_Base.knowledge_base import ObjectOfDiscussion
                    presented_ood = ObjectOfDiscussion(
                        name=source_info.get("name", "Unknown"),
                        topic=topic,
                        publisher=speaker_id,  # Use speaker's agent_id as publisher
                        source_type=source_info.get("source_type", "Agent Statement"),
                        attitude=source_info.get("attitude", 0.0),
                        rating=source_info.get("source_bias", 0.0),
                        content=source_info.get("content", ""),
                    )
                    
                    # If there's a specific target, teach them
                    if target_id:
                        target_agent = engine.get_agent(target_id)
                        if target_agent and not target_agent.has_knowledge_item(
                            presented_ood.name, topic, speaker_id
                        ):
                            # Evaluate agent_opinion for the receiving agent
                            presented_ood.agent_opinion = target_agent.evaluate_ood(presented_ood)
                            target_agent.add_knowledge(presented_ood)
                    else:
                        # No specific target - teach all agents in the cluster
                        for agent_id in agent_ids:
                            if agent_id != speaker_id:  # Don't teach the speaker
                                agent = engine.get_agent(agent_id)
                                if agent and not agent.has_knowledge_item(
                                    presented_ood.name, topic, speaker_id
                                ):
                                    # Create a copy for each agent and evaluate their opinion
                                    agent_ood = ObjectOfDiscussion(
                                        name=presented_ood.name,
                                        topic=presented_ood.topic,
                                        publisher=presented_ood.publisher,
                                        source_type=presented_ood.source_type,
                                        attitude=presented_ood.attitude,
                                        rating=presented_ood.rating,
                                        content=presented_ood.content,
                                    )
                                    agent_ood.agent_opinion = agent.evaluate_ood(agent_ood)
                                    agent.add_knowledge(agent_ood)
            
            # Ensure conversation doesn't end on a question - add a response if needed
            if outstanding_question and question_target_id:
                # Generate a response from the agent who was asked
                response_event = engine.sample_interaction_event(
                    topic=topic,
                    conversation_id=conv_id,
                    cluster_agent_ids=agent_ids,
                    prev_type="question",
                    outstanding_question=True,
                    last_speaker_id=last_speaker_id,
                    question_target_id=question_target_id,
                )
                
                if response_event:
                    response_event["turn"] = max_turns_per_cluster  # Add as final turn
                    if round_num is not None:
                        response_event["round"] = round_num
                    all_events.append(response_event)
                    # Write to JSONL file
                    log_file.write(json.dumps(response_event, ensure_ascii=False) + "\n")

    return all_events, conv_counter

def describe_agent(agent, topic):
    print(f"\n=== Agent {agent.agent_id} ===")
    print(f"  opinion     = {agent.opinion:.2f}")
    print(f"  attitude    = {agent.attitude:.2f}")
    print(f"  bias        = {agent.bias:.2f}")
    print(f"  uncertainty = {agent.uncertainty:.2f}")

    subs = agent.subscribed_sources.get(topic, [])
    print(f"  subscribed sources for '{topic}':")
    for s in subs:
        print(f"    - {s}")

    t = agent.knowledge_base.get_knowledge_by_topic(topic, content_only=False)
    if t is None:
        print("  no topic objects in agent KB")
        return

    print(f"  # objects in agent KB for '{topic}': {len(t.all_objects())}")
    for obj in t.all_objects():
        print(f"    • {obj.name}  (publisher={obj.publisher}, rating={obj.rating:.2f})")

if __name__ == "__main__":
    # # Example usage with randomly generated agents with names

    # build_agent_knowldge_base(AGENTS)
    # # kb = KnowledgeBase("Knowledge_Base/Master_KB")
    # c = cluster(AGENTS).cluster_by_jenks()

    # # 2. Build interaction engine and adjacency graph
    # engine = InteractionEngine(AGENTS)
    # engine.update_inner_cluster(c)

    # # 3. Run sequential conversations (one cluster at a time)
    # # Note: Pass round_num to organize logs by round (e.g., round_num=1)
    # events, next_conv_index = run_sequential_conversations(
    #     engine=engine,
    #     clusters=c,
    #     topic=TOPIC,
    #     start_conv_index=0,
    #     max_turns_per_cluster=random.randint(10, 25),
    #     round_num=1,  # Specify round number to organize logs by round
    # )

    # # 4. Format and print conversations - show LLM, template, and raw versions for comparison
    # llm_conversations = generate_conversation_with_llm(events, TOPIC)
    # template_conversations = format_conversation_to_text(events)
    
    # for conv_id in sorted(llm_conversations.keys()):
    #     # LLM-generated version
    #     print(llm_conversations[conv_id])
        
    #     # Template-based version
    #     print("\n--- Template-Based Version ---")
    #     if conv_id in template_conversations:
    #         print(template_conversations[conv_id])
    #     else:
    #         print("[No template version available]")
        
    #     # Raw dictionary version
    #     print("\n--- Raw Dictionary Version ---")
    #     conv_events = [ev for ev in events if ev.get('conversation_id') == conv_id]
    #     conv_events.sort(key=lambda x: x.get('turn', 0))
    #     for ev in conv_events:
    #         print(ev)
    #     print()


    results = run_simulation(AGENTS, max_rounds=10, enable_knowledge_sharing=False)

