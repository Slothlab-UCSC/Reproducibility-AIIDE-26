import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from Agent.agent import Agent

from collections import defaultdict
import random

ALLOWED_PREV = {
    # type: set of previous types it can follow
    "support":     {"statement", "agreement", "disagreement", "support", "challenge", "response"},
    "challenge":   {"statement", "agreement", "disagreement", "support", "challenge", "response"},
    "agreement":   {"agreement", "disagreement", "challenge", "response", "statement", "support"},
    "disagreement":{"disagreement", "agreement", "challenge", "response", "statement", "support"},
    # statement: see note below, "least likely" after statement, not forbidden
    "statement":   {"agreement", "challenge", "response", "support", "statement"},
    "question":    {"disagreement", "agreement", "challenge", "response", "statement", "support"},
    # response (answer) only really makes sense after question
    "response":    {"question"},
}


def cluster_agent_ids(clusters):
    """
    Returns a list of lists of agent_ids, one list per cluster.
    """
    result = []
    for cl in clusters._clusters:
        ids = [a.agent_id for a in cl.agents]
        result.append(ids)
    return result

class InteractionEngine:
    def __init__(self, agents):
        self.agents = agents
        self.agent_index = {a.agent_id: a for a in agents}
        self.inner_adj = {}

    def get_agent(self, agent_id):
        return self.agent_index.get(agent_id)

    def update_inner_cluster(self, clusters):
        self.inner_adj = {}
        for a in self.agents:
            self.inner_adj[a.agent_id] = set()
        # for each cluster, fully connect within the cluster
        for cluster in clusters._clusters:
            # cluster is a list of agent_ids
            for i in range(len(cluster.agents)):
                for j in range(i + 1, len(cluster.agents)):
                    a_id = cluster.agents[i].agent_id
                    b_id = cluster.agents[j].agent_id
                    # undirected edge
                    self.inner_adj[a_id].add(b_id)
                    self.inner_adj[b_id].add(a_id)

    def expertise(self, agent, topic):
        """
        Approximate expertise as a saturating function of how many OODs
        the agent has in their KB for this topic. Returns in [0,1].
        """
        kb = agent.knowledge_base
        if topic not in kb.kb:
            return 0.0
        n = len(kb.kb[topic].objs)
        # 0 -> 0, 1 -> 0.5, 3 -> 0.75, 7 -> ~0.875, etc.
        return 1.0 - 1.0 / (1.0 + n)
    
    def alignment(self, agent, statement_opinion):
        """
        How aligned is the agent with the presented opinion?
        Returns in [0,1], where 1 = perfectly aligned, 0 = totally opposed.
        """
        return 1.0 - abs(agent.opinion - statement_opinion) / 2.0
    
    def score_statement(self, agent, topic, group_opinion):
        """
        Base tendency to make a standalone statement:
        - higher when uncertainty is low
        - higher with expertise
        - can be slightly stronger when agent is not perfectly aligned with group
          (they have a "take" to offer)
        """
        exp = self.expertise(agent, topic)
        if group_opinion is not None:
            align = self.alignment(agent, group_opinion)
            # more likely to speak if they have something slightly different to say
            diversity = 1.0 - align
        else:
            diversity = 0.5  # neutral if no reference

        return max(
            0.0,
            0.5 * (1.0 - agent.uncertainty) +  # lower uncertainty → more statements
            0.3 * exp +                        # more expertise → more statements
            0.2 * diversity                    # some difference from group → more to say
        )

    def score_agreement(self, agent, statement_opinion):
        align = self.alignment(agent, statement_opinion)
        return max(0.0,
                   0.5 * align
                   + 0.3 * agent.public_compliance_threshold
                   + 0.2 * (1.0 - agent.uncertainty))
    
    def score_disagreement(self, agent, statement_opinion):
        align = self.alignment(agent, statement_opinion)
        return max(0.0,
                   0.5 * (1.0 - align)
                   + 0.3 * (1.0 - agent.private_acceptance_threshold)
                   + 0.2 * (1.0 - agent.uncertainty))

    def score_support(self, agent, topic, statement_opinion):
        align = self.alignment(agent, statement_opinion)
        exp = self.expertise(agent, topic)
        return max(0.0,
                   0.4 * align
                   + 0.3 * (1.0 - agent.uncertainty)
                   + 0.3 * exp)

    def score_challenge(self, agent, topic, statement_opinion):
        align = self.alignment(agent, statement_opinion)
        exp = self.expertise(agent, topic)
        return max(0.0,
                   0.4 * (1.0 - align)
                   + 0.3 * (1.0 - agent.uncertainty)
                   + 0.3 * exp)

    def score_question(self, agent, topic):
        exp = self.expertise(agent, topic)
        return max(0.0,
                   0.5 * agent.uncertainty
                   + 0.3 * agent.private_acceptance_threshold
                   + 0.2 * (1.0 - exp))

    def score_response(self, agent, topic):
        exp = self.expertise(agent, topic)
        return max(0.0,
                   0.6 * (1.0 - agent.uncertainty)
                   + 0.4 * exp)
    
    def choose_interaction_type(self, agent_id, topic, statement_opinion, prev_type, outstanding_question):
        """
        Return one of:
          'agreement', 'disagreement', 'support',
          'challenge', 'question', 'response'
        or None if nothing fires.
        """
        agent = self.agent_index[agent_id]

        scores: dict[str, float] = {}

        # Base scores (before transition rules)
        if statement_opinion is not None:
            scores["agreement"]    = self.score_agreement(agent, statement_opinion)
            scores["disagreement"] = self.score_disagreement(agent, statement_opinion)
            scores["support"]      = self.score_support(agent, topic, statement_opinion)
            scores["challenge"]    = self.score_challenge(agent, topic, statement_opinion)
        else:
            scores["agreement"]    = 0.0
            scores["disagreement"] = 0.0
            scores["support"]      = 0.0
            scores["challenge"]    = 0.0

        scores["question"]  = self.score_question(agent, topic)
        scores["response"]  = self.score_response(agent, topic)
        scores["statement"] = self.score_statement(agent, topic, statement_opinion)

        # ---------- Apply conversation rules ----------

        # 1) Conversation start: only Statement or Question allowed
        if prev_type is None:
            for k in list(scores.keys()):
                if k not in ("statement", "question"):
                    scores[k] = 0.0

        else:
            # We have a previous type → use ALLOWED_PREV table
            for t in scores.keys():
                # Response can ONLY happen when there is an outstanding question
                if t == "response":
                    if not outstanding_question:
                        scores[t] = 0.0
                        continue
                # Enforce predecessor rules
                allowed_prev = ALLOWED_PREV.get(t, set())
                if prev_type not in allowed_prev:
                    scores[t] = 0.0

            # Special note: Statements are "least likely" after Statements,
            # not impossible → downweight when prev was also statement.
            if prev_type == "statement":
                scores["statement"] *= 0.2  # keep small but non-zero

        # If no scores survive, return None
        total = sum(scores.values())
        if total <= 0:
            return None

        # Normalize and sample
        r = random.random()
        cumulative = 0.0
        for kind, score in scores.items():
            p = score / total
            cumulative += p
            if r < cumulative:
                return kind

        # Fallback
        return max(scores, key=scores.get)

    def sample_interaction_event(self, topic, conversation_id, cluster_agent_ids, prev_type, outstanding_question, last_speaker_id, question_target_id=None):
        """
        Sample a single interaction event within current inner_adj graph.

        Args:
            question_target_id: If there's an outstanding question, this is the agent who was asked (should respond)
        
        Returns a dict:
          {
            'speaker': agent_id,
            'target': neighbor_id or None,
            'type': 'agreement' | 'disagreement' | ...,
            'statement_opinion': float in [-1,1] or None for questions
          }
        """
        if cluster_agent_ids:
            base_candidates = cluster_agent_ids
        else:
            base_candidates = [a.agent_id for a in self.agents]

        if not base_candidates:
            return None
        
        # If there's an outstanding question, the response should come from the agent who was asked
        if outstanding_question and question_target_id and question_target_id in base_candidates:
            speaker_id = question_target_id
            speaker = self.agent_index[speaker_id]
            # For response, we need to know who asked (the last speaker)
            if last_speaker_id:
                target_id = last_speaker_id
                target = self.agent_index[target_id]
                group_opinion = target.opinion
            else:
                target_id = None
                group_opinion = None
            
            # Force response type when there's an outstanding question and we have the target
            kind = "response"
        else:
            # Normal flow: choose speaker
            if last_speaker_id is not None:
                candidate_ids = [aid for aid in base_candidates if aid != last_speaker_id]
                if not candidate_ids:
                    # Edge case: cluster size 1 → must allow same speaker
                    candidate_ids = base_candidates
            else:
                candidate_ids = base_candidates

            speaker_id = random.choice(candidate_ids)
            speaker = self.agent_index[speaker_id]

            neighbors_all = list(self.inner_adj.get(speaker_id, []))
            if cluster_agent_ids:
                neighbors = [nid for nid in neighbors_all if nid in cluster_agent_ids]
            else:
                neighbors = neighbors_all

            if neighbors:
                target_id = random.choice(neighbors)
                target = self.agent_index[target_id]
                group_opinion = target.opinion
            else:
                target_id = None
                group_opinion = None

            kind = self.choose_interaction_type(
                agent_id=speaker_id,
                topic=topic,
                statement_opinion=group_opinion,
                prev_type=prev_type,
                outstanding_question=outstanding_question,
            )
            if kind is None:
                return None

        stmt_op = self.compute_statement_opinion(
            agent=speaker,
            topic=topic,
            interaction_type=kind,
            group_opinion=group_opinion,
        )

        # For challenge or support interactions, find a relevant knowledge base item
        source_item = None
        if kind in ("challenge", "support"):
            source_item = speaker.find_knowledge_for_interaction(topic)
            # If found, extract the content or create a dict with relevant info
            if source_item:
                source_item = {
                    "name": source_item.name,
                    "content": source_item.content,
                    "publisher": source_item.publisher,
                    "source_bias": source_item.rating,
                    "agent_opinion": source_item.agent_opinion
                }

        return {
            "conversation_id": conversation_id,
            "speaker": speaker_id,
            "target": target_id,
            "type": kind,
            "statement_opinion": stmt_op,
            "source": source_item
        }
    
    def clamp(self, x: float, lo: float = -1.0, hi: float = 1.0) -> float:
        return max(lo, min(hi, x))

    def mix(self, a: float, b: float, w: float) -> float:
        """
        Linear interpolation between a and b with weight w in [0,1].
        w=0 -> a, w=1 -> b
        """
        return (1.0 - w) * a + w * b
    
    def compute_statement_opinion(
        self,
        agent: Agent,
        topic: str,
        interaction_type: str,
        group_opinion: float | None,
    ) -> float | None:
        """
        Compute the opinion value [-1,1] expressed in the statement for
        a given interaction type.

        Questions return None. Others return a score in [-1,1].
        """

        # Questions don't *state* a position
        if interaction_type == "question":
            return None

        # Base internal stance from opinion, bias, attitude
        internal = (
            0.4 * agent.opinion +
            0.3 * agent.bias +
            0.3 * agent.attitude
        )
        internal = self.clamp(internal)

        # If no group opinion is available (e.g. first speaker),
        # just express something close to internal.
        if group_opinion is None:
            # Slightly moderated by public compliance
            w = 0.3 * agent.public_compliance_threshold
            expressed = self.mix(internal, 0.0, w)  # maybe soften toward center
            return self.clamp(expressed)

        pc = agent.public_compliance_threshold
        pa = agent.private_acceptance_threshold
        exp = self.expertise(agent, topic)

        # Normalize thresholds just in case
        pc = max(0.0, min(1.0, pc))
        pa = max(0.0, min(1.0, pa))

        # --- Interaction-specific behavior ---

        if interaction_type == "agreement":
            # Lean toward group opinion, more so with higher PC
            base = self.mix(internal, group_opinion, pc)
            expressed = base

        elif interaction_type == "support":
            # Similar to agreement, but more weight on internal if expert
            # Experts feel more confident expressing their own aligned view
            blend = 0.5 + 0.3 * exp  # [0.5, 0.8]
            base = self.mix(group_opinion, internal, blend)
            expressed = base

        elif interaction_type == "disagreement":
            # Lean away from group; stronger with low PA (stubborn)
            anti_group = -group_opinion
            # When PA is low, more weight on anti_group; when PA high, closer to internal
            w = 1.0 - pa
            base = self.mix(internal, anti_group, w)
            expressed = base

        elif interaction_type == "challenge":
            # Stronger push against group if expert and stubborn
            anti_group = -group_opinion
            w = 0.5 + 0.3 * (1.0 - pa) + 0.2 * exp  # [0.5, ~1.0]
            w = max(0.0, min(1.0, w))
            base = self.mix(internal, anti_group, w)
            expressed = base

        elif interaction_type == "response":
            # A response tends to be informative, somewhere between internal and group
            # More group leaning with high PC, more internal with expertise
            w_group = 0.3 * pc
            w_internal = 0.3 * exp
            # normalize weights
            w_total = w_group + w_internal
            if w_total > 0:
                w_group /= w_total
                w_internal /= w_total
            else:
                w_group = 0.5
                w_internal = 0.5

            mid = w_group * group_opinion + w_internal * internal
            expressed = mid

        else:
            # Fallback: just say something close to internal
            expressed = internal

        return self.clamp(expressed)
    
    def describe_interaction(self, interaction: dict) -> str:
        """
        Generate a text description of an interaction event.
        
        Args:
            interaction: Dict with keys 'speaker', 'target', 'type', 'statement_opinion'
            
        Returns:
            A human-readable description of the interaction
        """
        speaker = interaction.get('speaker', 'Unknown')
        target = interaction.get('target')
        interaction_type = interaction.get('type', 'unknown')
        statement_opinion = interaction.get('statement_opinion')
        
        # Format opinion value for display
        if statement_opinion is None:
            opinion_desc = ""
        else:
            opinion_desc = f"{statement_opinion:.3f}"
        
        # Generate description based on interaction type
        if interaction_type == "challenge":
            if target:
                if opinion_desc:
                    return f"{speaker} challenges {target}'s statement (opinion: {opinion_desc})"
                else:
                    return f"{speaker} challenges {target}'s statement"
            else:
                if opinion_desc:
                    return f"{speaker} makes a challenge (opinion: {opinion_desc})"
                else:
                    return f"{speaker} makes a challenge"
        
        elif interaction_type == "disagreement":
            if target:
                if opinion_desc:
                    return f"{speaker} disagrees with {target}'s statement (opinion: {opinion_desc})"
                else:
                    return f"{speaker} disagrees with {target}'s statement"
            else:
                if opinion_desc:
                    return f"{speaker} expresses disagreement (opinion: {opinion_desc})"
                else:
                    return f"{speaker} expresses disagreement"
        
        elif interaction_type == "agreement":
            if target:
                if opinion_desc:
                    return f"{speaker} agrees with {target}'s statement (opinion: {opinion_desc})"
                else:
                    return f"{speaker} agrees with {target}'s statement"
            else:
                if opinion_desc:
                    return f"{speaker} expresses agreement (opinion: {opinion_desc})"
                else:
                    return f"{speaker} expresses agreement"
        
        elif interaction_type == "support":
            if target:
                if opinion_desc:
                    return f"{speaker} supports {target}'s statement (opinion: {opinion_desc})"
                else:
                    return f"{speaker} supports {target}'s statement"
            else:
                if opinion_desc:
                    return f"{speaker} provides support (opinion: {opinion_desc})"
                else:
                    return f"{speaker} provides support"
        
        elif interaction_type == "question":
            if target:
                return f"{speaker} asks {target} a question"
            else:
                return f"{speaker} asks a question"
        
        elif interaction_type == "response":
            if target:
                if opinion_desc:
                    return f"{speaker} responds to {target} (opinion: {opinion_desc})"
                else:
                    return f"{speaker} responds to {target}"
            else:
                if opinion_desc:
                    return f"{speaker} provides a response (opinion: {opinion_desc})"
                else:
                    return f"{speaker} provides a response"
        
        else:
            # Fallback for unknown types
            if target:
                return f"{speaker} interacts with {target} ({interaction_type})"
            else:
                return f"{speaker} performs a {interaction_type} interaction"