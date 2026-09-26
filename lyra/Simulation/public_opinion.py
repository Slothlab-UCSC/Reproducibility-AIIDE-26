import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from Clusters.cluster import cluster, individual_cluster

from typing import Dict, List, Tuple
import math


#----------------- Globals -------------------

LAMBDA_SOCIAL = 0.7   # weight on cluster mean vs. attitude when no consensus
BETA_STEP     = 0.6   # how far to move opinion toward target per round
UNC_DECAY     = 0.9   # base uncertainty decay rate when persuaded
ATT_ALPHA     = 0.1   # small drift of attitude toward opinion when no consensus
UNC_INCREASE  = 0.1   # uncertainty increase when resisting persuasion or in disagreement

#Prob thresholds
P_THRESH = 0.875

TAU = 15.0     # time constant for saturation
W_O  = -1.5     # bias: how "skeptical" the model starts
W_K = 1.2      # weight: few clusters
W_S = 2.5      # weight: stability (few changes)
W_T = 1.5      # weight: elapsed time

#----------------- Helper -------------------
def stats(clusters):
    stats = {}
    for cluster in clusters.clusters:
        stats[cluster.cluster_id] = {"mean_op": cluster.mean_opinion(), 
                                     "mean_at": cluster.mean_attitude(),  
                                     "var": cluster.variance_opinion(), 
                                     "size": cluster.size()}
    return stats

def nearest_cluster(opinion, stats):
    return min(stats.keys(), key=lambda cid: abs(opinion - stats[cid]["mean_op"]))

def public_opinion_strength(x_a, x_b, x_c):
    if x_a <= 1:
        f_a = 0
    elif x_a <= 10:
        f_a = x_a/10
    else:
        f_a = 1
    
    f_b = 1 / (1 + math.exp(24 * x_b - 6))

    f_c = 1 / (1 + math.exp(-12 * x_c + 6))
    
    return (f_a + f_b + f_c)/3

def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))

def mean_opinion_change(prev_ops, curr_ops, scale = .1):
    """
    Mean |Δopinion| normalized to [0,1].
    If prev_ops is None, return 0.5 (neutral).
    """
    if not prev_ops or not curr_ops:
        return 0.5
    print("Previous:")
    print(prev_ops)
    print("current:")
    print(curr_ops)
    deltas = []
    for aid, curr in curr_ops.items():
        prev = prev_ops.get(aid, curr)  # if new, treat as no change
        deltas.append(abs(curr - prev))
    if not deltas:
        return 0.5
    mean_abs = sum(deltas) / len(deltas)
    return (1 - math.exp(-mean_abs / max(scale, 1e-6)))

def public_opinion_prob(k, k_max, prev_opinions, curr_opinions, current_round):
    # cluster ammount
    s_k = 1 - min((k-1) / max(k_max-1, 1), 1)

    # Opinion stability
    delta_op = 1 - mean_opinion_change(prev_opinions, curr_opinions)
    # Time that has passed
    s_t = 1 - math.exp(-current_round / max(TAU, 1e-6))

    z = W_O + W_K * s_k + W_S * delta_op + W_T * s_t
    return sigmoid(z)

def analyze_conversations_for_agent(agent_id, conversation_events, cluster_agent_ids, agent_opinion=None):
    """
    Analyze conversation events to extract information relevant to an agent.
    
    Args:
        agent_id: ID of the agent to analyze
        conversation_events: List of conversation event dictionaries
        cluster_agent_ids: List of agent IDs in the same cluster
        agent_opinion: Current opinion of the agent (optional, for detecting contrasting opinions)
    
    Returns:
        Dictionary with:
        - agreement_ratio: Ratio of agreement/support events vs disagreement
        - avg_statement_opinion: Average opinion expressed in statements
        - contradictory_statements: Count of statements with opposing opinions
        - support_received: Count of support/agreement events received
        - has_conversations: Whether agent participated in conversations
        - contrasting_opinions: Count of opinions on opposite side of spectrum
        - like_minded_opinions: Count of opinions on same side of spectrum
        - challenges_received: Count of challenges received (by agent_id)
        - challenges_by_agent: Dict mapping agent_id to challenge count
        - agreements_by_agent: Dict mapping agent_id to agreement count
        - contrasting_ratio: Ratio of contrasting vs like-minded opinions
    """
    if not conversation_events:
        return {
            'agreement_ratio': 0.5,
            'avg_statement_opinion': None,
            'contradictory_statements': 0,
            'support_received': 0,
            'has_conversations': False,
            'contrasting_opinions': 0,
            'like_minded_opinions': 0,
            'challenges_received': 0,
            'challenges_by_agent': {},
            'agreements_by_agent': {},
            'contrasting_ratio': 0.0
        }
    
    # Filter events where agent is involved (as speaker or target) and in same cluster
    relevant_events = []
    for event in conversation_events:
        speaker = event.get('speaker')
        target = event.get('target')
        # Check if agent is involved and both are in same cluster
        if (speaker == agent_id or target == agent_id) and \
           speaker in cluster_agent_ids and \
           (target is None or target in cluster_agent_ids):
            relevant_events.append(event)
    
    if not relevant_events:
        return {
            'agreement_ratio': 0.5,
            'avg_statement_opinion': None,
            'contradictory_statements': 0,
            'support_received': 0,
            'has_conversations': False,
            'contrasting_opinions': 0,
            'like_minded_opinions': 0,
            'challenges_received': 0,
            'challenges_by_agent': {},
            'agreements_by_agent': {},
            'contrasting_ratio': 0.0
        }
    
    # Analyze event types
    agreement_count = 0
    support_count = 0
    disagreement_count = 0
    statement_opinions = []
    contradictory_count = 0
    support_received = 0
    contrasting_opinions = 0
    like_minded_opinions = 0
    challenges_received = 0
    challenges_by_agent = {}
    agreements_by_agent = {}
    
    # Determine agent's side of spectrum if opinion provided
    agent_side = None
    if agent_opinion is not None:
        agent_side = 1 if agent_opinion >= 0 else -1
    
    for event in relevant_events:
        event_type = event.get('type', '')
        statement_op = event.get('statement_opinion')
        speaker = event.get('speaker')
        target = event.get('target')
        
        # Count agreement/support patterns
        if event_type in ['agreement', 'support']:
            if target == agent_id:
                support_received += 1
                # Track agreements by specific agent
                if speaker not in agreements_by_agent:
                    agreements_by_agent[speaker] = 0
                agreements_by_agent[speaker] += 1
            if event_type == 'agreement':
                agreement_count += 1
            else:
                support_count += 1
        
        # Count disagreements
        if event_type == 'disagreement':
            disagreement_count += 1
        
        # Count challenges (directed at this agent)
        if event_type == 'challenge':
            if target == agent_id:
                challenges_received += 1
                # Track challenges by specific agent
                if speaker not in challenges_by_agent:
                    challenges_by_agent[speaker] = 0
                challenges_by_agent[speaker] += 1
        
        # Collect statement opinions and analyze contrasting vs like-minded
        if statement_op is not None:
            statement_opinions.append(statement_op)
            
            # Detect contrasting vs like-minded opinions (if we know agent's opinion)
            if agent_side is not None:
                statement_side = 1 if statement_op >= 0 else -1
                if statement_side != agent_side:
                    contrasting_opinions += 1
                else:
                    like_minded_opinions += 1
        
        # Count contradictory statements (opposite side of spectrum from each other)
        if statement_op is not None and len(statement_opinions) > 1:
            # Check if this statement is on opposite side from previous statements
            prev_avg = sum(statement_opinions[:-1]) / len(statement_opinions[:-1])
            if (prev_avg >= 0 and statement_op < 0) or (prev_avg < 0 and statement_op >= 0):
                contradictory_count += 1
    
    total_interactions = agreement_count + support_count + disagreement_count
    agreement_ratio = (agreement_count + support_count) / max(total_interactions, 1) if total_interactions > 0 else 0.5
    
    avg_statement_opinion = sum(statement_opinions) / len(statement_opinions) if statement_opinions else None
    
    # Calculate contrasting ratio
    total_opinions = contrasting_opinions + like_minded_opinions
    contrasting_ratio = contrasting_opinions / max(total_opinions, 1) if total_opinions > 0 else 0.0
    
    return {
        'agreement_ratio': agreement_ratio,
        'avg_statement_opinion': avg_statement_opinion,
        'contradictory_statements': contradictory_count,
        'support_received': support_received,
        'has_conversations': True,
        'total_interactions': len(relevant_events),
        'contrasting_opinions': contrasting_opinions,
        'like_minded_opinions': like_minded_opinions,
        'challenges_received': challenges_received,
        'challenges_by_agent': challenges_by_agent,
        'agreements_by_agent': agreements_by_agent,
        'contrasting_ratio': contrasting_ratio
    }

#----------------- Helper -------------------

def describe_agent_update(agent, original_opinion, original_attitude, original_uncertainty,
                          cluster_size, cluster_variance, cluster_mean_opinion, cluster_mean_attitude,
                          public_formed, opinion_strength=None, update_type=None, cluster_agents=None):
    """
    Generate a text description of an agent's thought process when updating values.
    
    Args:
        agent: The agent being updated
        original_opinion: Opinion before update
        original_attitude: Attitude before update
        original_uncertainty: Uncertainty before update
        cluster_size: Size of the cluster the agent is responding to
        cluster_variance: Variance of opinions in the cluster
        cluster_mean_opinion: Mean opinion of the cluster
        cluster_mean_attitude: Mean attitude of the cluster
        public_formed: Whether public opinion has formed
        opinion_strength: Public opinion strength (if public opinion formed)
        update_type: Type of update ('high_uncertainty', 'moderate_strength', 'high_strength', 'no_consensus', 'resisted')
    
    Returns:
        A text description of the agent's reasoning
    """
    agent_id = agent.agent_id
    new_opinion = agent.opinion
    new_attitude = agent.attitude
    new_uncertainty = agent.uncertainty
    
    opinion_change = abs(new_opinion - original_opinion)
    attitude_change = abs(new_attitude - original_attitude)
    uncertainty_change = new_uncertainty - original_uncertainty
    
    # Format values for display
    def fmt(v):
        return f"{v:.3f}"
    
    # Generate cluster description with agent IDs
    def get_cluster_desc(size, agents_list, current_agent_id):
        if agents_list is None:
            return f"{size} others" if size > 1 else "another agent"
        
        # Filter out the current agent
        other_agents = [a for a in agents_list if a.agent_id != current_agent_id]
        
        if len(other_agents) == 0:
            # Fallback to size if we can't get agent list
            return f"{size} others" if size > 1 else "another agent"
        elif len(other_agents) == 1:
            return other_agents[0].agent_id
        elif len(other_agents) == 2:
            return f"{other_agents[0].agent_id} and {other_agents[1].agent_id}"
        elif len(other_agents) <= 4:
            names = ", ".join([a.agent_id for a in other_agents[:-1]])
            return f"{names}, and {other_agents[-1].agent_id}"
        else:
            return f"{len(other_agents)} others"
    
    cluster_desc = get_cluster_desc(cluster_size, cluster_agents, agent_id)
    
    if update_type == 'high_uncertainty':
        return (f"{agent_id}, feeling uncertain ({fmt(original_uncertainty)}), sees {cluster_desc} "
                f"converging around {fmt(cluster_mean_opinion)}. "
                f"Without strong convictions, he adopts this position "
                f"(opinion {fmt(original_opinion)} → {fmt(new_opinion)}, "
                f"attitude {fmt(original_attitude)} → {fmt(new_attitude)})")
    
    elif update_type == 'resisted':
        strength_desc = "insufficient" if opinion_strength < 0.4 else "not strong enough"
        return (f"{agent_id} notices {cluster_desc} holding opinion {fmt(cluster_mean_opinion)}, "
                f"but finds the collective pressure ({fmt(opinion_strength)}) {strength_desc}. "
                f"He holds firm at {fmt(original_opinion)}")
    
    elif update_type == 'moderate_strength':
        return (f"{agent_id} is swayed by {cluster_desc} expressing {fmt(cluster_mean_opinion)}. "
                f"The collective momentum ({fmt(opinion_strength)}) feels like a natural shift. "
                f"He adjusts both his stated view ({fmt(original_opinion)} → {fmt(new_opinion)}) "
                f"and internal stance ({fmt(original_attitude)} → {fmt(new_attitude)})")
    
    elif update_type == 'high_strength':
        return (f"{agent_id} feels the weight of public opinion ({fmt(opinion_strength)}) from "
                f"{cluster_desc} at {fmt(cluster_mean_opinion)}. "
                f"He aligns his public stance ({fmt(original_opinion)} → {fmt(new_opinion)}) "
                f"while privately maintaining {fmt(original_attitude)}")
    
    elif update_type == 'no_consensus_persuaded':
        # Determine direction of opinion change
        if new_opinion > original_opinion:
            direction = "increases"
        elif new_opinion < original_opinion:
            direction = "decreases"
        else:
            direction = "unchanged"
        
        change_magnitude = abs(new_opinion - original_opinion)
        change_desc = "slightly" if change_magnitude < 0.1 else "noticeably"
        
        if direction == "unchanged":
            return (f"{agent_id} considers {cluster_desc} at {fmt(cluster_mean_opinion)}, "
                    f"weighing it against his own stance ({fmt(original_attitude)}). "
                    f"He stays at {fmt(original_opinion)} but feels more certain "
                    f"({fmt(original_uncertainty)} → {fmt(new_uncertainty)})")
        else:
            return (f"{agent_id} considers {cluster_desc} at {fmt(cluster_mean_opinion)}, "
                    f"weighing it against his own stance ({fmt(original_attitude)}). "
                    f"His opinion {change_desc} {direction} ({fmt(original_opinion)} → {fmt(new_opinion)}) "
                    f"and he feels more certain ({fmt(original_uncertainty)} → {fmt(new_uncertainty)})")
    
    elif update_type == 'no_consensus_disagreement':
        opinion_diff = abs(cluster_mean_opinion - original_opinion)
        conflict_desc = "strongly conflicts" if opinion_diff > 0.5 else "conflicts"
        
        return (f"{agent_id} sees {cluster_desc} at {fmt(cluster_mean_opinion)}, "
                f"which {conflict_desc} with his view ({fmt(original_opinion)}). "
                f"The confident disagreement leaves him more uncertain "
                f"({fmt(original_uncertainty)} → {fmt(new_uncertainty)})")
    
    elif update_type == 'no_consensus_aligned':
        # Determine direction of opinion change
        if new_opinion > original_opinion:
            direction = "increases"
        elif new_opinion < original_opinion:
            direction = "decreases"
        else:
            direction = "unchanged"
        
        change_magnitude = abs(new_opinion - original_opinion)
        change_desc = "slightly" if change_magnitude < 0.05 else "gradually"
        
        if direction == "unchanged":
            return (f"{agent_id} finds alignment with {cluster_desc} at {fmt(cluster_mean_opinion)}. "
                    f"He remains at {fmt(original_opinion)} and feels slightly more confident "
                    f"({fmt(original_uncertainty)} → {fmt(new_uncertainty)})")
        else:
            return (f"{agent_id} finds alignment with {cluster_desc} at {fmt(cluster_mean_opinion)}. "
                    f"His opinion {change_desc} {direction} ({fmt(original_opinion)} → {fmt(new_opinion)}) "
                    f"and he feels slightly more confident ({fmt(original_uncertainty)} → {fmt(new_uncertainty)})")
    
    else:
        # Generic fallback
        changes = []
        if opinion_change > 0.01:
            changes.append(f"opinion {fmt(original_opinion)} -> {fmt(new_opinion)}")
        if attitude_change > 0.01:
            changes.append(f"attitude {fmt(original_attitude)} -> {fmt(new_attitude)}")
        if abs(uncertainty_change) > 0.01:
            direction = "increases" if uncertainty_change > 0 else "decreases"
            changes.append(f"uncertainty {fmt(original_uncertainty)} -> {fmt(new_uncertainty)} ({direction})")
        
        if changes:
            return f"{agent_id} updates: {', '.join(changes)} based on cluster of {cluster_size} agents"
        else:
            return f"{agent_id} maintains his position despite cluster of {cluster_size} agents"


# Main function
def public_opinion_main(agents, cluster_obj, current_round, curr_opinions, prev_opinons=None, conversation_events=None):
    """
    Implements:
    - If public opinion not formed: move opinion toward blend of cluster mean and own attitude.
    - If public opinion formed: use strength thresholds; update with step-size.
    
    Args:
        agents: List of agents
        cluster_obj: Cluster object with agent assignments
        current_round: Current round number
        curr_opinions: Dictionary of current opinions {agent_id: opinion}
        prev_opinons: Dictionary of previous opinions (optional)
        conversation_events: List of conversation events from this round (optional)
    """

    assignments = cluster_obj.as_assignments()
    stat = stats(cluster_obj)

    public_opinion_p = public_opinion_prob(
        k = max(0, len(assignments)),
        k_max= len(cluster_obj.agents),
        prev_opinions= prev_opinons,
        curr_opinions= curr_opinions,
        current_round= current_round
    )
    print("public opinion value:" + str(public_opinion_p))
    public_formed = public_opinion_p > P_THRESH

    largest_cid = max(assignments.keys(), key=lambda c: len(assignments[c])) if assignments else None

    for agent in agents:
        if not assignments:
            continue

        # Store original values to detect changes
        original_opinion = agent.opinion
        original_attitude = agent.attitude
        original_uncertainty = agent.uncertainty
        
        # ---------- If consensus formed ----------
        # Change high uncertainty individuals if public opinion has been formed
        if public_formed and agent.uncertainty > 0.8:
            largest_group_opinion = stat[largest_cid]["mean_op"]
            largest_group_attitude= stat[largest_cid]["mean_at"]
            cluster_size = stat[largest_cid]["size"]
            cluster_variance = stat[largest_cid]["var"]
            
            agent.update_opinion(largest_group_opinion, 1)
            agent.update_attitude(largest_group_attitude, 1)
            
            description = describe_agent_update(
                agent, original_opinion, original_attitude, original_uncertainty,
                cluster_size, cluster_variance, largest_group_opinion, largest_group_attitude,
                public_formed, update_type='high_uncertainty',
                cluster_agents=assignments.get(largest_cid, [])
            )
            print(description)
            continue
        
        new_cid = nearest_cluster(agent.opinion, stat)
        mean_op = stat[new_cid]["mean_op"]
        mean_at = stat[new_cid]["mean_at"]
        x_a = stat[new_cid]["size"]
        x_b = stat[new_cid]["var"]
        x_c = abs(agent.attitude - agent.opinion) / 2

        if public_formed:
            op_str = public_opinion_strength(x_a, x_b, x_c)

            threshold1 = 1 - agent.uncertainty
            threshold2 = max(.6, threshold1)
            
            if op_str < threshold1:
                # Strength is too weak to change minds
                # Since not being influenced, apply stronger misalignment correction toward bias/attitude
                opinion_bias_diff = abs(agent.opinion - agent.bias)
                opinion_attitude_diff = abs(agent.opinion - agent.attitude)
                
                if opinion_bias_diff > 0.2 or opinion_attitude_diff > 0.2:
                    # Significant misalignment - skew more strongly toward bias/attitude when resisting
                    if opinion_bias_diff > opinion_attitude_diff:
                        correction_strength = min(opinion_bias_diff / 2.0, 0.25)  # Stronger correction when resisting
                        agent.opinion = (1 - correction_strength) * agent.opinion + correction_strength * agent.bias
                    else:
                        correction_strength = min(opinion_attitude_diff / 2.0, 0.25)  # Stronger correction when resisting
                        agent.opinion = (1 - correction_strength) * agent.opinion + correction_strength * agent.attitude
                
                description = describe_agent_update(
                    agent, original_opinion, original_attitude, original_uncertainty,
                    x_a, x_b, mean_op, mean_at, public_formed, 
                    opinion_strength=op_str, update_type='resisted',
                    cluster_agents=assignments.get(new_cid, [])
                )
                print(description)
            elif op_str < threshold2:
                # Moderate strength - change opinion and attitude
                # Apply misalignment correction before updating
                target_opinion = mean_op
                opinion_bias_diff = abs(target_opinion - agent.bias)
                opinion_attitude_diff = abs(target_opinion - agent.attitude)
                
                if opinion_bias_diff > 0.2 or opinion_attitude_diff > 0.2:
                    # Significant misalignment - skew slightly toward bias/attitude
                    if opinion_bias_diff > opinion_attitude_diff:
                        correction_strength = min(opinion_bias_diff / 2.0, 0.15)
                        target_opinion = (1 - correction_strength) * target_opinion + correction_strength * agent.bias
                    else:
                        correction_strength = min(opinion_attitude_diff / 2.0, 0.15)
                        target_opinion = (1 - correction_strength) * target_opinion + correction_strength * agent.attitude
                
                agent.update_opinion(target_opinion, 1)
                agent.update_attitude(mean_at, 1)
                
                description = describe_agent_update(
                    agent, original_opinion, original_attitude, original_uncertainty,
                    x_a, x_b, mean_op, mean_at, public_formed,
                    opinion_strength=op_str, update_type='moderate_strength',
                    cluster_agents=assignments.get(new_cid, [])
                )
                print(description)
            else:
                # High strength - change opinion but keep attitude
                # Apply misalignment correction before updating
                target_opinion = mean_op
                opinion_bias_diff = abs(target_opinion - agent.bias)
                opinion_attitude_diff = abs(target_opinion - agent.attitude)
                
                if opinion_bias_diff > 0.2 or opinion_attitude_diff > 0.2:
                    # Significant misalignment - skew slightly toward bias/attitude
                    if opinion_bias_diff > opinion_attitude_diff:
                        correction_strength = min(opinion_bias_diff / 2.0, 0.15)
                        target_opinion = (1 - correction_strength) * target_opinion + correction_strength * agent.bias
                    else:
                        correction_strength = min(opinion_attitude_diff / 2.0, 0.15)
                        target_opinion = (1 - correction_strength) * target_opinion + correction_strength * agent.attitude
                
                agent.update_opinion(target_opinion, 1)
                
                description = describe_agent_update(
                    agent, original_opinion, original_attitude, original_uncertainty,
                    x_a, x_b, mean_op, mean_at, public_formed,
                    opinion_strength=op_str, update_type='high_strength',
                    cluster_agents=assignments.get(new_cid, [])
                )
                print(description) 

        # ---------- If consensus NOT formed ----------
        else:
            new_cid = nearest_cluster(agent.opinion, stat)
            mean_op = stat[new_cid]["mean_op"]
            mean_at = stat[new_cid]["mean_at"]
            cluster_size = stat[new_cid]["size"]
            cluster_variance = stat[new_cid]["var"]
            
            # Get all agents in the cluster for deeper analysis
            cluster_agent_list = assignments.get(new_cid, [])
            cluster_agent_ids = [a.agent_id for a in cluster_agent_list]
            
            # Analyze conversations for this agent
            conv_analysis = analyze_conversations_for_agent(
                agent.agent_id, 
                conversation_events, 
                cluster_agent_ids,
                agent.opinion
            ) if conversation_events else None
            
            # Check if agent is isolated (alone in cluster or no cluster)
            is_isolated = False
            if not cluster_agent_list:
                is_isolated = True
            else:
                # Filter out the current agent to see if there are others
                other_agents = [a for a in cluster_agent_list if a.agent_id != agent.agent_id]
                if len(other_agents) == 0:
                    is_isolated = True
            
            # If isolated, increase uncertainty and skip further processing
            # But limit the increase to prevent runaway uncertainty for frequently isolated agents
            if is_isolated:
                # Reduce isolation uncertainty increase to be more gradual
                agent.uncertainty = min(1.0, agent.uncertainty + UNC_INCREASE * 0.3)  # Reduced from 0.5
                description = describe_agent_update(
                    agent, original_opinion, original_attitude, original_uncertainty,
                    cluster_size, cluster_variance, mean_op, mean_at,
                    public_formed, update_type='no_consensus_disagreement',
                    cluster_agents=cluster_agent_list
                )
                print(description)
                continue
            
            # Analyze cluster opinions to detect opposing ideas and alignment
            cluster_opinions = [a.opinion for a in cluster_agent_list if a.agent_id != agent.agent_id]
            cluster_attitudes = [a.attitude for a in cluster_agent_list if a.agent_id != agent.agent_id]
            
            if not cluster_opinions:
                # Shouldn't happen if not isolated, but safety check
                continue
            
            # Calculate how many opinions oppose the agent's view
            # An opinion "opposes" if it's on the opposite side of the spectrum
            agent_side = 1 if agent.opinion >= 0 else -1
            opposing_count = sum(1 for op in cluster_opinions if (op >= 0 and agent_side < 0) or (op < 0 and agent_side > 0))
            opposing_ratio = opposing_count / len(cluster_opinions) if cluster_opinions else 0
            
            # Calculate contradictory ideas within the cluster
            # Measure diversity/contradiction by:
            # 1. High variance (opinions spread out)
            # 2. Opinions spanning both sides of the spectrum
            # 3. Large range of opinions
            # 4. Contradictory statements in conversations
            if len(cluster_opinions) > 1:
                opinion_range = max(cluster_opinions) - min(cluster_opinions)
                # Check if opinions span both sides (contradictory)
                has_positive = any(op > 0 for op in cluster_opinions)
                has_negative = any(op < 0 for op in cluster_opinions)
                spans_both_sides = has_positive and has_negative
                
                # Contradictory ideas: high variance OR spans both sides with large range
                contradictory_factor = 0.0
                if cluster_variance > 0.4:  # High variance indicates diverse opinions
                    contradictory_factor += 0.5
                if spans_both_sides and opinion_range > 0.8:  # Large range across both sides
                    contradictory_factor += 0.5
                elif spans_both_sides and opinion_range > 0.5:  # Moderate range across both sides
                    contradictory_factor += 0.3
            else:
                contradictory_factor = 0.0
            
            # Add contradictory statements from conversations
            if conv_analysis and conv_analysis['has_conversations']:
                # More contradictory statements in conversations = more uncertainty
                if conv_analysis['contradictory_statements'] > 2:
                    contradictory_factor = min(1.0, contradictory_factor + 0.4)
                elif conv_analysis['contradictory_statements'] > 0:
                    contradictory_factor = min(1.0, contradictory_factor + 0.2)
            
            # Calculate alignment with agent's bias/attitude
            # Check how close cluster opinions are to agent's bias and attitude
            bias_alignment = 1.0 - min(abs(mean_op - agent.bias) / 2.0, 1.0)  # 1.0 = perfect alignment, 0.0 = opposite
            attitude_alignment = 1.0 - min(abs(mean_op - agent.attitude) / 2.0, 1.0)
            overall_alignment = (bias_alignment + attitude_alignment) / 2.0
            
            # Calculate average uncertainty and certainty in the cluster
            avg_cluster_uncertainty = sum(a.uncertainty for a in cluster_agent_list) / len(cluster_agent_list)
            cluster_certainty = 1.0 - avg_cluster_uncertainty
            
            # Determine influence strength based on:
            # 1. Agent's uncertainty (higher uncertainty = more influenceable)
            # 2. Alignment with bias/attitude (better alignment = more influence)
            # 3. Opposing ideas (too many opposing = move away)
            # 4. Conversation patterns (agreement/support received)
            uncertainty_factor = agent.uncertainty  # Higher uncertainty = more conforming
            alignment_factor = overall_alignment  # Better alignment = more influence
            
            # Adjust based on conversations
            conversation_influence = 1.0
            conversation_target_adjustment = None  # Will be set if conversations strongly influence direction
            
            if conv_analysis and conv_analysis['has_conversations']:
                # Rule 1: Too many contrasting opinions → change opinion in opposite direction
                if conv_analysis['contrasting_ratio'] > 0.7 and conv_analysis['contrasting_opinions'] >= 3:
                    # Move away from cluster mean, toward opposite direction
                    # Calculate opposite direction from cluster mean
                    opposite_direction = -mean_op if mean_op != 0 else (1.0 if agent.opinion < 0 else -1.0)
                    # Blend: move toward opposite direction and own attitude/bias
                    away_target = agent.attitude if abs(agent.attitude - agent.opinion) < abs(agent.bias - agent.opinion) else agent.bias
                    conversation_target_adjustment = 0.4 * opposite_direction + 0.6 * away_target
                    conversation_influence = 0.6  # Reduce influence strength when moving away
                
                # Rule 2: Like-minded opinions → slightly converge toward group
                elif conv_analysis['contrasting_ratio'] < 0.3 and conv_analysis['like_minded_opinions'] >= 2:
                    # Gradual convergence: blend current opinion with cluster mean
                    if conv_analysis['avg_statement_opinion'] is not None:
                        # Use both cluster mean and statement opinions, but keep agent's current position
                        group_target = 0.6 * mean_op + 0.4 * conv_analysis['avg_statement_opinion']
                        # Blend: 70% current opinion, 30% toward group (gradual convergence)
                        conversation_target_adjustment = 0.7 * agent.opinion + 0.3 * group_target
                    else:
                        # Blend: 70% current opinion, 30% toward cluster mean (gradual convergence)
                        conversation_target_adjustment = 0.7 * agent.opinion + 0.3 * mean_op
                    conversation_influence = 0.8  # Moderate influence for gradual convergence
                
                # Rule 3: Lots of challenges by a specific agent → change opinion away from group
                if conv_analysis['challenges_by_agent']:
                    max_challenges = max(conv_analysis['challenges_by_agent'].values())
                    challenging_agent = max(conv_analysis['challenges_by_agent'], key=conv_analysis['challenges_by_agent'].get)
                    if max_challenges >= 3:  # 3+ challenges from same agent
                        # Move away from cluster mean and that agent's influence
                        # Find that agent's opinion if possible
                        challenging_agent_op = None
                        for a in cluster_agent_list:
                            if a.agent_id == challenging_agent:
                                challenging_agent_op = a.opinion
                                break
                        
                        if challenging_agent_op is not None:
                            # Move away from challenging agent's opinion
                            away_from_challenger = -challenging_agent_op if challenging_agent_op != 0 else (1.0 if agent.opinion < 0 else -1.0)
                            away_target = agent.attitude if abs(agent.attitude - agent.opinion) < abs(agent.bias - agent.opinion) else agent.bias
                            # Override previous adjustment if challenges are strong
                            conversation_target_adjustment = 0.3 * mean_op + 0.4 * away_from_challenger + 0.3 * away_target
                            conversation_influence = 0.5  # Strong push away
                
                # Rule 4: Lots of agreement from an agent → slightly converge toward cluster's opinion
                if conv_analysis['agreements_by_agent']:
                    max_agreements = max(conv_analysis['agreements_by_agent'].values())
                    agreeing_agent = max(conv_analysis['agreements_by_agent'], key=conv_analysis['agreements_by_agent'].get)
                    if max_agreements >= 3:  # 3+ agreements from same agent
                        # Find that agent's opinion
                        agreeing_agent_op = None
                        for a in cluster_agent_list:
                            if a.agent_id == agreeing_agent:
                                agreeing_agent_op = a.opinion
                                break
                        
                        if agreeing_agent_op is not None:
                            # Gradually converge: blend current opinion with agreeing agent and cluster mean
                            group_target = 0.5 * mean_op + 0.5 * agreeing_agent_op
                            if conversation_target_adjustment is None:
                                # Blend: 75% current opinion, 25% toward group (gradual convergence)
                                conversation_target_adjustment = 0.75 * agent.opinion + 0.25 * group_target
                            else:
                                # Blend existing adjustment with gradual convergence
                                conversation_target_adjustment = 0.7 * conversation_target_adjustment + 0.3 * (0.75 * agent.opinion + 0.25 * group_target)
                            conversation_influence = max(conversation_influence, 0.85)  # Moderate influence for gradual convergence
                
                # General agreement/support patterns
                if conversation_target_adjustment is None:
                    # High agreement/support in conversations slightly increases influence (but still gradual)
                    if conv_analysis['agreement_ratio'] > 0.7:
                        conversation_influence = 1.1  # Slight increase for gradual convergence
                    elif conv_analysis['agreement_ratio'] < 0.3:
                        conversation_influence = 0.8  # Less influence when disagreement
                    
                    # Use statement opinions if available and aligned
                    if conv_analysis['avg_statement_opinion'] is not None:
                        statement_alignment = 1.0 - min(abs(conv_analysis['avg_statement_opinion'] - agent.attitude) / 2.0, 1.0)
                        if statement_alignment > 0.6:
                            # Statements align with agent's attitude - more influence
                            conversation_influence *= (1.0 + statement_alignment * 0.2)
            
            # If conversation strongly influences direction, use that target
            if conversation_target_adjustment is not None:
                target = conversation_target_adjustment
                # Determine update type based on direction
                if abs(target - mean_op) > abs(target - agent.opinion):
                    update_type = 'no_consensus_disagreement'
                    influence_strength = BETA_STEP * conversation_influence * 0.7  # Moderate strength when moving away
                else:
                    update_type = 'no_consensus_persuaded'
                    # Use reduced influence strength for gradual convergence (target already includes current opinion blend)
                    influence_strength = BETA_STEP * conversation_influence * 0.6  # Gradual convergence
            # If too many opposing ideas (high opposing ratio AND high variance), agent moves away
            elif opposing_ratio > 0.6 and cluster_variance > 0.3:
                # Too many conflicting ideas - agent becomes more certain of their own position
                # Move opinion slightly away from cluster mean, toward own attitude/bias
                away_from_cluster = agent.attitude if abs(agent.attitude - agent.opinion) < abs(agent.bias - agent.opinion) else agent.bias
                target = 0.3 * mean_op + 0.7 * away_from_cluster
                influence_strength = 0.2  # Weak influence, moving away
                update_type = 'no_consensus_disagreement'
            elif uncertainty_factor > 0.6:
                # High uncertainty - more likely to conform to cluster
                # Weight cluster mean more heavily
                # Use statement opinions from conversations if available
                if conv_analysis and conv_analysis['avg_statement_opinion'] is not None:
                    # Blend cluster mean with statement opinions from conversations
                    target = 0.5 * mean_op + 0.3 * conv_analysis['avg_statement_opinion'] + 0.2 * agent.attitude
                else:
                    target = 0.7 * mean_op + 0.3 * agent.attitude
                influence_strength = BETA_STEP * (0.5 + uncertainty_factor * 0.5) * conversation_influence
                update_type = 'no_consensus_persuaded'
            elif alignment_factor > 0.6:
                # Good alignment with bias/attitude - be influenced by cluster
                # Weight based on alignment strength
                # Use statement opinions from conversations if available
                if conv_analysis and conv_analysis['avg_statement_opinion'] is not None:
                    # Blend with statement opinions
                    target = (0.3 + alignment_factor * 0.2) * mean_op + 0.2 * conv_analysis['avg_statement_opinion'] + (0.3 - alignment_factor * 0.3) * agent.attitude
                else:
                    target = (0.4 + alignment_factor * 0.3) * mean_op + (0.3 - alignment_factor * 0.3) * agent.attitude
                influence_strength = BETA_STEP * (0.4 + alignment_factor * 0.4) * conversation_influence
                update_type = 'no_consensus_persuaded'
            else:
                # Default: blend of cluster mean and own attitude
                # Use statement opinions from conversations if available
                if conv_analysis and conv_analysis['avg_statement_opinion'] is not None:
                    target = 0.4 * mean_op + 0.3 * conv_analysis['avg_statement_opinion'] + 0.3 * agent.attitude
                else:
                    target = LAMBDA_SOCIAL * mean_op + (1 - LAMBDA_SOCIAL) * agent.attitude
                influence_strength = BETA_STEP * conversation_influence
                update_type = 'no_consensus_aligned'
            
            # Check for misalignment between opinion and bias/attitude
            # If opinion doesn't align with bias or attitude, skew it slightly toward them
            opinion_bias_diff = abs(agent.opinion - agent.bias)
            opinion_attitude_diff = abs(agent.opinion - agent.attitude)
            
            # Calculate misalignment strength (higher = more misaligned)
            bias_misalignment = opinion_bias_diff / 2.0  # Normalize to [0, 1]
            attitude_misalignment = opinion_attitude_diff / 2.0  # Normalize to [0, 1]
            max_misalignment = max(bias_misalignment, attitude_misalignment)
            
            # If there's significant misalignment, add correction toward bias/attitude
            if max_misalignment > 0.2:  # Threshold: opinion differs by more than 0.4 from bias/attitude
                # Determine which to correct toward (bias or attitude)
                if opinion_bias_diff > opinion_attitude_diff:
                    # Bias is more misaligned, correct toward bias
                    correction_target = agent.bias
                    correction_strength = bias_misalignment * 0.15  # Gradual correction (15% of misalignment)
                else:
                    # Attitude is more misaligned, correct toward attitude
                    correction_target = agent.attitude
                    correction_strength = attitude_misalignment * 0.15  # Gradual correction
                
                # Blend the calculated target with the correction target
                # More misalignment = stronger correction
                target = (1 - correction_strength) * target + correction_strength * correction_target
            
            # Update opinion based on calculated target and influence strength
            new_opinion = (1 - influence_strength) * agent.opinion + influence_strength * target
            
            # Update attitude - drift slightly toward opinion
            agent.attitude = (1 - ATT_ALPHA) * agent.attitude + ATT_ALPHA * agent.opinion
            
            # Check if opinion changed significantly
            opinion_change = abs(new_opinion - agent.opinion)
            agent.opinion = new_opinion
            
            # Update uncertainty based on interaction type and cluster dynamics
            if update_type == 'no_consensus_disagreement':
                # Too many opposing ideas - uncertainty increases (but more gradually)
                disagreement_factor = min(opposing_ratio * 1.5, 1.0)
                # Also increase if there are contradictory ideas in the cluster
                total_uncertainty_increase = disagreement_factor + contradictory_factor
                # Add uncertainty from conversation disagreements
                if conv_analysis and conv_analysis['has_conversations']:
                    if conv_analysis['agreement_ratio'] < 0.3:  # Low agreement in conversations
                        total_uncertainty_increase = min(1.0, total_uncertainty_increase + 0.2)  # Reduced from 0.3
                # Cap the increase to prevent runaway uncertainty (max 0.05 per round for disagreement)
                max_increase = min(total_uncertainty_increase, 0.5)  # Cap at 50% of disagreement factor
                agent.uncertainty = min(1.0, agent.uncertainty + UNC_INCREASE * max_increase)
            elif update_type == 'no_consensus_persuaded':
                # Being persuaded - uncertainty decreases
                # But if there are contradictory ideas, decrease less (or even increase slightly)
                decay_factor = UNC_DECAY
                if alignment_factor > 0.6:
                    decay_factor *= (0.85 + alignment_factor * 0.1)  # More decay when aligned
                if uncertainty_factor > 0.6:
                    decay_factor *= 0.9  # More decay when highly uncertain
                
                # Adjust based on conversation support
                if conv_analysis and conv_analysis['has_conversations']:
                    # High support/agreement in conversations increases certainty
                    if conv_analysis['support_received'] > 2 and conv_analysis['agreement_ratio'] > 0.6:
                        decay_factor *= 0.85  # More decay (more certainty) when supported
                    # Contradictory statements reduce certainty gain
                    if conv_analysis['contradictory_statements'] > 1:
                        decay_factor = min(1.0, decay_factor + 0.15)  # Less decay (less certainty gain)
                
                # If there are contradictory ideas, reduce the decay effect
                if contradictory_factor > 0.3:
                    # Contradictory ideas make the agent less certain even when persuaded
                    decay_factor = min(1.0, decay_factor + contradictory_factor * 0.2)
                    # If very contradictory, actually increase uncertainty slightly
                    if contradictory_factor > 0.7:
                        agent.uncertainty = min(1.0, agent.uncertainty * decay_factor + UNC_INCREASE * 0.2)
                    else:
                        agent.uncertainty *= decay_factor
                else:
                    agent.uncertainty *= decay_factor
            else:  # no_consensus_aligned
                # Aligned with cluster - slight uncertainty decrease
                # But if there are contradictory ideas, uncertainty may increase instead
                if contradictory_factor > 0.5:
                    # Many contradictory ideas even in "aligned" cluster increases uncertainty (but more gradually)
                    # Reduce the increase rate to prevent runaway uncertainty
                    increase_amount = UNC_INCREASE * contradictory_factor * 0.3  # Reduced from 0.5
                    agent.uncertainty = min(1.0, agent.uncertainty + increase_amount)
                else:
                    # Adjust based on conversations
                    if conv_analysis and conv_analysis['has_conversations']:
                        # High agreement in conversations increases certainty
                        if conv_analysis['agreement_ratio'] > 0.7:
                            agent.uncertainty *= (UNC_DECAY + 0.1)  # More certainty
                        # Contradictory statements reduce certainty (but don't increase as much)
                        elif conv_analysis['contradictory_statements'] > 1:
                            # In aligned case, contradictory statements should only slightly increase uncertainty
                            # or just prevent decrease, not cause large increases
                            agent.uncertainty = min(1.0, agent.uncertainty + UNC_INCREASE * 0.1)  # Reduced from 0.2
                        else:
                            agent.uncertainty *= (UNC_DECAY + 0.05)
                    else:
                        agent.uncertainty *= (UNC_DECAY + 0.05)
            
            description = describe_agent_update(
                agent, original_opinion, original_attitude, original_uncertainty,
                cluster_size, cluster_variance, mean_op, mean_at,
                public_formed, update_type=update_type,
                cluster_agents=cluster_agent_list
            )
            print(description)

        # Clamp values
        agent.opinion  = max(-1.0, min(1.0, agent.opinion))
        agent.attitude = max(-1.0, min(1.0, agent.attitude))
        agent.uncertainty = max(0.0, min(1.0, agent.uncertainty))

    return public_formed
        