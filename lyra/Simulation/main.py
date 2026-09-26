import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from Simulation.simulation import run_simulation, format_conversation_to_text
from Simulation.llm import generate_conversation_with_llm
from Simulation.config import TOPIC, AGENTS

# Use agents from config.py
agents = AGENTS

# Print agent information
print("=" * 80)
print("AGENT INFORMATION")
print("=" * 80)
for agent in agents:
    print(f"\nAgent: {agent.agent_id}")
    print(f"  Opinion: {agent.opinion:.3f}")
    print(f"  Attitude: {agent.attitude:.3f}")
    print(f"  Uncertainty: {agent.uncertainty:.3f}")
    print(f"  Bias: {agent.bias:.3f}")
    print(f"  Public Compliance Threshold: {agent.public_compliance_threshold:.3f}")
    print(f"  Private Acceptance Threshold: {agent.private_acceptance_threshold:.3f}")
    # Print log file path if it exists
    if hasattr(agent, 'log_path') and agent.log_path:
        print(f"  Log File: {agent.log_path}")
print("=" * 80)

results = run_simulation(agents, max_rounds=10, enable_knowledge_sharing=False)

# Display conversations from all rounds
if 'all_events' in results and results['all_events']:
    print("\n" + "=" * 80)
    print("CONVERSATIONS")
    print("=" * 80)
    
    # Group events by round
    from collections import defaultdict
    events_by_round = defaultdict(list)
    for event in results['all_events']:
        round_num = event.get('round', 0)
        events_by_round[round_num].append(event)
    
    # Display conversations organized by round
    for round_num in sorted(events_by_round.keys()):
        round_events = events_by_round[round_num]
        
        print(f"\n{'=' * 80}")
        print(f"ROUND {round_num} CONVERSATIONS")
        print(f"{'=' * 80}")
        
        # Generate LLM, template, and raw versions for this round
        llm_conversations = generate_conversation_with_llm(round_events, TOPIC)
        template_conversations = format_conversation_to_text(round_events)
        
        # Set up directory for logging LLM conversations
        interactions_dir = os.path.join(ROOT, "Simulation", "Interactions")
        round_dir = os.path.join(interactions_dir, f"round-{round_num}")
        os.makedirs(round_dir, exist_ok=True)
        
        # Group events by conversation for this round
        events_by_conv = defaultdict(list)
        for event in round_events:
            conv_id = event.get('conversation_id', 0)
            events_by_conv[conv_id].append(event)
        
        for conv_id in sorted(events_by_conv.keys()):
            conv_events = events_by_conv[conv_id]
            conv_events.sort(key=lambda x: x.get('turn', 0))
            
            # LLM-generated version
            if conv_id in llm_conversations:
                llm_text = llm_conversations[conv_id]
                print(llm_text)
                
                # Log LLM conversation to file
                llm_file_path = os.path.join(round_dir, f"conversation-{conv_id}_llm.txt")
                with open(llm_file_path, "w", encoding="utf-8") as llm_file:
                    llm_file.write(llm_text)
            else:
                print(f"\n=== Conversation {conv_id} (Round {round_num}) ===\n[LLM version not available]")
            
            # # Template-based version
            # print("\n--- Template-Based Version ---")
            # if conv_id in template_conversations:
            #     print(template_conversations[conv_id])
            # else:
            #     print("[No template version available]")
            
            # # Raw dictionary version
            # print("\n--- Raw Dictionary Version ---")
            # for ev in conv_events:
            #     print(ev)
            print()
else:
    print("\nNo conversation events found in simulation results.")