"""
Agent class for the Lyra system recreation.

This module implements the core agent with properties and behaviors
as described in the Lyra paper.
"""

from typing import Optional, List, Dict, Any
import random
import os, math, random, json
import sys
import importlib.util
from Knowledge_Base.knowledge_base import KnowledgeBase, ObjectOfDiscussion, Topic



class Agent:
    """
    An agent in the Lyra system with properties and behaviors.
    
    Each agent has:
    - Attitude: General disposition/outlook
    - Opinion: Current opinion on the topic
    - Uncertainty: How uncertain the agent is about their opinion
    - Public Compliance Threshold: Threshold for public compliance
    - Private Acceptance Threshold: Threshold for private acceptance
    - Bias: Agent's inherent bias
    - Knowledge Base: KnowledgeBase instance that stores topics and objects of discussion
    """
    
    def __init__(self, 
                 agent_id: str,
                 attitude: float = 0.0,
                 opinion: float = 0.0,
                 uncertainty: float = 0.5,
                 public_compliance_threshold: float = 0.5,
                 private_acceptance_threshold: float = 0.3,
                 bias: float = 0.0,
                 knowledge_base_path: Optional[str] = None):
        """
        Initialize an agent with specified properties.
        
        Args:
            agent_id: Unique identifier for the agent
            attitude: Agent's general disposition (-1.0 to 1.0)
            opinion: Agent's current opinion (-1.0 to 1.0)
            uncertainty: How uncertain the agent is (0.0 to 1.0)
            public_compliance_threshold: Threshold for public compliance (0.0 to 1.0)
            private_acceptance_threshold: Threshold for private acceptance (0.0 to 1.0)
            bias: Agent's inherent bias (-1.0 to 1.0)
            knowledge_base_path: Optional path for the agent's knowledge base directory.
                                If None, defaults to "Knowledge Base/agent_{agent_id}"
        """
        self.agent_id = agent_id
        
        # Validate and set properties directly
        self._validate_and_set_properties(
            attitude, opinion, uncertainty,
            public_compliance_threshold, private_acceptance_threshold, bias
        )
        
        # Additional state variables
        self.interaction_history: List[Dict[str, Any]] = []
        self.last_updated: int = 0  # Timestep when last updated
        
        # Initialize knowledge base
        if knowledge_base_path is None:
            knowledge_base_path = f"Knowledge_Base/Agent/agent_{agent_id}"
        os.makedirs(knowledge_base_path, exist_ok=True)

        # WIPE ALL EXISTING JSONS FOR THIS AGENT (clean start each run)
        for fname in os.listdir(knowledge_base_path):
            full_path = os.path.join(knowledge_base_path, fname)
            if os.path.isfile(full_path) and fname.endswith(".json"):
                os.remove(full_path)

        # Initialize knowledge base (in-memory only, no loading from disk)
        self.knowledge_base = KnowledgeBase(knowledge_base_path, load_from_disk=False)

        self.subscribed_sources: Dict[str, List[str]] = {}
        
        # Create JSON with history (agent log)
        self.log_dir = knowledge_base_path  # reuse the same folder
        self.log_path = os.path.join(self.log_dir, f"agent_{agent_id}.json")
        self.init_log_file()
        
    
    def _validate_and_set_properties(self, attitude: float, opinion: float, 
                                   uncertainty: float, public_compliance_threshold: float,
                                   private_acceptance_threshold: float, bias: float) -> None:
        """Validate and set agent properties."""
        # Validate properties that should be between -1 and 1
        for attr_name, value in [('attitude', attitude), ('opinion', opinion), ('bias', bias)]:
            if not -1.0 <= value <= 1.0:
                raise ValueError(f"{attr_name} must be between -1.0 and 1.0, got {value}")
        
        # Validate properties that should be between 0 and 1
        for attr_name, value in [('uncertainty', uncertainty), 
                               ('public_compliance_threshold', public_compliance_threshold),
                               ('private_acceptance_threshold', private_acceptance_threshold)]:
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{attr_name} must be between 0.0 and 1.0, got {value}")
        
        # Set properties directly as attributes
        self.attitude = attitude
        self.opinion = opinion
        self.uncertainty = uncertainty
        self.public_compliance_threshold = public_compliance_threshold
        self.private_acceptance_threshold = private_acceptance_threshold
        self.bias = bias
    
    @classmethod
    def create_random_agent(cls, agent_id: str) -> 'Agent':
        """
        Create an agent with random properties within valid ranges.
        
        Args:
            agent_id: Unique identifier for the agent
            
        Returns:
            Agent with randomized properties
        """
        return cls(
            agent_id=agent_id,
            attitude=round(random.uniform(-1.0, 1.0), 2),
            opinion=round(random.uniform(-1.0, 1.0), 2),
            uncertainty=round(random.uniform(0.0, 1.0), 2),
            public_compliance_threshold=round(random.uniform(0.0, 1.0), 2),
            private_acceptance_threshold=round(random.uniform(0.0, 1.0), 2),
            bias=round(random.uniform(-1.0, 1.0), 2)
        )
    
    def get_attitude(self) -> float:
        """Get the agent's attitude."""
        return self.attitude
    
    def get_opinion(self) -> float:
        """Get the agent's current opinion."""
        return self.opinion
    
    def get_uncertainty(self) -> float:
        """Get the agent's uncertainty level."""
        return self.uncertainty
    
    def get_public_compliance_threshold(self) -> float:
        """Get the public compliance threshold."""
        return self.public_compliance_threshold
    
    def get_private_acceptance_threshold(self) -> float:
        """Get the private acceptance threshold."""
        return self.private_acceptance_threshold
    
    def get_bias(self) -> float:
        """Get the agent's bias."""
        return self.bias
    
    def update_opinion(self, new_opinion: float, timestep: int, influenced_by: Optional[str] = None) -> None:
        """
        Update the agent's opinion.
        
        Args:
            new_opinion: New opinion value (-1.0 to 1.0)
            timestep: Current timestep
            influenced_by: ID of the agent that influenced this change (optional)
        """
        if not -1.0 <= new_opinion <= 1.0:
            raise ValueError(f"Opinion must be between -1.0 and 1.0, got {new_opinion}")
        
        old_opinion = self.opinion
        self.opinion = new_opinion
        self.last_updated = timestep
        
        # Record the change in interaction history
        self.interaction_history.append({
            'timestep': timestep,
            'type': 'opinion_update',
            'old_value': old_opinion,
            'new_value': new_opinion,
            'change': new_opinion - old_opinion,
            'influenced_by': influenced_by
        })

    def update_attitude(self, new_attitude: float, timestep: int, influenced_by: Optional[str] = None) -> None:
        """
        Update the agent's attitude.
        
        Args:
            new_attitude: New attitude value (-1.0 to 1.0)
            timestep: Current timestep
            influenced_by: ID of the agent that influenced this change (optional)
        """
        if not -1.0 <= new_attitude <= 1.0:
            raise ValueError(f"Opinion must be between -1.0 and 1.0, got {new_attitude}")
        
        old_attitude = self.attitude
        self.attitude = new_attitude
        self.last_updated = timestep
        
        # Record the change in interaction history
        self.interaction_history.append({
            'timestep': timestep,
            'type': 'opinion_update',
            'old_value': old_attitude,
            'new_value': new_attitude,
            'change': new_attitude - old_attitude,
            'influenced_by': influenced_by
        })
    
    def update_uncertainty(self, new_uncertainty: float, timestep: int, influenced_by: Optional[str] = None) -> None:
        """
        Update the agent's uncertainty level.
        
        Args:
            new_uncertainty: New uncertainty value (0.0 to 1.0)
            timestep: Current timestep
            influenced_by: ID of the agent that influenced this change (optional)
        """
        if not 0.0 <= new_uncertainty <= 1.0:
            raise ValueError(f"Uncertainty must be between 0.0 and 1.0, got {new_uncertainty}")
        
        old_uncertainty = self.uncertainty
        self.uncertainty = new_uncertainty
        self.last_updated = timestep
        
        # Record the change in interaction history
        self.interaction_history.append({
            'timestep': timestep,
            'type': 'uncertainty_update',
            'old_value': old_uncertainty,
            'new_value': new_uncertainty,
            'change': new_uncertainty - old_uncertainty,
            'influenced_by': influenced_by
        })
    
    def will_comply_publicly(self, pressure: float) -> bool:
        """
        Determine if the agent will comply publicly based on pressure.
        
        Args:
            pressure: External pressure to comply (0.0 to 1.0)
            
        Returns:
            True if agent will comply publicly, False otherwise
        """
        return pressure >= self.public_compliance_threshold
    
    def will_stand_by_views(self, pressure: float) -> bool:
        """
        Determine if the agent will stand by their views based on pressure.
        
        Args:
            pressure: External pressure to change views (0.0 to 1.0)
            
        Returns:
            True if agent will stand by their views (resist pressure), False otherwise
        """
        return pressure >= self.private_acceptance_threshold
    
    def calculate_influence_susceptibility(self) -> float:
        """
        Calculate how susceptible the agent is to influence.
        
        Returns:
            Susceptibility value (higher = more susceptible)
        """
        # Higher uncertainty and lower thresholds make agent more susceptible
        uncertainty_factor = self.uncertainty
        threshold_factor = 1.0 - (self.public_compliance_threshold + 
                                 self.private_acceptance_threshold) / 2.0
        
        return round((uncertainty_factor + threshold_factor) / 2.0, 2)
    
    def add_knowledge(self, obj: Any) -> None:
        """
        Add an ObjectOfDiscussion to the agent's knowledge base.
        
        Args:
            obj: An object with name, topic, rating, and content attributes
                 (e.g., ObjectOfDiscussion or any object with these attributes)
        """
        # Use KnowledgeBase's learn_ood method - it handles creating topics and folders
        self.knowledge_base.learn_ood(obj)
    
    def has_knowledge_item(self, name: str, topic: str, publisher: Optional[str] = None) -> bool:
        """
        Check if the agent already has a knowledge item with the given name and topic.
        Optionally checks publisher as well.
        
        Args:
            name: Name of the knowledge item
            topic: Topic name
            publisher: Optional publisher name to match
            
        Returns:
            True if the item exists, False otherwise
        """
        topic_objs = self.knowledge_base.get_knowledge_by_topic(topic, content_only=True)
        if not topic_objs:
            return False
        
        for obj in topic_objs:
            if obj.name == name:
                # If publisher is specified, check it matches
                if publisher is not None:
                    if obj.publisher == publisher:
                        return True
                else:
                    # Just check name match
                    return True
        
        return False
    
    def get_knowledge_by_source(self, source: str) -> List[Any]:
        """
        Get all knowledge items from a specific source.
        
        Args:
            source: The source to filter by (searches in content)
            
        Returns:
            List of ObjectOfDiscussion objects from the specified source
        """
        results = []
        for topic in self.knowledge_base.kb.values():
            for obj in topic.objs:
                if source in obj.content:
                    results.append(obj)
        return results
    
    def has_knowledge_about(self, object_of_discussion: str) -> bool:
        """
        Check if the agent has knowledge about a specific object of discussion.
        
        Args:
            object_of_discussion: The object of discussion to check for (name or content)
            
        Returns:
            True if the agent has knowledge about this object, False otherwise
        """
        for topic in self.knowledge_base.kb.values():
            for obj in topic.objs:
                if object_of_discussion in obj.name or object_of_discussion in obj.content:
                    return True
        return False
    
    def get_state_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the agent's current state.
        
        Returns:
            Dictionary containing agent state information
        """
        return {
            'agent_id': self.agent_id,
            'attitude': self.attitude,
            'opinion': self.opinion,
            'uncertainty': self.uncertainty,
            'public_compliance_threshold': self.public_compliance_threshold,
            'private_acceptance_threshold': self.private_acceptance_threshold,
            'bias': self.bias,
            'last_updated': self.last_updated,
            'interaction_count': len(self.interaction_history),
            'knowledge_base_size': sum(len(topic.objs) for topic in self.knowledge_base.kb.values()),
            'influence_susceptibility': self.calculate_influence_susceptibility()
        }
    
    def __str__(self) -> str:
        """String representation of the agent."""
        return (f"Agent({self.agent_id}): "
                f"opinion={self.opinion:.2f}, "
                f"uncertainty={self.uncertainty:.2f}, "
                f"attitude={self.attitude:.2f}")
    
    def __repr__(self) -> str:
        """Detailed string representation of the agent."""
        return (f"Agent(agent_id='{self.agent_id}', "
                f"attitude={self.attitude}, "
                f"opinion={self.opinion}, "
                f"uncertainty={self.uncertainty}, "
                f"public_compliance_threshold={self.public_compliance_threshold}, "
                f"private_acceptance_threshold={self.private_acceptance_threshold}, "
                f"bias={self.bias})")
    

    # ---------- Source selection helpers ----------
    def _load_source_metadata(self, info_json_path):
        with open(info_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("Sources", [])

    def pick_sources_for_topic(
        self,
        info_json_path,
        min_sources=2,
        max_sources=5,
        alpha=3.0,
        exploration_min=0.05,
        exploration_max=0.5,
    ):
        sources = self._load_source_metadata(info_json_path)
        if not sources:
            return []

        orientation = 0.5 * self.attitude + 0.5 * self.bias

        weights = []
        for src in sources:
            b_s = float(src.get("Source_Bias", 0.0))
            dist = abs(orientation - b_s)
            weights.append(math.exp(-alpha * dist))

        total_w = sum(weights)
        if total_w == 0.0:
            probs_align = [1.0 / len(weights)] * len(weights)
        else:
            probs_align = [w / total_w for w in weights]

        N = len(sources)
        exploration = exploration_min + self.uncertainty * (exploration_max - exploration_min)

        probs = [
            (1.0 - exploration) * p + exploration * (1.0 / N)
            for p in probs_align
        ]

        max_sources = min(max_sources, N)
        if max_sources < min_sources:
            min_sources = max_sources

        k_float = max_sources - self.uncertainty * (max_sources - min_sources)
        k = max(min_sources, min(int(round(k_float)), N))

        indices = list(range(N))
        draw_count = min(N * 3, max(3 * k, N))
        sampled_indices = random.choices(indices, weights=probs, k=draw_count)

        chosen_indices = []
        seen = set()
        for idx in sampled_indices:
            if idx not in seen:
                seen.add(idx)
                chosen_indices.append(idx)
                if len(chosen_indices) >= k:
                    break

        if len(chosen_indices) < k:
            for idx in indices:
                if idx not in seen:
                    chosen_indices.append(idx)
                    if len(chosen_indices) >= k:
                        break

        return [sources[i] for i in chosen_indices]

    def seed_knowledge_from_master(
        self,
        master_kb,
        topic,
        info_json_path,
        min_sources=2,
        max_sources=5,
        **pick_kwargs,
    ) -> List[ObjectOfDiscussion]:
        """
        Populate this agent's KB for a topic based on info.json + master_kb,
        and return the list of OODs learned in this seeding step.
        """
        chosen_sources = self.pick_sources_for_topic(
            info_json_path,
            min_sources=min_sources,
            max_sources=max_sources,
            **pick_kwargs,
        )
        if not chosen_sources:
            return []

        chosen_names = {s["Source_Name"] for s in chosen_sources}

        master_topic = master_kb.get_knowledge_by_topic(topic, content_only=False)
        if master_topic is None:
            return []

        new_oods: List[ObjectOfDiscussion] = []
        for obj in master_topic.all_objects():
            if getattr(obj, "publisher", None) in chosen_names:
                # make a per-agent copy of the OOD
                personal_ood = ObjectOfDiscussion(
                    name=obj.name,
                    topic=obj.topic,
                    publisher=obj.publisher,
                    source_type=obj.source_type,
                    attitude=obj.attitude,
                    rating=obj.rating,
                    content=obj.content,
                )
                # compute how this agent feels about this work
                personal_ood.agent_opinion = self.evaluate_ood(personal_ood)

                # store into this agent's KB
                self.knowledge_base.learn_ood(personal_ood)
                new_oods.append(personal_ood)

        self.subscribed_sources[topic] = list(chosen_names)
        return new_oods

    def init_log_file(self) -> None:
        """
        Create or wipe this agent's JSON log.
        Stores static info and initial state. Rounds get appended later.
        """
        data = {
            "agent_id": self.agent_id,
            "static": {
                "bias": self.bias,
                "public_compliance_threshold": self.public_compliance_threshold,
                "private_acceptance_threshold": self.private_acceptance_threshold,
            },
            "initial_state": {
                "attitude": self.attitude,
                "opinion": self.opinion,
                "uncertainty": self.uncertainty,
            },
            "rounds": []
        }

        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def log_round(
        self,
        round_idx: int,
        new_oods: Optional[List[ObjectOfDiscussion]] = None,
    ) -> None:
        """
        Append the current state of the agent for this round to the JSON log.

        new_oods: list of ObjectOfDiscussion learned *during this round*.
                  For round 0, pass all initially assigned OODs.
        """
        if new_oods is None:
            new_oods = []

        # Load existing log
        with open(self.log_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Convert OODs to simple dicts for JSON
        new_oods_payload = []
        for o in new_oods:
            new_oods_payload.append({
                "topic": o.topic,
                "name": o.name,
                "publisher": getattr(o, "publisher", None),
                "source_bias": getattr(o, "rating", None),
                "attitude": getattr(o, "attitude", None),
                "agent_opinion": getattr(o, "agent_opinion", None),
            })

        entry = {
            "round": round_idx,
            "attitude": self.attitude,
            "opinion": self.opinion,
            "uncertainty": self.uncertainty,
            "new_oods": new_oods_payload,
        }

        data.setdefault("rounds", []).append(entry)

        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    def evaluate_ood(self, ood: ObjectOfDiscussion) -> float:
        """
        Compute this agent's opinion about a given OOD,
        based on how much the source resonates with the agent.

        Example heuristic:
          - alignment with agent bias vs. source bias (rating)
          - alignment with agent attitude vs. work attitude
        Result is mapped back to [-1, 1].
        """
        # alignment components in [0, 1]
        bias_alignment = 1.0 - abs(self.bias - ood.rating) / 2.0          # both in [-1,1]
        att_alignment = 1.0 - abs(self.attitude - ood.attitude) / 2.0     # both in [-1,1]

        # weighted combination
        raw = 0.5 * bias_alignment + 0.5 * att_alignment   # in [0,1]

        # map [0,1] -> [-1,1]
        agent_opinion = 2.0 * raw - 1.0
        return max(-1.0, min(1.0, agent_opinion))
    

    # =================== Interactions ==========================
    def _score_source_for_research(self, source_bias: float) -> float:
        """
        Score how likely this agent is to read a source with the given bias,
        based on:
          - their own bias
          - public_compliance_threshold
          - private_acceptance_threshold

        Higher score → more likely to be picked.
        """

        # Similarity between agent bias and source bias in [0,1]
        dist = abs(self.bias - source_bias)          # max 2
        sim = 1.0 - dist / 2.0                       # 1 = same bias, 0 = opposite

        # Base alignment vs opposition weights
        if abs(self.bias) >= 0.75:
            # Heavily biased → prefers aligned sources
            align_weight = 0.9
            oppose_weight = 0.1
        else:
            # Moderates → more inclined toward opposing sources
            align_weight = 0.4
            oppose_weight = 0.6

        # Public compliance: high PC → more willing to read non-aligned
        if self.public_compliance_threshold > 0.7:
            oppose_weight += 0.2

        # Private acceptance: high PA → more likely to stick with aligned
        if self.private_acceptance_threshold > 0.7:
            align_weight += 0.2

        # Clip weights to something sane
        align_weight = max(0.0, min(1.5, align_weight))
        oppose_weight = max(0.0, min(1.5, oppose_weight))

        # Final score mixes aligned and opposing preference
        align_score = align_weight * sim
        oppose_score = oppose_weight * (1.0 - sim)

        score = align_score + oppose_score

        # Avoid exact zero so everything has at least a tiny chance
        return max(score, 1e-6)
    
    def research_when_isolated(self, master_kb, topic, info_json_path, min_new=1, max_new=3,):
        """
        When an agent is isolated (alone in their cluster),
        they research 1–3 new items from the master KB.

        They preferentially read opposing sources unless:
        - extreme bias (>|0.75|)
        - high public threshold (>0.7)
        - high private acceptance (>0.7)

        This function:
        - selects sources based on these rules
        - selects works from chosen sources
        - computes agent_opinion
        - adds them to the agent KB using learn_ood
        - returns the list of new OODs
        """
         # 1. Load source metadata
        sources = self._load_source_metadata(info_json_path)
        if not sources:
            return []

        orientation = 0.5 * self.attitude + 0.5 * self.bias

        # 2. Decide whether to prefer opposing vs aligned
        prefer_opposing = True
        if abs(self.bias) >= 0.75:
            prefer_opposing = False
        if self.public_compliance_threshold > 0.7:
            prefer_opposing = True
        if self.private_acceptance_threshold > 0.7:
            prefer_opposing = False

        # 3. Build weights over SOURCES
        aligned_weights = []
        opposing_weights = []
        for src in sources:
            src_bias = float(src.get("Source_Bias", 0.0))
            dist = abs(orientation - src_bias)
            aligned_w = 1.0 / (1.0 + dist)
            opposing_w = dist
            aligned_weights.append(aligned_w)
            opposing_weights.append(opposing_w)

        if prefer_opposing:
            final_weights = opposing_weights
        else:
            final_weights = aligned_weights

        total_w = sum(final_weights)
        if total_w == 0:
            probs = [1.0 / len(final_weights)] * len(final_weights)
        else:
            probs = [w / total_w for w in final_weights]

        # 4. Pick some SOURCES (still just sources here)
        k_sources = random.randint(1, min(3, len(sources)))
        idxs = list(range(len(sources)))
        sampled = random.choices(idxs, weights=probs, k=min(3 * k_sources, len(idxs)))

        chosen_idxs = []
        seen = set()
        for idx in sampled:
            if idx not in seen:
                seen.add(idx)
                chosen_idxs.append(idx)
                if len(chosen_idxs) >= k_sources:
                    break

        chosen_sources = [sources[i] for i in chosen_idxs]
        chosen_names = {s["Source_Name"] for s in chosen_sources}

        # 5. Now pick WORKS (OODs) from those sources, BUT LIMIT TO 1–3
        master_topic = master_kb.get_knowledge_by_topic(topic, content_only=False)
        if master_topic is None:
            return []

        # all candidate works whose publisher is in chosen_names
        candidate_objs = [
            obj for obj in master_topic.all_objects()
            if getattr(obj, "publisher", None) in chosen_names
        ]
        if not candidate_objs:
            return []

        # choose how many works to read
        k_works = random.randint(min_new, min(max_new, len(candidate_objs)))

        # sample k_works distinct works
        chosen_objs = random.sample(candidate_objs, k_works) if len(candidate_objs) > k_works else candidate_objs

        new_oods: List[ObjectOfDiscussion] = []

        for obj in chosen_objs:
            personal_ood = ObjectOfDiscussion(
                name=obj.name,
                topic=obj.topic,
                publisher=obj.publisher,
                source_type=obj.source_type,
                attitude=obj.attitude,
                rating=obj.rating,
                content=obj.content,
            )
            personal_ood.agent_opinion = self.evaluate_ood(personal_ood)
            self.knowledge_base.learn_ood(personal_ood)
            new_oods.append(personal_ood)

        return new_oods
    
    def find_knowledge_for_interaction(self, topic: str, bias_tolerance: float = 0.4, min_agent_opinion: float = 0.5) -> Optional[ObjectOfDiscussion]:
        """
        Find a knowledge base item suitable for challenge or support interactions.
        
        Criteria:
        - source_bias (rating) should be similar to agent's bias (within bias_tolerance)
        - agent_opinion should be high (>= min_agent_opinion)
        
        Args:
            topic: The topic to search in
            bias_tolerance: Maximum difference between agent bias and source bias (default 0.4)
            min_agent_opinion: Minimum agent_opinion value to consider (default 0.5)
            
        Returns:
            An ObjectOfDiscussion matching the criteria, or None if none found
        """
        # Get all objects for this topic
        topic_objs = self.knowledge_base.get_knowledge_by_topic(topic, content_only=True)
        if not topic_objs:
            return None
        
        # Filter by criteria
        candidates = []
        for obj in topic_objs:
            # Check source_bias similarity
            bias_diff = abs(self.bias - obj.rating)
            if bias_diff > bias_tolerance:
                continue
            
            # Check agent_opinion (evaluate if not set)
            if obj.agent_opinion is None:
                obj.agent_opinion = self.evaluate_ood(obj)
            
            if obj.agent_opinion is not None and obj.agent_opinion >= min_agent_opinion:
                candidates.append(obj)
        
        if not candidates:
            return None
        
        # Sort by agent_opinion (highest first), then by bias similarity (closest first)
        candidates.sort(
            key=lambda o: (
                -o.agent_opinion if o.agent_opinion is not None else -1.0,  # Higher agent_opinion first
                abs(self.bias - o.rating)  # Closer bias second
            )
        )
        
        # Return the best match
        return candidates[0]