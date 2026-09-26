"""
NYT Connections Puzzle Generator - Generator Module
Contains: PuzzleGenerator class with all generation methods
"""

import os
import random
import numpy as np
import itertools
import copy
from typing import List, Dict, Tuple, Optional, Any
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity

from core import (
    PuzzleMode, ModelBackend, DifficultyColor, 
    WordGroup, ConnectionsPuzzle,
    OpenSourceLLM, TreeOfThoughtsNode, ReinforcementLearningBuffer,
    EnhancedDifficultyPredictor, TriCOSimilarityCalculator, SemanticKnowledgeBase,
    PromptTemplates,
    parse_puzzle_response, generate_fallback_group,
    is_valid_word, clean_word, extract_valid_words
)

from sentence_transformers import SentenceTransformer
from openai import OpenAI


class PuzzleGenerator:
    """Enhanced puzzle generation framework with improved TriCO and generation methods"""
    
    def __init__(self, 
                 api_key: str = None,
                 backend: ModelBackend = ModelBackend.MOCK,
                 open_source_model: str = None,
                 enable_novel_methods: bool = True,
                 enable_reinforcement: bool = True,
                 enable_ensemble: bool = True):
        
        self.backend = backend
        
        # Initialize backend
        if backend == ModelBackend.OPENAI:
            api_key = api_key or os.environ.get('OPENAI_API_KEY')
            if api_key and api_key not in ["your-api-key-here", None, ""]:
                try:
                    self.client = OpenAI(api_key=api_key, timeout=60.0)
                    print("OpenAI backend initialized")
                except Exception as e:
                    print(f"Could not initialize OpenAI: {e}")
                    print("Falling back to mock backend")
                    self.backend = ModelBackend.MOCK
                    self.client = None
            else:
                print("No API key found, using mock backend")
                self.backend = ModelBackend.MOCK
                self.client = None
                
        elif backend == ModelBackend.OPEN_SOURCE:
            try:
                self.llm = OpenSourceLLM(open_source_model)
                print(f"Open source backend initialized with {self.llm.model_name}")
            except Exception as e:
                print(f"Could not load open source model: {e}")
                print("Falling back to mock backend")
                self.backend = ModelBackend.MOCK
                self.llm = None
        else:
            self.client = None
            self.llm = None
            print("Using mock backend")
        
        # Feature flags
        self.enable_novel_methods = enable_novel_methods
        self.enable_reinforcement = enable_reinforcement
        self.enable_ensemble = enable_ensemble
        
        # Initialize embedding models
        print("Loading embedding models...")
        self.embedder = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
        
        # Additional embedders for ensemble
        self.additional_embedders = {}
        if enable_ensemble:
            try:
                print("Loading ensemble models...")
                self.additional_embedders['minilm'] = SentenceTransformer('sentence-transformers/all-MiniLM-L12-v2')
            except Exception as e:
                print(f"Warning: Could not load ensemble models: {e}")
                self.enable_ensemble = False
        
        # Initialize TriCO calculator
        self.trico_calculator = TriCOSimilarityCalculator(self.embedder)
        
        # Initialize knowledge base
        self.knowledge_base = SemanticKnowledgeBase()
        
        # Reinforcement learning components
        if enable_reinforcement:
            self.difficulty_predictor = EnhancedDifficultyPredictor()
            self.feedback_buffer = ReinforcementLearningBuffer()
        
        # Mock response index
        self._mock_index = 0
        
        # Current word pool for TriCO indexing
        self._current_word_pool = []
    
    def generate_puzzle(self, 
                       mode: PuzzleMode = PuzzleMode.ONE_STEP,
                       theme: Optional[str] = None,
                       seeded_words: Optional[List[str]] = None,
                       difficulty_target: float = 0.35) -> ConnectionsPuzzle:
        """Generate a complete Connections puzzle with difficulty enhancement"""
        
        try:
            if mode == PuzzleMode.ONE_STEP:
                puzzle = self._generate_one_step(theme)
            
            elif mode == PuzzleMode.INTENTIONAL_OVERLAP:
                puzzle = self._generate_intentional_overlap(theme)
                
            elif mode == PuzzleMode.FALSE_GROUP:
                puzzle = self._generate_false_group(theme, seeded_words)
            
            elif mode == PuzzleMode.TREE_OF_THOUGHTS:
                puzzle = self._generate_tree_of_thoughts(theme)
            
            elif mode == PuzzleMode.TRICO:
                puzzle = self._generate_trico_puzzle(theme)
            
            elif mode == PuzzleMode.FALSE_GROUP_SEEDED:
                puzzle = self._generate_false_group_seeded(seeded_words)
            else:
                puzzle = self._generate_one_step(theme)
            
            # CRITICAL: Validate that words actually match their categories
            puzzle.groups = self._validate_words_match_category(puzzle.groups)
            
            # Apply difficulty enhancement to all puzzles
            puzzle = self._enhance_difficulty(puzzle)
            
            return puzzle
                
        except Exception as e:
            print(f"Generation failed: {e}")
            import traceback
            traceback.print_exc()
            print("Falling back to one-step generation")
            return self._generate_one_step(theme)
    
    def _enhance_difficulty(self, puzzle: ConnectionsPuzzle) -> ConnectionsPuzzle:
        """Post-process puzzle to maximize difficulty and deception"""
        
        # Step 1: Compute cross-group similarities to find near-misses
        all_words = puzzle.get_all_words()
        embeddings = self.embedder.encode(all_words)
        word_to_group = puzzle.get_word_to_group_map()
        
        # Find words that are semantically close but in different groups
        cross_group_pairs = []
        for i, word1 in enumerate(all_words):
            for j, word2 in enumerate(all_words):
                if i < j and word_to_group[word1] != word_to_group[word2]:
                    sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                    if sim > 0.4:  # Moderately similar
                        cross_group_pairs.append((word1, word2, sim))
        
        # Sort by similarity (highest first)
        cross_group_pairs.sort(key=lambda x: x[2], reverse=True)
        
        # Step 2: Count near-misses (plausible wrong groupings)
        near_misses = self._count_near_misses(puzzle, embeddings, all_words)
        
        # Step 3: If puzzle is too easy, try to swap words to increase difficulty
        if near_misses < 30:  # Target at least 30 near-misses
            puzzle = self._try_increase_deception(puzzle, cross_group_pairs)
        
        # Step 4: Ensure at least one abstract category
        has_abstract = False
        abstract_patterns = ['___', 'before', 'after', 'slang', 'words that', 'things that', 'can be']
        for group in puzzle.groups:
            if any(p in group.category.lower() for p in abstract_patterns):
                has_abstract = True
                break
        
        if not has_abstract and self.backend != ModelBackend.MOCK:
            # Try to make purple category more abstract
            puzzle = self._abstractify_purple_category(puzzle)
        
        # Store deception metrics
        puzzle.metadata['near_misses'] = near_misses
        puzzle.metadata['cross_group_pairs'] = len(cross_group_pairs)
        puzzle.metadata['difficulty_enhanced'] = True
        
        return puzzle
    
    def _count_near_misses(self, puzzle: ConnectionsPuzzle, embeddings, all_words) -> int:
        """Count how many plausible but wrong 4-word groupings exist"""
        from itertools import combinations
        
        word_to_group = puzzle.get_word_to_group_map()
        word_to_idx = {w: i for i, w in enumerate(all_words)}
        
        near_miss_count = 0
        threshold = 0.35  # Similarity threshold for "plausible" grouping
        
        # Check all combinations of 4 words
        for combo in combinations(all_words, 4):
            # Skip if this is an actual correct group
            groups_in_combo = set(word_to_group[w] for w in combo)
            if len(groups_in_combo) == 1:
                continue  # This is a correct group
            
            # Compute average similarity within this combo
            indices = [word_to_idx[w] for w in combo]
            combo_embeddings = [embeddings[i] for i in indices]
            
            similarities = []
            for i in range(4):
                for j in range(i+1, 4):
                    sim = cosine_similarity([combo_embeddings[i]], [combo_embeddings[j]])[0][0]
                    similarities.append(sim)
            
            avg_sim = sum(similarities) / len(similarities)
            
            if avg_sim > threshold:
                near_miss_count += 1
        
        return near_miss_count
    
    def _try_increase_deception(self, puzzle: ConnectionsPuzzle, 
                                cross_group_pairs: List) -> ConnectionsPuzzle:
        """Try to make puzzle more deceptive by identifying trap words"""
        
        # Mark words involved in cross-group similarity as "trap words"
        trap_words = set()
        for w1, w2, sim in cross_group_pairs[:10]:  # Top 10 confusing pairs
            trap_words.add(w1)
            trap_words.add(w2)
        
        puzzle.metadata['trap_words'] = list(trap_words)
        puzzle.metadata['confusing_pairs'] = [(w1, w2, f"{sim:.2f}") for w1, w2, sim in cross_group_pairs[:5]]
        
        return puzzle
    
    def _abstractify_purple_category(self, puzzle: ConnectionsPuzzle) -> ConnectionsPuzzle:
        """Try to make the purple category more abstract (only for semantic groups)"""
        
        # Find the purple group
        purple_group = None
        for group in puzzle.groups:
            if group.difficulty == DifficultyColor.PURPLE:
                purple_group = group
                break
        
        if not purple_group:
            return puzzle
        
        # DON'T abstractify phonetic or orthographic groups - their categories describe patterns
        if purple_group.primary_view in ['pho', 'orth']:
            return puzzle
        
        # Skip if category already describes a pattern
        pattern_indicators = ['letter', 'rhyme', 'start with', 'end with', 'sound', 'vowel', 'pattern']
        if any(p in purple_group.category.lower() for p in pattern_indicators):
            return puzzle
        
        # Ask LLM for a more abstract category name
        prompt = f"""These 4 words go together: {', '.join(purple_group.words)}

Current category name: "{purple_group.category}"

Suggest a MORE CLEVER/TRICKY category name that:
1. Uses wordplay, fill-in-blank, or lateral thinking
2. Is not immediately obvious
3. Makes players think "aha!" when revealed

Examples of clever category names:
- "___ BALL" (instead of "Sports equipment")
- "Things that can be BROKEN" (instead of "Fragile items")
- "Words before HOUSE" (instead of "Types of buildings")

Output just the new category name, nothing else:"""
        
        response = self._call_llm(prompt, temperature=0.7)
        if response:
            new_name = response.strip().split('\n')[0][:50]
            if len(new_name) > 3:
                purple_group.category = new_name
        
        return puzzle
    
    # ================================================================
    # ONE-STEP GENERATION (FIXED)
    # ================================================================
    
    def _generate_one_step(self, theme: Optional[str] = None) -> ConnectionsPuzzle:
        """Paper-faithful One-Step generation with proper word validation"""
        
        prompt = PromptTemplates.one_step(theme)
        response = self._call_llm(prompt, temperature=0.8)
        
        # Parse with validation
        groups = self._parse_puzzle_response_validated(response)
        
        # Ensure valid groups with no duplicates
        groups = self._ensure_valid_groups(groups)
        
        # Assign difficulties based on similarity
        groups = self._assign_difficulties_targeted(groups)
        
        puzzle = ConnectionsPuzzle(groups=groups)
        puzzle.metadata['generation_method'] = 'one_step'
        puzzle.metadata['theme'] = theme
        
        return puzzle
    
    def _parse_puzzle_response_validated(self, response: str) -> List[WordGroup]:
        """Parse LLM response with strict word validation"""
        
        groups = []
        lines = response.strip().split('\n')
        
        color_map = {
            'YELLOW': DifficultyColor.YELLOW,
            'GREEN': DifficultyColor.GREEN,
            'BLUE': DifficultyColor.BLUE,
            'PURPLE': DifficultyColor.PURPLE
        }
        
        used_words = set()
        
        for line in lines:
            if not line.strip():
                continue
            
            for color_name, color_enum in color_map.items():
                if color_name in line.upper():
                    try:
                        # Extract category and words
                        parts = line.split(':', 1)
                        if len(parts) < 2:
                            continue
                        
                        content = parts[1].strip()
                        
                        # Split category from words
                        if '-' in content:
                            category, words_str = content.split('-', 1)
                        elif '–' in content:
                            category, words_str = content.split('–', 1)
                        else:
                            category = f"{color_name} Category"
                            words_str = content
                        
                        # Clean and truncate category name properly
                        category = category.strip().strip('[]"\'')
                        
                        # Truncate at word boundary if too long
                        if len(category) > 35:
                            # Find last space before position 35
                            last_space = category[:35].rfind(' ')
                            if last_space > 15:
                                category = category[:last_space]
                            else:
                                category = category[:35]
                        
                        # Remove any trailing punctuation or partial words
                        category = category.rstrip('.,;:- ')
                        
                        # Extract and validate words
                        words = extract_valid_words(words_str, used_words)
                        
                        if len(words) >= 4:
                            words = words[:4]
                            used_words.update(words)
                            
                            groups.append(WordGroup(
                                words=words,
                                category=category,
                                difficulty=color_enum
                            ))
                    except Exception as e:
                        pass
                    break
        
        return groups
    
    # ================================================================
    # INTENTIONAL OVERLAP GENERATION (ENHANCED FOR MAXIMUM DIFFICULTY)
    # ================================================================
    
    def _generate_intentional_overlap(self, theme: Optional[str] = None) -> ConnectionsPuzzle:
        """
        Enhanced Intentional Overlap - creates MAXIMUM deception.
        
        Strategy: Each group contains words that SEEM to belong to other groups.
        We dynamically discover words with multiple meanings to create traps.
        """
        
        # Step 1: Dynamically discover polysemous (multi-meaning) words using LLM
        discovery_prompt = """List 20 common English words that have MULTIPLE DISTINCT meanings.
Each word should work in at least 2 very different contexts.

Format each line as:
WORD: meaning1, meaning2, meaning3

Good examples:
BANK: financial institution, river edge, to tilt an airplane
SPRING: season, coiled metal, water source, to jump
BAT: flying mammal, baseball equipment
SEAL: marine animal, to close, official stamp
CRANE: bird, construction equipment, to stretch neck

List 20 such words (different from examples):"""

        trap_words_response = self._call_llm(discovery_prompt, temperature=0.8)
        
        # Parse discovered trap words
        discovered_traps = {}
        for line in trap_words_response.split('\n'):
            if ':' in line:
                parts = line.split(':', 1)
                word = clean_word(parts[0])
                if word and len(word) >= 3:
                    meanings = [m.strip() for m in parts[1].split(',') if m.strip()]
                    if len(meanings) >= 2:
                        discovered_traps[word] = meanings
        
        # If discovery failed, use minimal seed set and expand via LLM
        if len(discovered_traps) < 8:
            seed_traps = ["BANK", "SPRING", "ROCK", "MATCH", "POUND", "SEAL", "CRANE", "WAVE"]
            for word in seed_traps:
                if word not in discovered_traps:
                    meaning_prompt = f"List 3 different meanings for the word '{word}'. Just list them separated by commas."
                    meanings_response = self._call_llm(meaning_prompt, temperature=0.3)
                    meanings = [m.strip() for m in meanings_response.split(',') if m.strip()][:3]
                    if meanings:
                        discovered_traps[word] = meanings
        
        # Step 2: Find 4 trap words that could form a false connection
        # Group trap words by their meanings to find overlaps
        trap_words = list(discovered_traps.keys())
        if len(trap_words) < 4:
            # Emergency: generate more
            for _ in range(3):
                fb = generate_fallback_group(set(trap_words), self.embedder, self.knowledge_base)
                for w in fb.words:
                    if w not in trap_words:
                        trap_words.append(w)
                        discovered_traps[w] = [f"meaning of {w}"]
        
        # Use embeddings to find 4 words that seem related (high similarity)
        # but actually have different primary uses
        if len(trap_words) >= 4:
            embeddings = self.embedder.encode(trap_words)
            sim_matrix = cosine_similarity(embeddings)
            
            # Find best quartet with high mutual similarity
            best_quartet = None
            best_score = -1
            
            combos = list(itertools.combinations(range(len(trap_words)), 4))
            if len(combos) > 100:
                combos = random.sample(combos, 100)
            
            for combo in combos:
                sub_sim = sim_matrix[np.ix_(combo, combo)]
                score = (sub_sim.sum() - 4) / 12
                if score > best_score:
                    best_score = score
                    best_quartet = combo
            
            if best_quartet:
                anchor_words = [trap_words[i] for i in best_quartet]
            else:
                anchor_words = random.sample(trap_words, 4)
        else:
            anchor_words = trap_words[:4]
        
        used_words = set()
        groups = []
        
        # Step 3: For each anchor word, create a group using a specific meaning
        for i, anchor in enumerate(anchor_words):
            # Get meanings for this word (discovered or ask LLM)
            if anchor in discovered_traps and discovered_traps[anchor]:
                meanings = discovered_traps[anchor]
                meaning_idx = min(i, len(meanings) - 1)
                target_meaning = meanings[meaning_idx]
            else:
                # Ask LLM for meaning
                meaning_prompt = f"What is one meaning of the word '{anchor}'? Reply with just the meaning."
                target_meaning = self._call_llm(meaning_prompt, temperature=0.3).strip()
            
            # Generate companions for this anchor using specific meaning
            prompt = f"""Create a word group for a DIFFICULT Connections puzzle.

The word "{anchor}" will be in this group, using its meaning: "{target_meaning}"

Generate 3 OTHER words that:
1. Fit the same category as {anchor} (when {anchor} means "{target_meaning}")
2. Are single common English words (uppercase, no phrases)
3. Ideally also have alternate meanings that could create confusion

DO NOT include: {', '.join(used_words)}

Output format:
Category: [specific category name for this meaning]
Words: WORD1, WORD2, WORD3"""

            response = self._call_llm(prompt, temperature=0.9)
            
            # Parse response
            category_name = f"{anchor}'s category"
            companion_words = []
            
            for line in response.split('\n'):
                line_lower = line.lower()
                if 'category:' in line_lower:
                    cat_part = line.split(':', 1)[1].strip().strip('[]"\'')
                    if len(cat_part) < 40 and len(cat_part) > 2:
                        category_name = cat_part
                elif 'words:' in line_lower or (',' in line and len(companion_words) == 0):
                    words_part = line.split(':', 1)[-1] if ':' in line else line
                    companion_words = extract_valid_words(words_part, used_words | {anchor})
            
            # Need more companions? Generate dynamically
            while len(companion_words) < 3:
                fb = generate_fallback_group(used_words | {anchor}, self.embedder, self.knowledge_base)
                for w in fb.words:
                    if w not in used_words and w != anchor and len(companion_words) < 3:
                        companion_words.append(w)
            
            # Build the group: anchor + 3 companions
            group_words = [anchor] + companion_words[:3]
            used_words.update(group_words)
            
            # Assign difficulty - make later groups harder
            difficulties = [DifficultyColor.YELLOW, DifficultyColor.GREEN, 
                          DifficultyColor.BLUE, DifficultyColor.PURPLE]
            
            groups.append(WordGroup(
                words=group_words,
                category=category_name,
                difficulty=difficulties[i]
            ))
        
        # Step 4: Reassign difficulties based on actual semantic similarity
        groups = self._assign_difficulties_targeted(groups)
        
        puzzle = ConnectionsPuzzle(groups=groups)
        puzzle.metadata['has_intentional_overlap'] = True
        puzzle.metadata['generation_method'] = 'intentional_overlap'
        puzzle.metadata['anchor_words'] = anchor_words
        puzzle.metadata['discovered_trap_count'] = len(discovered_traps)
        
        return puzzle
    
    # ================================================================
    # FALSE GROUP GENERATION (ENHANCED FOR MAXIMUM DECEPTION)
    # ================================================================
    
    def _generate_false_group(self, theme: Optional[str], 
                             seeded_words: Optional[List[str]] = None) -> ConnectionsPuzzle:
        """
        Enhanced False Group generation with MAXIMUM deception.
        DYNAMICALLY discovers words that seem related but have different meanings.
        """
        
        # Step 1: Dynamically discover a false group using LLM
        discovery_prompt = """Find 4 English words that:
1. All SEEM to belong to the same category at first glance
2. But each actually has a DIFFERENT primary meaning when used in everyday speech

For example, these 4 words seem like "body parts" but aren't:
- PALM (seems body part, also a tree)
- TEMPLE (seems body part, also a building)  
- PUPIL (seems body part, also a student)
- NAIL (seems body part, also hardware)

Now generate a DIFFERENT set of 4 words that create a similar trap.
These words should strongly appear to be related but each has an alternate meaning.

Format:
Apparent category: [what they seem to be]
Word 1: WORD - seems like [apparent], but also means [alternate]
Word 2: WORD - seems like [apparent], but also means [alternate]
Word 3: WORD - seems like [apparent], but also means [alternate]
Word 4: WORD - seems like [apparent], but also means [alternate]"""

        if theme:
            discovery_prompt += f"\n\nTry to make the apparent category related to: {theme}"
        
        response = self._call_llm(discovery_prompt, temperature=0.9)
        
        # Parse the discovered false group
        seed_words = []
        meanings = []
        false_group_name = "Deceptive Group"
        
        for line in response.split('\n'):
            line_clean = line.strip()
            
            if 'apparent category:' in line_clean.lower():
                cat_part = line_clean.split(':', 1)[1].strip()
                false_group_name = f"Things that seem like {cat_part}"
            elif line_clean.startswith('Word') and ':' in line_clean:
                # Extract the word
                parts = line_clean.split(':', 1)
                if len(parts) > 1:
                    word_part = parts[1].strip()
                    # Get the word (before any dash or explanation)
                    word = word_part.split('-')[0].split()[0].strip().upper()
                    word = clean_word(word)
                    if word and len(word) >= 2:
                        seed_words.append(word)
                        # Extract meanings if available
                        if 'but also' in word_part.lower():
                            alt_meaning = word_part.lower().split('but also')[-1].strip()
                            meanings.append(alt_meaning)
                        else:
                            meanings.append(f"alternate meaning of {word}")
        
        # If discovery failed, try again with simpler prompt
        if len(seed_words) < 4:
            simple_prompt = """List 4 words that all seem like they're related to ANIMALS, but each has a completely different primary meaning:
Example format:
CRANE, SEAL, BAT, BUFFALO
(CRANE=machine, SEAL=to close, BAT=sports, BUFFALO=city/verb)

Now give me a DIFFERENT set of 4 such words (not animals - pick a different category):"""
            
            response = self._call_llm(simple_prompt, temperature=0.9)
            
            # Try to extract 4 words from response
            potential_words = extract_valid_words(response, set())
            if potential_words:
                seed_words = potential_words[:4]
                meanings = [f"alternate meaning {i+1}" for i in range(4)]
                false_group_name = "Deceptively similar words"
        
        # Ensure we have exactly 4 seed words
        while len(seed_words) < 4:
            # Generate more using LLM
            fb = generate_fallback_group(set(seed_words), self.embedder, self.knowledge_base)
            for w in fb.words:
                if w not in seed_words:
                    seed_words.append(w)
                    meanings.append(f"alternate meaning of {w}")
                if len(seed_words) >= 4:
                    break
        
        seed_words = seed_words[:4]
        meanings = meanings[:4]
        
        used_words = set(seed_words)
        groups = []
        
        # Step 2: For each seed word, create a group using its alternate meaning
        for i, seed_word in enumerate(seed_words):
            meaning_hint = meanings[i] if i < len(meanings) else "alternate meaning"
            
            prompt = f"""Create a word group for a Connections puzzle.

The word "{seed_word}" will be in this group.
Use "{seed_word}" with its meaning: {meaning_hint}

Generate 3 OTHER words that:
1. Fit the same category as {seed_word} (with this meaning)
2. Are single common English words (uppercase)

DO NOT include: {', '.join(used_words - {seed_word})}

Format:
Category: [specific name for this category]
Words: WORD1, WORD2, WORD3"""
            
            response = self._call_llm(prompt, temperature=0.8)
            
            # Parse response
            new_category = f"Group {i + 1}"
            companion_words = []
            
            for line in response.split('\n'):
                line_lower = line.lower()
                if 'category:' in line_lower:
                    cat_part = line.split(':', 1)[1].strip()
                    cat_part = cat_part.strip('[]"\'-')
                    if len(cat_part) < 35 and len(cat_part) > 1:
                        new_category = cat_part
                elif 'words:' in line_lower or (',' in line and len(companion_words) == 0):
                    words_part = line.split(':', 1)[-1] if ':' in line else line
                    companion_words = extract_valid_words(words_part, used_words)[:3]
            
            # Ensure we have 3 companion words
            while len(companion_words) < 3:
                fallback = generate_fallback_group(used_words, self.embedder, self.knowledge_base)
                for w in fallback.words:
                    if w not in used_words:
                        companion_words.append(w)
                        used_words.add(w)
                    if len(companion_words) >= 3:
                        break
            
            # Create group: seed word + 3 companions
            group_words = [seed_word] + companion_words[:3]
            used_words.update(group_words)
            
            groups.append(WordGroup(
                words=group_words,
                category=new_category,
                difficulty=DifficultyColor.GREEN
            ))
        
        # Ensure exactly 4 groups
        while len(groups) < 4:
            fallback = generate_fallback_group(used_words, self.embedder, self.knowledge_base)
            groups.append(fallback)
            used_words.update(fallback.words)
        
        groups = groups[:4]
        
        # The false group is the 4 seed words - they're IN the puzzle but in different groups
        false_group = WordGroup(
            words=seed_words,
            category=false_group_name,
            difficulty=DifficultyColor.PURPLE
        )
        
        groups = self._assign_difficulties_targeted(groups)
        
        puzzle = ConnectionsPuzzle(groups=groups, false_group=false_group)
        puzzle.metadata['has_false_group'] = True
        puzzle.metadata['generation_method'] = 'false_group'
        puzzle.metadata['false_group_words'] = seed_words
        puzzle.metadata['false_group_trap'] = false_group_name
        puzzle.metadata['dynamically_discovered'] = True
        
        return puzzle
    
    def _generate_false_group_seeded(self, seeded_words: Optional[List[str]]) -> ConnectionsPuzzle:
        """Generate puzzle with specific false group words"""
        
        if not seeded_words or len(seeded_words) < 4:
            seeded_words = random.sample(self._generate_diverse_word_pool(None, 20), 4)
        
        # Clean and validate seeded words
        clean_seeds = []
        for w in seeded_words:
            cleaned = clean_word(w)
            if is_valid_word(cleaned):
                clean_seeds.append(cleaned)
        
        while len(clean_seeds) < 4:
            fallback = generate_fallback_group(set(clean_seeds), self.embedder, self.knowledge_base)
            for w in fallback.words:
                if w not in clean_seeds:
                    clean_seeds.append(w)
                if len(clean_seeds) >= 4:
                    break
        
        seeded_words = clean_seeds[:4]
        used_words = set(seeded_words)
        groups = []
        
        # Create 4 groups, each containing one seed word + 3 new words
        for i, seed in enumerate(seeded_words):
            prompt = f"""Create a category that includes the word "{seed}".
Provide 3 OTHER words (not "{seed}") that fit the same category.

IMPORTANT:
- Do NOT include "{seed}" in your list
- Do NOT include: {', '.join(used_words)}
- Output ONLY single words

Format:
Category: [name]
Words: word1, word2, word3"""
            
            response = self._call_llm(prompt)
            
            new_category = f"Group {i + 1}"
            new_words = []
            
            for line in response.split('\n'):
                if 'category:' in line.lower():
                    cat_part = line.split(':', 1)[1].strip()
                    if len(cat_part) < 40:
                        new_category = cat_part
                elif 'words:' in line.lower() or (',' in line and len(new_words) == 0):
                    words_part = line.split(':', 1)[-1] if ':' in line else line
                    new_words = extract_valid_words(words_part, used_words)[:3]
            
            # Ensure we have 3 new words
            while len(new_words) < 3:
                fallback = generate_fallback_group(used_words, self.embedder, self.knowledge_base)
                for w in fallback.words:
                    if w not in used_words:
                        new_words.append(w)
                        used_words.add(w)
                    if len(new_words) >= 3:
                        break
            
            group_words = [seed] + new_words[:3]
            used_words.update(group_words)
            
            groups.append(WordGroup(
                words=group_words,
                category=new_category,
                difficulty=DifficultyColor.GREEN
            ))
        
        # Create false group
        false_group = WordGroup(
            words=seeded_words,
            category="Seeded False Group",
            difficulty=DifficultyColor.PURPLE
        )
        
        groups = self._assign_difficulties_targeted(groups)
        puzzle = ConnectionsPuzzle(groups=groups, false_group=false_group)
        puzzle.metadata['has_false_group'] = True
        puzzle.metadata['false_group_seeded'] = True
        
        return puzzle
    
    # ================================================================
    # TREE OF THOUGHTS GENERATION (FIXED)
    # ================================================================
    
    def _generate_tree_of_thoughts(self, theme: Optional[str]) -> ConnectionsPuzzle:
        """Tree of Thoughts generation with proper word validation"""
        
        # Initialize tree root
        root = TreeOfThoughtsNode({"theme": theme, "groups": []})
        
        # Step 1: Choose category types
        category_prompt = PromptTemplates.tree_of_thoughts_categories(theme)
        category_response = self._call_llm(category_prompt)
        
        # Parse category types - clean them up
        category_types = []
        for line in category_response.split('\n'):
            line = line.strip()
            # Remove leading numbers, dashes, bullets
            line = line.lstrip('0123456789.-•*) ')
            # Remove trailing punctuation
            line = line.rstrip('.,;:')
            if line and len(line) < 50 and len(line) > 2:
                category_types.append(line)
        
        if len(category_types) < 4:
            category_types = ["Words meaning happy", "Types of music genres", "Kitchen utensils", "Sports equipment"]
        
        category_types = category_types[:4]
        
        # Step 2: Generate word pools for each category
        used_words = set()
        
        for cat_type in category_types:
            child_state = {"category_type": cat_type, "words": []}
            child = root.add_child(child_state)
            
            word_prompt = f"""Generate exactly 8 single words for the category: {cat_type}
{"Related to theme: " + theme if theme else ""}

Output ONLY 8 words, comma-separated, nothing else:"""
            
            word_response = self._call_llm(word_prompt)
            
            # Extract valid words
            words = extract_valid_words(word_response, used_words)
            
            child.state["word_pool"] = words
            
            if len(words) >= 4:
                selected = words[:4]
                child.state["selected_words"] = selected
                child.score = self._score_word_group(selected)
                used_words.update(selected)
        
        # Step 3: Build groups from best branches
        groups = []
        used_in_groups = set()
        
        for child in sorted(root.children, key=lambda x: x.score, reverse=True)[:4]:
            if "selected_words" in child.state and len(child.state["selected_words"]) >= 4:
                words_to_add = [w for w in child.state["selected_words"] if w not in used_in_groups][:4]
                
                if len(words_to_add) == 4:
                    # Clean category name
                    cat_name = child.state.get("category_type", "Category")
                    cat_name = cat_name.lstrip('0123456789.-•*) ').rstrip('.,;:')
                    
                    groups.append(WordGroup(
                        words=words_to_add,
                        category=cat_name,
                        difficulty=DifficultyColor.YELLOW
                    ))
                    used_in_groups.update(words_to_add)
        
        # Fill missing groups
        while len(groups) < 4:
            fallback = generate_fallback_group(used_in_groups, self.embedder, self.knowledge_base)
            groups.append(fallback)
            used_in_groups.update(fallback.words)
        
        groups = groups[:4]
        groups = self._assign_difficulties_targeted(groups)
        
        puzzle = ConnectionsPuzzle(groups=groups)
        puzzle.metadata['generation_method'] = 'tree_of_thoughts'
        
        return puzzle
    
    # ================================================================
    # TRICO GENERATION (FULLY DYNAMIC - NO HARDCODING)
    # ================================================================
    
    def _generate_trico_puzzle(self, theme: Optional[str]) -> ConnectionsPuzzle:
        """
        Generate puzzle using TriCO with FULLY DYNAMIC pattern discovery.
        
        NO HARDCODED WORD LISTS - everything is discovered dynamically:
        1. Semantic groups: LLM generates + validates
        2. Phonetic groups: pronouncing library finds real rhymes
        3. Orthographic groups: Pattern analysis on word pool
        """
        
        print("Generating TriCO puzzle")
        
        max_attempts = 5
        
        for attempt in range(max_attempts):
            try:
                # Step 1: Generate diverse word pool via LLM
                print(f"Step 1: Generating word pool (attempt {attempt + 1})...")
                word_pool = self._generate_dynamic_word_pool(theme)
                print(f"  Generated {len(word_pool)} words")
                
                # Step 2: Find semantic groups using embeddings + LLM validation
                print("Step 2: Finding semantic groups...")
                semantic_groups = self._find_dynamic_semantic_groups(word_pool)
                print(f"  Found {len(semantic_groups)} semantic groups")
                
                # Step 3: Find phonetic groups using pronouncing library
                print("Step 3: Finding phonetic rhyme groups...")
                used_words = set(w for g in semantic_groups for w in g.words)
                remaining_pool = [w for w in word_pool if w not in used_words]
                phonetic_groups = self._find_dynamic_rhyme_groups(remaining_pool)
                print(f"  Found {len(phonetic_groups)} phonetic groups")
                
                # Step 4: Find orthographic groups from remaining words
                print("Step 4: Finding orthographic groups...")
                used_words.update(w for g in phonetic_groups for w in g.words)
                remaining_pool = [w for w in word_pool if w not in used_words]
                ortho_groups = self._find_dynamic_orthographic_groups(remaining_pool)
                print(f"  Found {len(ortho_groups)} orthographic groups")
                
                # Step 5: Select 4 diverse groups
                print("Step 5: Selecting diverse groups...")
                selected = self._select_trico_groups(semantic_groups, phonetic_groups, ortho_groups)
                
                if len(selected) != 4:
                    print(f"  Only got {len(selected)} groups, retrying...")
                    continue
                
                # Step 6: Final quality check
                print("Step 6: Final quality validation...")
                if not self._validate_trico_final(selected):
                    print("  Quality check failed, retrying...")
                    continue
                
                # Step 7: Assign difficulties
                print("Step 7: Assigning difficulties...")
                selected = self._assign_trico_difficulties(selected)
                
                # Create puzzle
                puzzle = ConnectionsPuzzle(groups=selected)
                puzzle.metadata['generation_method'] = 'trico'
                puzzle.metadata['ultra_hard'] = True
                puzzle.metadata['expected_solve_rate'] = 0.25
                puzzle.metadata['fully_dynamic'] = True  # Flag that nothing was hardcoded
                
                # Record view distribution
                view_counts = {}
                for g in selected:
                    v = g.primary_view or 'sem'
                    view_counts[v] = view_counts.get(v, 0) + 1
                puzzle.metadata['view_distribution'] = view_counts
                
                print("TriCO puzzle generated successfully!")
                return puzzle
                
            except Exception as e:
                print(f"TriCO attempt {attempt + 1} failed: {e}")
                import traceback
                traceback.print_exc()
        
        # Fallback
        print("TriCO failed, falling back to Tree of Thoughts...")
        return self._generate_tree_of_thoughts(theme)
    
    def _generate_dynamic_word_pool(self, theme: Optional[str]) -> List[str]:
        """Generate word pool dynamically via LLM - NO HARDCODED WORDS"""
        
        word_pool = set()
        
        # Generate words from various domains
        prompts = [
            "List 15 common single-word nouns (everyday objects, animals, foods):",
            "List 15 single-word verbs in present tense:",
            "List 15 single-word adjectives:",
            "List 10 types of animals (single words):",
            "List 10 colors (single words):",
            "List 10 foods (single words):",
            "List 10 professions (single words):",
            "List 10 sports (single words):",
            "List 10 musical terms or instruments (single words):",
            "List 10 weather-related words (single words):",
            "List 10 emotions (single words):",
            "List 10 body parts (single words):",
        ]
        
        # Add theme-related words
        if theme:
            prompts.insert(0, f"List 15 words related to '{theme}' (single words only):")
        
        for prompt in prompts:
            try:
                response = self._call_llm(prompt, temperature=0.7)
                words = extract_valid_words(response, word_pool)
                word_pool.update(words[:12])
            except:
                continue
        
        # Generate GROUPS of rhyming words (not just words that might rhyme)
        rhyme_prompts = [
            "List 6 words that rhyme with GATE (same '-ate' sound): ",
            "List 6 words that rhyme with RING (same '-ing' sound): ",
            "List 6 words that rhyme with TRAIN (same '-ain' sound): ",
            "List 6 words that rhyme with LIGHT (same '-ight' sound): ",
            "List 6 words that rhyme with CALL (same '-all' sound): ",
            "List 6 words that rhyme with DREAM (same '-eam' sound): ",
        ]
        
        for prompt in rhyme_prompts:
            try:
                response = self._call_llm(prompt, temperature=0.5)
                words = extract_valid_words(response, word_pool)
                word_pool.update(words[:6])
            except:
                continue
        
        result = list(word_pool)
        random.shuffle(result)
        return result[:80]  # Return up to 80 words
    
    def _find_dynamic_semantic_groups(self, word_pool: List[str]) -> List[WordGroup]:
        """Find semantic groups using embeddings + LLM validation - NO HARDCODED CATEGORIES"""
        
        groups = []
        
        if len(word_pool) < 12:
            return groups
        
        # Use embeddings to cluster words
        embeddings = self.embedder.encode(word_pool)
        
        # Try multiple clustering attempts
        used_words = set()
        
        for n_clusters in [8, 10, 12]:
            if len(word_pool) < n_clusters:
                continue
            
            try:
                kmeans = KMeans(n_clusters=n_clusters, random_state=42 + n_clusters, n_init=10)
                labels = kmeans.fit_predict(embeddings)
                
                for cluster_id in range(n_clusters):
                    if len(groups) >= 4:
                        break
                    
                    cluster_words = [word_pool[i] for i in range(len(word_pool)) 
                                    if labels[i] == cluster_id and word_pool[i] not in used_words]
                    
                    if len(cluster_words) < 4:
                        continue
                    
                    # Calculate coherence
                    cluster_emb = self.embedder.encode(cluster_words[:6])
                    sim_matrix = cosine_similarity(cluster_emb)
                    coherence = (sim_matrix.sum() - len(cluster_emb)) / max(len(cluster_emb) * (len(cluster_emb) - 1), 1)
                    
                    if coherence < 0.35:
                        continue
                    
                    # Ask LLM for category name
                    candidate_words = cluster_words[:4]
                    category_prompt = f"""What specific category do these words belong to: {', '.join(candidate_words)}?
Give a short category name (2-4 words). Examples: "Types of Fish", "Kitchen Utensils", "Emotions"
IMPORTANT: All words must fit ONE specific category. Don't use "and" to combine categories.
If they don't ALL share a clear single category, respond with "NO CATEGORY".
Answer:"""
                    
                    category = self._call_llm(category_prompt, temperature=0.3).strip()
                    category = category.split('\n')[0].strip('"\'[](){}')
                    
                    # Reject mixed categories (contain "and", "or", "/")
                    if any(sep in category.lower() for sep in [' and ', ' or ', '/', ' & ']):
                        continue
                    
                    if 'no category' in category.lower() or len(category) < 3:
                        continue
                    
                    # Validate each word belongs to category
                    valid_words = []
                    for word in candidate_words:
                        check_prompt = f'Does "{word}" belong to the category "{category}"? Answer only yes or no:'
                        answer = self._call_llm(check_prompt, temperature=0.1).strip().lower()
                        if 'yes' in answer:
                            valid_words.append(word)
                    
                    if len(valid_words) >= 4:
                        groups.append(WordGroup(
                            words=valid_words[:4],
                            category=category[:35],
                            difficulty=DifficultyColor.YELLOW,
                            primary_view='sem',
                            similarity_score=coherence
                        ))
                        used_words.update(valid_words[:4])
            except Exception as e:
                continue
        
        return groups[:4]
    
    def _find_dynamic_rhyme_groups(self, word_pool: List[str]) -> List[WordGroup]:
        """Find rhyming groups using pronouncing library - REAL PHONETIC RHYMES"""
        
        groups = []
        
        try:
            import pronouncing
        except ImportError:
            print("  Warning: pronouncing library not available, using LLM fallback")
            return self._find_rhymes_via_llm(word_pool)
        
        # Build rhyme groups using CMU dictionary
        rhyme_buckets = {}  # rhyme_part -> list of words
        
        for word in word_pool:
            try:
                phones_list = pronouncing.phones_for_word(word.lower())
                if not phones_list:
                    continue
                
                phones = phones_list[0]
                rhyme_part = pronouncing.rhyming_part(phones)
                
                if rhyme_part:
                    if rhyme_part not in rhyme_buckets:
                        rhyme_buckets[rhyme_part] = []
                    rhyme_buckets[rhyme_part].append(word.upper())
            except:
                continue
        
        # Find buckets with 4+ words
        used_words = set()
        for rhyme_part, words in sorted(rhyme_buckets.items(), key=lambda x: -len(x[1])):
            available = [w for w in words if w not in used_words]
            
            if len(available) >= 4:
                selected = available[:4]
                
                # Get a readable rhyme description
                # Extract the ending sound for category name
                sample_word = selected[0].lower()
                ending = self._get_rhyme_ending(sample_word)
                
                groups.append(WordGroup(
                    words=selected,
                    category=f"Rhymes with '-{ending.upper()}'",
                    difficulty=DifficultyColor.BLUE,
                    primary_view='pho'
                ))
                used_words.update(selected)
                
                if len(groups) >= 2:
                    break
        
        return groups
    
    def _get_rhyme_ending(self, word: str) -> str:
        """Get a human-readable rhyme ending for a word"""
        try:
            import pronouncing
            phones_list = pronouncing.phones_for_word(word.lower())
            if phones_list:
                phones = phones_list[0]
                # Find the vowel and everything after
                parts = phones.split()
                for i, part in enumerate(parts):
                    if any(c.isdigit() for c in part):  # Vowels have stress markers (digits)
                        # Return from this vowel onwards as approximate ending
                        remaining = ''.join(p.rstrip('012') for p in parts[i:])
                        # Map to approximate spelling
                        return self._phones_to_spelling(remaining, word)
        except:
            pass
        
        # Fallback: return last 2-3 letters
        return word[-3:] if len(word) > 3 else word[-2:]
    
    def _phones_to_spelling(self, phones: str, word: str) -> str:
        """Convert phoneme string to approximate spelling based on word ending"""
        # Use the actual word ending as it's more readable
        word = word.lower()
        
        # Try different ending lengths to find a common pattern
        for length in [4, 3, 2]:
            if len(word) >= length:
                ending = word[-length:]
                # Check if it looks like a valid ending (has a vowel)
                if any(c in 'aeiou' for c in ending):
                    return ending.upper()
        
        return word[-2:].upper()
    
    def _find_rhymes_via_llm(self, word_pool: List[str]) -> List[WordGroup]:
        """Fallback: Find rhymes using LLM when pronouncing library unavailable"""
        
        groups = []
        used_words = set()
        
        # Ask LLM to identify rhyming groups
        words_str = ', '.join(word_pool[:40])
        prompt = f"""From these words, identify groups of 4+ words that RHYME (same ending sound):
{words_str}

List each rhyming group on a separate line in format: WORD1, WORD2, WORD3, WORD4
Only include groups where ALL words truly rhyme (same sound, not just spelling).
If no clear rhyming groups exist, say "NONE"."""
        
        response = self._call_llm(prompt, temperature=0.3)
        
        if 'none' in response.lower():
            return groups
        
        for line in response.strip().split('\n'):
            if len(groups) >= 2:
                break
            
            words = [w.strip().upper() for w in line.split(',') if w.strip()]
            words = [w for w in words if w in [wp.upper() for wp in word_pool] and w not in used_words]
            
            if len(words) >= 4:
                selected = words[:4]
                
                # Validate they actually rhyme
                validate_prompt = f'Do these words all rhyme (same ending sound): {", ".join(selected)}? Answer yes or no:'
                answer = self._call_llm(validate_prompt, temperature=0.1).strip().lower()
                
                if 'yes' in answer:
                    ending = selected[0][-3:] if len(selected[0]) > 3 else selected[0][-2:]
                    groups.append(WordGroup(
                        words=selected,
                        category=f"Rhymes with '-{ending}'",
                        difficulty=DifficultyColor.BLUE,
                        primary_view='pho'
                    ))
                    used_words.update(selected)
        
        return groups
    
    def _find_dynamic_orthographic_groups(self, word_pool: List[str]) -> List[WordGroup]:
        """Find orthographic pattern groups dynamically - NO HARDCODED WORDS"""
        
        groups = []
        used_words = set()
        
        # Group by word length
        length_buckets = {}
        for word in word_pool:
            L = len(word)
            if L >= 3:
                if L not in length_buckets:
                    length_buckets[L] = []
                length_buckets[L].append(word.upper())
        
        # Find length groups with 4+ words
        for length in sorted(length_buckets.keys()):
            if len(groups) >= 2:
                break
            
            available = [w for w in length_buckets[length] if w not in used_words]
            if len(available) >= 4 and length >= 4:
                selected = available[:4]
                groups.append(WordGroup(
                    words=selected,
                    category=f"{length}-letter words",
                    difficulty=DifficultyColor.PURPLE,
                    primary_view='orth'
                ))
                used_words.update(selected)
        
        # Group by prefix (first 2 letters)
        prefix_buckets = {}
        for word in word_pool:
            if len(word) >= 3 and word.upper() not in used_words:
                prefix = word[:2].upper()
                if prefix not in prefix_buckets:
                    prefix_buckets[prefix] = []
                prefix_buckets[prefix].append(word.upper())
        
        for prefix, words in sorted(prefix_buckets.items(), key=lambda x: -len(x[1])):
            if len(groups) >= 2:
                break
            
            if len(words) >= 4:
                selected = words[:4]
                groups.append(WordGroup(
                    words=selected,
                    category=f"Start with '{prefix}'",
                    difficulty=DifficultyColor.PURPLE,
                    primary_view='orth'
                ))
                used_words.update(selected)
        
        # Group by suffix (last 2 letters)
        suffix_buckets = {}
        for word in word_pool:
            if len(word) >= 3 and word.upper() not in used_words:
                suffix = word[-2:].upper()
                if suffix not in suffix_buckets:
                    suffix_buckets[suffix] = []
                suffix_buckets[suffix].append(word.upper())
        
        for suffix, words in sorted(suffix_buckets.items(), key=lambda x: -len(x[1])):
            if len(groups) >= 2:
                break
            
            if len(words) >= 4:
                selected = words[:4]
                groups.append(WordGroup(
                    words=selected,
                    category=f"End with '{suffix}'",
                    difficulty=DifficultyColor.PURPLE,
                    primary_view='orth'
                ))
                used_words.update(selected)
        
        return groups[:2]
    
    def _select_trico_groups(self, semantic: List[WordGroup], phonetic: List[WordGroup],
                             orthographic: List[WordGroup]) -> List[WordGroup]:
        """Select 4 groups with strict diversity rules"""
        
        selected = []
        used_words = set()
        
        def can_add(group):
            return len(group.words) == 4 and not any(w in used_words for w in group.words)
        
        def add_group(group):
            selected.append(group)
            used_words.update(group.words)
        
        # Priority 1: Add 2-3 semantic groups
        for g in semantic:
            if can_add(g) and len([s for s in selected if s.primary_view == 'sem']) < 3:
                add_group(g)
        
        # Priority 2: Add exactly 1 phonetic group
        for g in phonetic:
            if can_add(g) and len(selected) < 4:
                add_group(g)
                break
        
        # Priority 3: Add 1 orthographic group if needed
        if len(selected) < 4:
            for g in orthographic:
                if can_add(g):
                    add_group(g)
                    break
        
        # Fill remaining with semantic
        for g in semantic:
            if can_add(g) and len(selected) < 4:
                add_group(g)
        
        return selected
    
    def _validate_trico_final(self, groups: List[WordGroup]) -> bool:
        """Final quality validation for TriCO puzzle"""
        
        if len(groups) != 4:
            return False
        
        # Check all groups have exactly 4 unique words
        all_words = []
        for g in groups:
            if len(g.words) != 4:
                return False
            all_words.extend(g.words)
        
        if len(all_words) != 16 or len(set(all_words)) != 16:
            return False
        
        # Check view distribution
        view_counts = {}
        for g in groups:
            v = g.primary_view or 'sem'
            view_counts[v] = view_counts.get(v, 0) + 1
        
        # Must have at least 2 semantic groups
        if view_counts.get('sem', 0) < 2:
            print(f"    Only {view_counts.get('sem', 0)} semantic groups (need 2+)")
            return False
        
        # Validate semantic groups with LLM
        for g in groups:
            if g.primary_view == 'sem':
                # Reject mixed categories
                if any(sep in g.category.lower() for sep in [' and ', ' or ', '/', ' & ']):
                    print(f"    Category '{g.category}' is a mixed category (rejected)")
                    return False
                
                # Validate EACH word individually
                for word in g.words:
                    check_prompt = f'Is "{word}" a/an {g.category.lower()}? Answer ONLY yes or no:'
                    answer = self._call_llm(check_prompt, temperature=0.1).strip().lower()
                    if 'no' in answer:
                        print(f"    Word '{word}' does not fit category '{g.category}'")
                        return False
        
        return True
    
    def _assign_trico_difficulties(self, groups: List[WordGroup]) -> List[WordGroup]:
        """Assign difficulties based on pattern type and obscurity"""
        
        # Sort by how obvious the pattern is
        # Semantic groups with clear categories = easiest
        # Phonetic groups = medium
        # Orthographic groups = hardest
        
        def obscurity_score(g):
            if g.primary_view == 'sem':
                return 0 + (0.5 if g.similarity_score and g.similarity_score > 0.5 else 1)
            elif g.primary_view == 'pho':
                return 2
            else:  # orth
                return 3
        
        sorted_groups = sorted(groups, key=obscurity_score)
        
        colors = [DifficultyColor.YELLOW, DifficultyColor.GREEN, 
                  DifficultyColor.BLUE, DifficultyColor.PURPLE]
        
        for i, group in enumerate(sorted_groups):
            if i < len(colors):
                group.difficulty = colors[i]
        
        return sorted_groups
    
    def _trico_initial_partition(self, words: List[str], sims: Dict[str, np.ndarray]) -> Tuple[List[WordGroup], List[str], List[str]]:
        """Create initial partition for TriCO with ENFORCED VIEW DIVERSITY"""
        
        embeddings = self.embedder.encode(words)
        kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(embeddings)
        
        groups = []
        primary_views = []
        used_words = set()
        used_views = []  # Track used views for diversity
        
        # Define target views: we want at least 2 different views, ideally 3
        all_views = ['sem', 'pho', 'orth']
        
        for cluster_id in range(4):
            cluster_indices = [i for i, c in enumerate(clusters) if c == cluster_id]
            cluster_words = [words[i] for i in cluster_indices if words[i] not in used_words]
            
            if len(cluster_words) >= 4:
                # Score each view for this cluster
                view_scores = {}
                view_quartets = {}
                
                for view in all_views:
                    quartet = self._best_quartet(cluster_words, view, sims)
                    if quartet:
                        coh = self._coherence_score(quartet, sims[view], words)
                        view_scores[view] = coh
                        view_quartets[view] = quartet
                    else:
                        view_scores[view] = 0
                        view_quartets[view] = cluster_words[:4]
                
                # Choose view with diversity consideration
                # Priority: underused views get a bonus
                view_counts = {v: used_views.count(v) for v in all_views}
                
                # Adjust scores: penalize overused views, bonus for unused
                adjusted_scores = {}
                for view in all_views:
                    base_score = view_scores[view]
                    # Penalty for each time this view was used
                    penalty = view_counts[view] * 0.15
                    # Bonus if this view hasn't been used yet
                    bonus = 0.10 if view_counts[view] == 0 else 0
                    adjusted_scores[view] = base_score - penalty + bonus
                
                # Pick best adjusted view
                best_view = max(adjusted_scores, key=adjusted_scores.get)
                best_quartet = view_quartets[best_view]
                
                selected_words = best_quartet
            else:
                # Pad with unused words
                selected_words = cluster_words.copy()
                remaining = [w for w in words if w not in used_words and w not in selected_words]
                selected_words.extend(remaining[:4 - len(selected_words)])
                
                # For incomplete clusters, pick least-used view
                view_counts = {v: used_views.count(v) for v in all_views}
                best_view = min(view_counts, key=view_counts.get)
            
            selected_words = selected_words[:4]
            used_words.update(selected_words)
            used_views.append(best_view)
            primary_views.append(best_view)
            
            groups.append(WordGroup(
                words=selected_words,
                category=f"Group {cluster_id + 1}",
                difficulty=DifficultyColor.YELLOW,
                primary_view=best_view
            ))
        
        return groups, words, primary_views
    
    def _best_quartet(self, words: List[str], view: str, sims: Dict[str, np.ndarray]) -> Optional[List[str]]:
        """Select best 4 words by coherence in given view"""
        if len(words) < 4:
            return None
        
        if len(words) == 4:
            return words
        
        M = sims[view]
        pool_index = {w: i for i, w in enumerate(self._current_word_pool)}
        idxs = [pool_index[w] for w in words if w in pool_index]
        
        if len(idxs) < 4:
            return words[:4]
        
        best_score = -1.0
        best_combo = None
        
        max_combos = 100
        combos = list(itertools.combinations(idxs, 4))
        
        if len(combos) > max_combos:
            combos = random.sample(combos, max_combos)
        
        for combo in combos:
            sub = list(combo)
            try:
                M_sub = M[np.ix_(sub, sub)]
                score = (M_sub.sum() - 4) / 12.0
                
                if score > best_score:
                    best_score = score
                    best_combo = sub
            except:
                continue
        
        if best_combo:
            return [self._current_word_pool[i] for i in best_combo]
        
        return words[:4]
    
    def _trico_optimize(self, groups: List[WordGroup], words: List[str], 
                       sims: Dict[str, np.ndarray], primary_views: List[str], 
                       tau: float = 0.5) -> Tuple[List[WordGroup], float]:
        """Run tri-objective optimization"""
        
        best_groups = copy.deepcopy(groups)
        best_score = self._tri_objective(groups, words, sims, primary_views, tau)
        
        for iteration in range(150):
            candidate_groups = copy.deepcopy(best_groups)
            candidate_views = copy.deepcopy(primary_views)
            
            # Random swap between groups
            if len(candidate_groups) >= 2:
                g1_idx, g2_idx = random.sample(range(min(4, len(candidate_groups))), 2)
                if len(candidate_groups[g1_idx].words) > 0 and len(candidate_groups[g2_idx].words) > 0:
                    w1_idx = random.randint(0, len(candidate_groups[g1_idx].words) - 1)
                    w2_idx = random.randint(0, len(candidate_groups[g2_idx].words) - 1)
                    
                    temp = candidate_groups[g1_idx].words[w1_idx]
                    candidate_groups[g1_idx].words[w1_idx] = candidate_groups[g2_idx].words[w2_idx]
                    candidate_groups[g2_idx].words[w2_idx] = temp
            
            # Occasionally try changing views
            if random.random() < 0.25 and len(candidate_views) > 0:
                g_idx = random.randint(0, min(3, len(candidate_views) - 1))
                candidate_views[g_idx] = random.choice(['sem', 'pho', 'orth'])
                if g_idx < len(candidate_groups):
                    candidate_groups[g_idx].primary_view = candidate_views[g_idx]
            
            score = self._tri_objective(candidate_groups, words, sims, candidate_views, tau)
            
            if score > best_score:
                best_score = score
                best_groups = candidate_groups
                primary_views = candidate_views
        
        return best_groups, best_score
    
    def _tri_objective(self, groups: List[WordGroup], words: List[str], 
                      sims: Dict[str, np.ndarray], primary_views: List[str] = None,
                      tau: float = 0.5) -> float:
        """Calculate tri-objective score"""
        
        idx = {w: i for i, w in enumerate(words)}
        
        if primary_views is None:
            primary_views = [g.primary_view or 'sem' for g in groups]
        
        # Intra-group coherence
        coh = 0.0
        for g_idx, g in enumerate(groups):
            if g_idx >= len(primary_views):
                continue
            
            p = primary_views[g_idx]
            I = [idx.get(w, 0) for w in g.words if w in idx]
            if len(I) >= 2:
                M = sims[p][np.ix_(I, I)]
                coh += (M.sum() - len(I)) / (len(I) * (len(I) - 1) + 1e-8)
        coh /= max(len(groups), 1)
        
        # Cross-group confusion in non-primary views
        non_primary = {
            'sem': ['pho', 'orth'],
            'pho': ['sem', 'orth'],
            'orth': ['sem', 'pho']
        }
        
        cross = 0
        count = 0
        
        for a in range(min(4, len(groups))):
            if a >= len(primary_views):
                continue
            for b in range(a+1, min(4, len(groups))):
                if b >= len(primary_views):
                    continue
                for view in non_primary.get(primary_views[a], []):
                    if view in non_primary.get(primary_views[b], []):
                        for wa in groups[a].words:
                            if wa not in idx:
                                continue
                            for wb in groups[b].words:
                                if wb not in idx:
                                    continue
                                cross += sims[view][idx[wa], idx[wb]]
                                count += 1
        
        cross = cross / max(count, 1)
        
        # Difficulty spread
        intrag = []
        for g_idx, g in enumerate(groups):
            if g_idx >= len(primary_views):
                continue
            I = [idx.get(w, 0) for w in g.words if w in idx]
            if len(I) >= 2:
                M = sims[primary_views[g_idx]][np.ix_(I, I)]
                intrag.append((M.sum() - len(I)) / (len(I) * (len(I) - 1) + 1e-8))
            else:
                intrag.append(0)
        
        spread = max(intrag) - min(intrag) if intrag else 0
        
        return 1.0 * coh + 0.4 * cross + 0.2 * spread
    
    def _best_view_and_coherence(self, groups: List[WordGroup], word_pool: List[str], 
                                 sims: Dict[str, np.ndarray]) -> List[WordGroup]:
        """Assign best primary view to each group WITH VIEW DIVERSITY"""
        
        all_views = ['sem', 'pho', 'orth']
        
        # First pass: compute scores for all groups and all views
        group_view_scores = []
        for g in groups:
            view_scores = {}
            for v in all_views:
                coh = self._coherence_score(g.words, sims[v], word_pool)
                view_scores[v] = coh
            group_view_scores.append(view_scores)
        
        # Second pass: assign views ensuring diversity
        # Use a greedy assignment that balances quality and diversity
        assigned_views = [None] * len(groups)
        view_counts = {v: 0 for v in all_views}
        
        # Sort groups by their "best view advantage" - how much better their best view is
        group_indices = list(range(len(groups)))
        
        def view_advantage(idx):
            scores = group_view_scores[idx]
            sorted_scores = sorted(scores.values(), reverse=True)
            if len(sorted_scores) >= 2:
                return sorted_scores[0] - sorted_scores[1]  # Advantage of best over second-best
            return 0
        
        # Process groups with strongest preference first
        group_indices.sort(key=view_advantage, reverse=True)
        
        for idx in group_indices:
            scores = group_view_scores[idx]
            
            # Adjust scores based on current view usage to encourage diversity
            adjusted_scores = {}
            for v in all_views:
                base = scores[v]
                # Penalty for overused views: -0.1 for each use beyond 1
                penalty = max(0, (view_counts[v] - 1)) * 0.10
                # Bonus for unused views
                bonus = 0.08 if view_counts[v] == 0 else 0
                adjusted_scores[v] = base - penalty + bonus
            
            # Pick best adjusted view
            best_view = max(adjusted_scores, key=adjusted_scores.get)
            assigned_views[idx] = best_view
            view_counts[best_view] += 1
        
        # Apply assignments
        for idx, g in enumerate(groups):
            g.primary_view = assigned_views[idx]
            g.similarity_score = group_view_scores[idx][assigned_views[idx]]
        
        # Log view distribution for debugging
        final_counts = {v: sum(1 for g in groups if g.primary_view == v) for v in all_views}
        
        return groups
    
    def _dedupe_and_repair_groups(self, groups: List[WordGroup], pool: List[str], 
                                  sims: Dict[str, np.ndarray], min_coh: float = 0.20) -> List[WordGroup]:
        """Remove duplicates and repair groups"""
        
        used = set()
        pool_remaining = set(pool)
        
        for g in groups:
            uniq = []
            for w in g.words:
                if w not in used:
                    uniq.append(w)
                    used.add(w)
                    pool_remaining.discard(w)
            
            # Top up if needed
            if len(uniq) < 4:
                candidates = []
                for w in pool_remaining:
                    if w not in used:
                        test_words = uniq + [w]
                        if len(test_words) <= 4:
                            coh = self._coherence_score(test_words, sims[g.primary_view or 'sem'], pool)
                            candidates.append((coh, w))
                
                candidates.sort(reverse=True)
                for _, w in candidates:
                    if len(uniq) >= 4:
                        break
                    uniq.append(w)
                    used.add(w)
                    pool_remaining.discard(w)
            
            g.words = uniq[:4]
        
        return groups
    
    def _repair_low_coherence_groups(self, groups: List[WordGroup], pool: List[str], 
                                     sims: Dict[str, np.ndarray], min_coh: float) -> List[WordGroup]:
        """Attempt to repair groups with low coherence"""
        
        used_words = set()
        for g in groups:
            used_words.update(g.words)
        
        available = [w for w in pool if w not in used_words]
        
        for g in groups:
            current_coh = self._coherence_score(g.words, sims[g.primary_view], pool)
            
            if current_coh < min_coh:
                # Try swapping each word
                for i in range(4):
                    best_replacement = None
                    best_new_coh = current_coh
                    
                    for candidate in available:
                        test_words = g.words.copy()
                        test_words[i] = candidate
                        new_coh = self._coherence_score(test_words, sims[g.primary_view], pool)
                        
                        if new_coh > best_new_coh:
                            best_new_coh = new_coh
                            best_replacement = (i, candidate, g.words[i])
                    
                    if best_replacement:
                        idx, new_word, old_word = best_replacement
                        g.words[idx] = new_word
                        available.remove(new_word)
                        available.append(old_word)
                        current_coh = best_new_coh
                        
                        if current_coh >= min_coh:
                            break
        
        return groups
    
    def _fix_duplicate_words(self, groups: List[WordGroup], pool: List[str]) -> List[WordGroup]:
        """Fix any duplicate words across groups"""
        
        seen = set()
        available = set(pool)
        
        for g in groups:
            available -= set(g.words)
        
        for g in groups:
            new_words = []
            for w in g.words:
                if w in seen:
                    # Find replacement
                    if available:
                        replacement = available.pop()
                        new_words.append(replacement)
                        seen.add(replacement)
                    else:
                        # Generate unique word
                        counter = 1
                        while f"WORD{counter}" in seen:
                            counter += 1
                        new_word = f"WORD{counter}"
                        new_words.append(new_word)
                        seen.add(new_word)
                else:
                    new_words.append(w)
                    seen.add(w)
            g.words = new_words
        
        return groups
    
    def _coherence_score(self, words: List[str], M_or_sims: Any, word_pool: Optional[List[str]] = None) -> float:
        """Calculate coherence score for a group"""
        
        if isinstance(M_or_sims, dict):
            M = M_or_sims.get('sem', list(M_or_sims.values())[0])
        else:
            M = M_or_sims
        
        if M.shape[0] == len(words) == 4:
            n = 4
            return (M.sum() - n) / (n * (n - 1))
        
        if word_pool is not None:
            try:
                indices = [word_pool.index(w) for w in words if w in word_pool]
                if len(indices) >= 2:
                    sub_M = M[np.ix_(indices, indices)]
                    n = len(indices)
                    return (sub_M.sum() - n) / (n * (n - 1))
            except:
                pass
        
        return 0.3  # Default moderate coherence
    
    def _get_trico_category(self, group: WordGroup, primary_view: str) -> str:
        """Generate category name for TriCO group - validates that category fits words"""
        
        words = group.words
        
        # First, detect ACTUAL patterns in the words
        
        # Check orthographic patterns (visual)
        orth_pattern = self._explain_orth_pattern(words)
        if orth_pattern and primary_view == 'orth':
            return orth_pattern
        
        # Check phonetic patterns (sound)
        if primary_view == 'pho':
            # Check for rhyming (same ending)
            endings_2 = [w[-2:].lower() if len(w) >= 2 else w.lower() for w in words]
            endings_3 = [w[-3:].lower() if len(w) >= 3 else w.lower() for w in words]
            
            if len(set(endings_2)) == 1:
                return f"End with '-{endings_2[0].upper()}'"
            if len(set(endings_3)) == 1:
                return f"End with '-{endings_3[0].upper()}'"
            
            # Check for alliteration (same start)
            starts = [w[0].upper() for w in words]
            if len(set(starts)) == 1:
                return f"Start with '{starts[0]}'"
            
            # Check for same syllable count (approximate)
            def count_vowels(w):
                return sum(1 for c in w.lower() if c in 'aeiou')
            vowel_counts = [count_vowels(w) for w in words]
            if len(set(vowel_counts)) == 1:
                return f"Words with {vowel_counts[0]} vowel sound(s)"
            
            # Generic phonetic fallback
            return "Sound Pattern Group"
        
        # For semantic view or no clear pattern, try LLM but validate
        if primary_view == 'sem':
            # Try multiple prompts to find a good category
            prompts_to_try = [
                f"""These 4 words need a SPECIFIC category name: {', '.join(words)}

Examples of GOOD categories: "Types of Fish", "Shades of Red", "Kitchen Utensils", "Card Games"
Examples of BAD categories: "Related Words", "Things", "Concepts"

What SPECIFIC category do ALL these words belong to?
Output ONLY the category name (2-5 words):""",

                f"""What do {', '.join(words)} have in common?
Be SPECIFIC - what type/kind of thing are they ALL?
Output ONLY the category (2-5 words):""",

                f"""Fill in: "{words[0]}, {words[1]}, {words[2]}, and {words[3]} are all ___"
Output ONLY what goes in the blank (2-5 words):"""
            ]
            
            for prompt in prompts_to_try:
                response = self._call_llm(prompt, temperature=0.3)
                category = response.strip().split('\n')[0].strip('"\'[](){}')
                
                # Clean up common prefixes
                for prefix in ['types of ', 'kinds of ', 'all ', 'they are all ']:
                    if category.lower().startswith(prefix):
                        # Keep as is for "types of" style
                        break
                
                # Reject vague categories
                vague_patterns = ['related', 'things', 'stuff', 'concepts', 'words', 
                                 'miscellaneous', 'various', 'items', 'group']
                is_vague = any(vp in category.lower() for vp in vague_patterns)
                
                if category and len(category) >= 3 and not is_vague:
                    # Validate the category
                    validation_prompt = f"""Does "{category}" accurately describe ALL of: {', '.join(words)}?
Answer ONLY "yes" or "no":"""
                    
                    validation = self._call_llm(validation_prompt, temperature=0.1).strip().lower()
                    
                    if 'yes' in validation:
                        if len(category) > 35:
                            category = category[:35].rsplit(' ', 1)[0]
                        return category
            
            # All prompts failed - try one more specific approach
            final_prompt = f"""I need a category for: {', '.join(words)}

These words MUST have something in common. What is it?
Think about: Are they all foods? Colors? Actions? Places? Objects?

Give me a 2-4 word category name:"""
            
            response = self._call_llm(final_prompt, temperature=0.5)
            category = response.strip().split('\n')[0].strip('"\'[](){}')
            
            if category and len(category) >= 3:
                return category
            
            # Absolute fallback - be honest
            return "Conceptually Related"
        
        # Orthographic view fallback
        if primary_view == 'orth':
            lengths = [len(w) for w in words]
            if len(set(lengths)) == 1:
                return f"{lengths[0]}-letter words"
            return "Letter Pattern Group"
        
        return "Word Group"
    
    def _all_rhyme(self, words: List[str]) -> bool:
        """Check if words rhyme - improved detection"""
        if len(words) < 2:
            return False
        
        # Check multiple ending patterns (phonetic rhyming)
        # Try 2-letter, 3-letter endings
        for suffix_len in [2, 3]:
            endings = []
            for w in words:
                if len(w) >= suffix_len:
                    endings.append(w[-suffix_len:].lower())
                else:
                    endings.append(w.lower())
            
            if len(set(endings)) == 1:
                return True
        
        # Check vowel patterns (approximate rhyme)
        def get_vowel_pattern(word):
            vowels = 'aeiou'
            return ''.join(c for c in word.lower() if c in vowels)[-2:]
        
        vowel_patterns = [get_vowel_pattern(w) for w in words]
        if len(set(vowel_patterns)) == 1 and vowel_patterns[0]:
            return True
        
        return False
    
    def _all_start_same(self, words: List[str]) -> bool:
        """Check if words start with same letter"""
        if len(words) < 2:
            return False
        starts = [w[0].upper() for w in words]
        return len(set(starts)) == 1
    
    def _has_recognizable_phonetic_pattern(self, words: List[str]) -> bool:
        """Check if words have a human-recognizable phonetic pattern"""
        if len(words) < 4:
            return False
        
        # Check for rhyming (same 2 or 3 letter ending)
        endings_2 = [w[-2:].lower() if len(w) >= 2 else w.lower() for w in words]
        if len(set(endings_2)) == 1:
            return True
        
        endings_3 = [w[-3:].lower() if len(w) >= 3 else w.lower() for w in words]
        if len(set(endings_3)) == 1:
            return True
        
        # Check for alliteration (same starting letter)
        starts = [w[0].upper() for w in words]
        if len(set(starts)) == 1:
            return True
        
        # Check for same 2-letter start (ST-, BR-, etc.)
        starts_2 = [w[:2].lower() if len(w) >= 2 else w.lower() for w in words]
        if len(set(starts_2)) == 1:
            return True
        
        # Check for same syllable count (approximate via vowel groups)
        def count_syllables(word):
            word = word.lower()
            count = 0
            prev_vowel = False
            for char in word:
                is_vowel = char in 'aeiou'
                if is_vowel and not prev_vowel:
                    count += 1
                prev_vowel = is_vowel
            return max(count, 1)
        
        syllables = [count_syllables(w) for w in words]
        if len(set(syllables)) == 1:
            return True
        
        # Check for same vowel pattern in last syllable
        def last_vowel_pattern(word):
            vowels = [c for c in word.lower() if c in 'aeiou']
            return ''.join(vowels[-2:]) if len(vowels) >= 2 else ''.join(vowels)
        
        vowel_patterns = [last_vowel_pattern(w) for w in words]
        if len(set(vowel_patterns)) == 1 and vowel_patterns[0]:
            return True
        
        return False
    
    def _explain_orth_pattern(self, words: List[str]) -> Optional[str]:
        """Explain orthographic pattern"""
        lows = [w.lower() for w in words]
        
        # Check common prefix
        pref = os.path.commonprefix(lows)
        if len(pref) >= 2:
            return f"Start with '{pref}'"
        
        # Check common suffix
        revs = [s[::-1] for s in lows]
        suf = os.path.commonprefix(revs)[::-1]
        if len(suf) >= 2:
            return f"End with '{suf}'"
        
        # Check same length
        lengths = [len(w) for w in words]
        if len(set(lengths)) == 1:
            return f"{lengths[0]}-letter words"
        
        # Check double letters
        if all(any(w[i] == w[i+1] for i in range(len(w)-1)) for w in lows if len(w) > 1):
            return "Words with double letters"
        
        return None
    
    def _assign_difficulties_trico(self, groups: List[WordGroup], sims: Dict[str, np.ndarray]) -> List[WordGroup]:
        """Assign difficulties based on TriCO coherence"""
        
        words = []
        for g in groups:
            words.extend(g.words)
        
        for g in groups:
            view = g.primary_view or 'sem'
            indices = []
            for w in g.words:
                if w in words:
                    indices.append(words.index(w))
            
            if len(indices) == 4:
                sub_matrix = sims[view][np.ix_(indices, indices)]
                g.similarity_score = (sub_matrix.sum() - 4) / 12
            else:
                g.similarity_score = 0.5
        
        groups.sort(key=lambda g: g.similarity_score, reverse=True)
        
        colors = [
            DifficultyColor.YELLOW,
            DifficultyColor.GREEN,
            DifficultyColor.BLUE,
            DifficultyColor.PURPLE
        ]
        
        for group, col in zip(groups, colors):
            group.difficulty = col
        
        return groups
    
    def _calculate_trico_deception(self, groups: List[WordGroup], sims: Dict[str, np.ndarray], 
                                   words: List[str]) -> float:
        """Calculate deception score for TriCO puzzle"""
        
        word_to_group = {}
        for g_idx, group in enumerate(groups):
            for word in group.words:
                word_to_group[word] = g_idx
        
        deception_score = 0.0
        deception_count = 0
        
        for view in ['sem', 'pho', 'orth']:
            for i, word in enumerate(words):
                if word not in word_to_group:
                    continue
                word_group = word_to_group[word]
                
                other_sims = []
                for j, other_word in enumerate(words):
                    if other_word not in word_to_group:
                        continue
                    if word_to_group[other_word] != word_group:
                        if i < len(sims[view]) and j < len(sims[view][0]):
                            other_sims.append(sims[view][i, j])
                
                if other_sims:
                    top_2_avg = np.mean(sorted(other_sims, reverse=True)[:2])
                    deception_score += top_2_avg
                    deception_count += 1
        
        return deception_score / max(deception_count, 1)
    
    def _calculate_near_misses(self, groups: List[WordGroup]) -> int:
        """Calculate number of near-miss quartets"""
        
        near_misses = 0
        threshold = 0.25
        
        all_words = []
        word_to_group = {}
        
        for group_idx, group in enumerate(groups):
            for word in group.words:
                all_words.append(word)
                word_to_group[word] = group_idx
        
        if len(all_words) < 16:
            return 0
        
        embeddings = self.embedder.encode(all_words)
        
        # Check 3+1 combinations
        for target_group in range(4):
            target_words = [w for w in all_words if word_to_group[w] == target_group]
            other_words = [w for w in all_words if word_to_group[w] != target_group]
            
            for trio in itertools.combinations(target_words, 3):
                for outsider in other_words:
                    quartet = list(trio) + [outsider]
                    indices = [all_words.index(w) for w in quartet]
                    
                    quartet_emb = embeddings[indices]
                    sim_matrix = cosine_similarity(quartet_emb)
                    coherence = (sim_matrix.sum() - 4) / 12
                    
                    if coherence >= threshold:
                        near_misses += 1
        
        return near_misses
    
    # ================================================================
    # HELPER METHODS
    # ================================================================
    
    def _validate_words_match_category(self, groups: List[WordGroup]) -> List[WordGroup]:
        """
        Validate that each word actually belongs to its category.
        Replace words that don't fit with better alternatives.
        """
        
        for group in groups:
            category = group.category
            words = group.words
            
            # NEVER validate phonetic or orthographic groups - their patterns are structural
            if group.primary_view in ['pho', 'orth']:
                continue
            
            # Skip generic/pattern-based categories that don't need semantic validation
            skip_patterns = ['letter', 'sound', 'pattern', 'start with', 'end with', 
                           'vowel', 'conceptually', 'related', 'rhyme']
            if any(p in category.lower() for p in skip_patterns):
                continue
            
            # Validate each word belongs to the category
            validation_prompt = f"""For the category "{category}", check if each word belongs:

Words: {', '.join(words)}

For each word, answer ONLY "yes" or "no" on separate lines:
{chr(10).join(f'{w}: ' for w in words)}"""
            
            response = self._call_llm(validation_prompt, temperature=0.1)
            
            # Parse validation results
            invalid_words = []
            lines = response.strip().split('\n')
            
            for i, word in enumerate(words):
                # Find the line for this word
                word_valid = True
                for line in lines:
                    if word.lower() in line.lower():
                        if 'no' in line.lower().split(':')[-1].strip().lower():
                            word_valid = False
                            break
                
                if not word_valid:
                    invalid_words.append(word)
            
            # Replace invalid words
            if invalid_words:
                used_words = set(w for g in groups for w in g.words)
                
                for invalid_word in invalid_words:
                    # Ask LLM for a replacement
                    replacement_prompt = f"""The word "{invalid_word}" does NOT fit the category "{category}".

Suggest ONE single word that DOES fit the category "{category}".
The word must be different from: {', '.join(used_words)}

Output ONLY the replacement word, nothing else:"""
                    
                    replacement = self._call_llm(replacement_prompt, temperature=0.5)
                    replacement = clean_word(replacement.strip().split()[0] if replacement.strip() else "")
                    
                    if replacement and replacement not in used_words and is_valid_word(replacement):
                        # Verify replacement is valid
                        verify_prompt = f'Does "{replacement}" fit the category "{category}"? Answer only yes or no:'
                        verify = self._call_llm(verify_prompt, temperature=0.1).strip().lower()
                        
                        if 'yes' in verify:
                            # Replace the word
                            idx = group.words.index(invalid_word)
                            group.words[idx] = replacement
                            used_words.add(replacement)
        
        return groups
    
    def _validate_and_fix_group(self, group: WordGroup, used_words: set) -> WordGroup:
        """
        Validate a single group and fix any words that don't match the category.
        Returns the fixed group.
        """
        category = group.category
        words = list(group.words)
        
        # Skip pattern-based categories
        skip_patterns = ['letter', 'sound', 'pattern', 'start with', 'end with', 
                        'vowel', 'conceptually', 'related', 'group']
        if any(p in category.lower() for p in skip_patterns):
            return group
        
        # Batch validation
        validation_prompt = f"""Category: "{category}"

For each word below, does it belong to this category? Answer "yes" or "no" for each:
{chr(10).join(f'- {w}:' for w in words)}"""
        
        response = self._call_llm(validation_prompt, temperature=0.1)
        
        # Parse and fix
        new_words = []
        for word in words:
            is_valid = True
            for line in response.split('\n'):
                if word.lower() in line.lower():
                    answer = line.split(':')[-1].strip().lower() if ':' in line else line.lower()
                    if 'no' in answer:
                        is_valid = False
                    break
            
            if is_valid:
                new_words.append(word)
            else:
                # Find replacement
                replacement = self._find_category_word(category, used_words | set(new_words))
                if replacement:
                    new_words.append(replacement)
                else:
                    new_words.append(word)  # Keep original if no replacement found
        
        group.words = new_words[:4]
        return group
    
    def _find_category_word(self, category: str, exclude: set) -> Optional[str]:
        """Find a word that fits the given category, excluding specified words."""
        
        prompt = f"""Give me ONE word that fits the category "{category}".
The word must NOT be any of: {', '.join(list(exclude)[:20])}

Output ONLY the single word:"""
        
        response = self._call_llm(prompt, temperature=0.7)
        word = clean_word(response.strip().split()[0] if response.strip() else "")
        
        if word and word not in exclude and is_valid_word(word):
            # Verify it fits
            verify = self._call_llm(f'Does "{word}" fit "{category}"? Yes or no:', temperature=0.1)
            if 'yes' in verify.lower():
                return word
        
        return None
    
    def _ensure_valid_groups(self, groups: List[WordGroup]) -> List[WordGroup]:
        """Ensure exactly 4 valid groups with unique, valid words"""
        
        used_words = set()
        valid_groups = []
        
        for group in groups:
            # Validate and clean each word, removing duplicates within group
            valid_words = []
            seen_in_group = set()
            
            for word in group.words:
                cleaned = clean_word(word)
                # Skip if empty, invalid, already used globally, or duplicate within group
                if not cleaned:
                    continue
                if not is_valid_word(cleaned):
                    continue
                if cleaned in used_words:
                    continue
                if cleaned in seen_in_group:
                    continue
                
                valid_words.append(cleaned)
                seen_in_group.add(cleaned)
                used_words.add(cleaned)
            
            if len(valid_words) == 4:
                group.words = valid_words
                valid_groups.append(group)
            elif len(valid_words) > 0:
                # Try to fill in missing words
                attempts = 0
                while len(valid_words) < 4 and attempts < 10:
                    attempts += 1
                    fallback = generate_fallback_group(used_words, self.embedder, self.knowledge_base)
                    for w in fallback.words:
                        cleaned_fb = clean_word(w)
                        if cleaned_fb and cleaned_fb not in used_words:
                            valid_words.append(cleaned_fb)
                            used_words.add(cleaned_fb)
                        if len(valid_words) >= 4:
                            break
                
                if len(valid_words) >= 4:
                    group.words = valid_words[:4]
                    valid_groups.append(group)
        
        # Fill in missing groups
        attempts = 0
        while len(valid_groups) < 4 and attempts < 10:
            attempts += 1
            fallback = generate_fallback_group(used_words, self.embedder, self.knowledge_base)
            # Ensure fallback doesn't have duplicates
            fallback_clean = []
            for w in fallback.words:
                cleaned = clean_word(w)
                if cleaned and cleaned not in used_words:
                    fallback_clean.append(cleaned)
                    used_words.add(cleaned)
            
            if len(fallback_clean) == 4:
                fallback.words = fallback_clean
                valid_groups.append(fallback)
            elif len(fallback_clean) > 0:
                # Try to complete this fallback group
                while len(fallback_clean) < 4:
                    fb2 = generate_fallback_group(used_words, self.embedder, self.knowledge_base)
                    for w in fb2.words:
                        cleaned = clean_word(w)
                        if cleaned and cleaned not in used_words:
                            fallback_clean.append(cleaned)
                            used_words.add(cleaned)
                        if len(fallback_clean) >= 4:
                            break
                    if len(fallback_clean) < 4:
                        break  # Can't complete, try again
                
                if len(fallback_clean) >= 4:
                    fallback.words = fallback_clean[:4]
                    valid_groups.append(fallback)
        
        # Final validation: ensure no duplicates across all groups
        all_words = []
        for g in valid_groups[:4]:
            all_words.extend(g.words)
        
        if len(all_words) != len(set(all_words)):
            # We have duplicates - fix them
            seen = set()
            for group in valid_groups[:4]:
                new_words = []
                for word in group.words:
                    if word not in seen:
                        new_words.append(word)
                        seen.add(word)
                    else:
                        # Replace duplicate with new word
                        fb = generate_fallback_group(seen, self.embedder, self.knowledge_base)
                        for fw in fb.words:
                            if fw not in seen:
                                new_words.append(fw)
                                seen.add(fw)
                                break
                group.words = new_words[:4]
        
        return valid_groups[:4]
    
    def _assign_difficulties_targeted(self, groups: List[WordGroup]) -> List[WordGroup]:
        """Assign difficulties based on paper's target similarity means"""
        
        target_means = {
            DifficultyColor.YELLOW: 0.4017,
            DifficultyColor.GREEN: 0.3536,
            DifficultyColor.BLUE: 0.2905,
            DifficultyColor.PURPLE: 0.2664
        }
        
        for group in groups:
            embeddings = self.embedder.encode(group.words)
            similarities = cosine_similarity(embeddings)
            n = len(similarities)
            group.similarity_score = (similarities.sum() - n) / (n * (n - 1))
        
        best_assignment = None
        best_distance = float('inf')
        
        colors = [DifficultyColor.YELLOW, DifficultyColor.GREEN, 
                 DifficultyColor.BLUE, DifficultyColor.PURPLE]
        
        for perm in itertools.permutations(range(4)):
            total_distance = 0
            for group_idx, color_idx in enumerate(perm):
                if group_idx < len(groups):
                    color = colors[color_idx]
                    distance = abs(groups[group_idx].similarity_score - target_means[color])
                    total_distance += distance
            
            if total_distance < best_distance:
                best_distance = total_distance
                best_assignment = perm
        
        if best_assignment:
            for group_idx, color_idx in enumerate(best_assignment):
                if group_idx < len(groups):
                    groups[group_idx].difficulty = colors[color_idx]
        
        return groups
    
    def _generate_diverse_word_pool(self, theme: Optional[str], size: int = 60) -> List[str]:
        """Generate diverse word pool for puzzle creation - includes words for ALL VIEWS"""
        
        word_pool = set()
        
        # Add from semantic networks
        if theme:
            theme_lower = theme.lower()
            for network_name, words in self.knowledge_base.semantic_networks.items():
                if theme_lower in network_name or network_name in theme_lower:
                    for w in words[:10]:
                        if is_valid_word(w):
                            word_pool.add(w)
        
        # Add random words from all networks
        for network_words in self.knowledge_base.semantic_networks.values():
            sample_size = min(5, len(network_words))
            for w in random.sample(network_words, sample_size):
                if is_valid_word(w):
                    word_pool.add(w)
        
        # Generate semantic words via LLM
        if len(word_pool) < size // 2:
            prompt = f"""Generate {size // 3} diverse single English words for a word puzzle.
Include variety: nouns, verbs, adjectives.
{"Theme: " + theme if theme else ""}

Output ONLY single words, comma-separated, nothing else:"""
            
            response = self._call_llm(prompt)
            new_words = extract_valid_words(response, word_pool)
            word_pool.update(new_words)
        
        # Generate PHONETIC-friendly words (rhyming patterns)
        phonetic_prompt = """Generate 20 English words that have good RHYMING potential.
Include sets like:
- Words ending in -ATE (PLATE, GATE, LATE, RATE)
- Words ending in -ING (RING, KING, SING, WING)
- Words ending in -OWN (CROWN, BROWN, TOWN, DOWN)
- Words ending in -EAK (PEAK, WEAK, LEAK, SPEAK)

Output ONLY single words, comma-separated:"""
        
        response = self._call_llm(phonetic_prompt, temperature=0.7)
        phonetic_words = extract_valid_words(response, word_pool)
        word_pool.update(phonetic_words)
        
        # Generate ORTHOGRAPHIC-friendly words (visual patterns)
        ortho_prompt = """Generate 20 English words that have interesting SPELLING patterns.
Include:
- Words starting with same 2 letters (STAR, STOP, STONE, STORM)
- Words ending with same 2 letters (THINK, DRINK, SHRINK, LINK)
- Words with double letters (APPLE, COFFEE, BUTTER, HAMMER)
- Words of same length (4-letter: BOAT, COAT, GOAT, MOAT)

Output ONLY single words, comma-separated:"""
        
        response = self._call_llm(ortho_prompt, temperature=0.7)
        ortho_words = extract_valid_words(response, word_pool)
        word_pool.update(ortho_words)
        
        # Curated words specifically good for non-semantic views
        pattern_words = [
            # Rhyming sets
            "PLATE", "GATE", "LATE", "RATE", "FATE", "DATE",
            "RING", "KING", "SING", "WING", "THING", "BRING",
            "CROWN", "BROWN", "TOWN", "DOWN", "GOWN", "FROWN",
            "PEAK", "WEAK", "LEAK", "SPEAK", "SNEAK", "CREEK",
            "LIGHT", "NIGHT", "SIGHT", "RIGHT", "MIGHT", "FIGHT",
            # Same prefix
            "STAR", "STOP", "STONE", "STORM", "STORY", "STORE",
            "BRAIN", "BREAK", "BREAD", "BRAVE", "BRAND", "BRASS",
            # Same suffix
            "THINK", "DRINK", "SHRINK", "LINK", "SINK", "PINK",
            "HAMMER", "SUMMER", "DRUMMER", "SWIMMER",
            # Double letters
            "APPLE", "COFFEE", "BUTTER", "LETTER", "BITTER", "BETTER",
            "BALLOON", "BASSOON", "RACCOON", "CARTOON",
            # Same length (4 letters)
            "BOAT", "COAT", "GOAT", "MOAT", "TOAD", "ROAD",
            "BALL", "CALL", "FALL", "HALL", "MALL", "TALL", "WALL",
        ]
        
        for w in pattern_words:
            if w not in word_pool and is_valid_word(w):
                word_pool.add(w)
        
        # Extensive fallback word list
        if len(word_pool) < size:
            fallback_words = [
                "APPLE", "CAR", "HOUSE", "TREE", "BOOK", "PHONE", "CHAIR", "TABLE",
                "MOUNTAIN", "RIVER", "OCEAN", "FOREST", "DESERT", "CITY", "ROAD", "BRIDGE",
                "HAPPY", "SAD", "FAST", "SLOW", "BIG", "SMALL", "HOT", "COLD",
                "RUN", "JUMP", "SWIM", "WALK", "DANCE", "SING", "PLAY", "WRITE",
                "DOCTOR", "TEACHER", "ARTIST", "WRITER", "ENGINEER", "CHEF", "PILOT", "NURSE",
                "RED", "BLUE", "GREEN", "YELLOW", "PURPLE", "ORANGE", "BLACK", "WHITE",
                "SPRING", "SUMMER", "AUTUMN", "WINTER", "MONDAY", "FRIDAY", "MARCH", "JULY",
                "GUITAR", "PIANO", "DRUMS", "VIOLIN", "FLUTE", "TRUMPET", "BASS", "HARP",
                "TIGER", "LION", "BEAR", "WOLF", "EAGLE", "SHARK", "WHALE", "SNAKE",
                "PIZZA", "BURGER", "PASTA", "SUSHI", "CURRY", "STEAK", "SALAD", "SOUP",
                "GOLD", "SILVER", "BRONZE", "COPPER", "IRON", "STEEL", "GLASS", "STONE",
                "KING", "QUEEN", "PRINCE", "KNIGHT", "CASTLE", "THRONE", "CROWN", "SWORD",
                "BEACH", "ISLAND", "VALLEY", "CANYON", "MEADOW", "CLIFF", "CAVE", "LAKE",
                "CLOCK", "WATCH", "MIRROR", "WINDOW", "DOOR", "LAMP", "SHELF", "FRAME",
            ]
            remaining = [w for w in fallback_words if w not in word_pool and is_valid_word(w)]
            word_pool.update(remaining[:size - len(word_pool)])
        
        result = list(word_pool)[:size]
        random.shuffle(result)
        return result
    
    def _score_word_group(self, words: List[str]) -> float:
        """Score a word group quality"""
        
        if len(words) != 4:
            return 0.0
        
        embeddings = self.embedder.encode(words)
        similarities = cosine_similarity(embeddings)
        
        n = len(similarities)
        avg_similarity = (similarities.sum() - n) / (n * (n - 1))
        
        return avg_similarity
    
    def _call_llm(self, prompt: str, temperature: float = 0.8) -> str:
        """Unified LLM calling interface"""
        
        if self.backend == ModelBackend.OPENAI and self.client:
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are an expert puzzle creator for the NYT Connections game."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=temperature,
                    max_tokens=500,
                    timeout=60
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"OpenAI API call failed: {e}")
                
        elif self.backend == ModelBackend.OPEN_SOURCE and hasattr(self, 'llm') and self.llm:
            try:
                response = self.llm.generate(prompt, temperature=temperature)
                return response
            except Exception as e:
                print(f"Open source model failed: {e}")
        
        return self._mock_response(prompt)
    
    def _mock_response(self, prompt: str) -> str:
        """Mock responses for testing - returns clean, valid puzzles"""
        
        mock_puzzles = [
            """YELLOW: Citrus Fruits - LEMON, LIME, ORANGE, GRAPEFRUIT
GREEN: Card Games - POKER, BRIDGE, HEARTS, SOLITAIRE
BLUE: Ocean Features - WAVE, TIDE, CURRENT, REEF
PURPLE: Things with Keys - PIANO, KEYBOARD, LOCK, MAP""",
            
            """YELLOW: Breakfast Foods - PANCAKE, WAFFLE, CEREAL, TOAST
GREEN: String Instruments - VIOLIN, CELLO, GUITAR, BASS
BLUE: Types of Dance - WALTZ, TANGO, SALSA, BALLET
PURPLE: Shades of Blue - NAVY, ROYAL, SKY, COBALT""",
            
            """YELLOW: Pizza Toppings - PEPPERONI, MUSHROOM, OLIVE, SAUSAGE
GREEN: Programming Languages - PYTHON, JAVA, RUST, SWIFT
BLUE: Weather Events - THUNDER, LIGHTNING, TORNADO, BLIZZARD
PURPLE: Board Games - CHESS, CHECKERS, MONOPOLY, SCRABBLE""",
            
            """YELLOW: Planets - MARS, VENUS, JUPITER, SATURN
GREEN: Kitchen Appliances - BLENDER, TOASTER, MICROWAVE, OVEN
BLUE: Types of Trees - OAK, MAPLE, PINE, BIRCH
PURPLE: Famous Scientists - EINSTEIN, NEWTON, DARWIN, CURIE""",
            
            """YELLOW: Fruits - APPLE, BANANA, CHERRY, MANGO
GREEN: Colors - CRIMSON, SCARLET, MAROON, BURGUNDY
BLUE: Sports Equipment - RACKET, HELMET, GLOVE, CLEATS
PURPLE: Musical Genres - JAZZ, BLUES, ROCK, COUNTRY""",
        ]
        
        # For word generation prompts, return simple word lists
        if 'words' in prompt.lower() and 'generate' in prompt.lower():
            word_lists = [
                "APPLE, BANANA, ORANGE, GRAPE, MANGO, PEACH, PLUM, CHERRY",
                "PIANO, GUITAR, DRUMS, VIOLIN, FLUTE, TRUMPET, CELLO, BASS",
                "RED, BLUE, GREEN, YELLOW, PURPLE, ORANGE, PINK, BROWN",
                "DOG, CAT, BIRD, FISH, HORSE, RABBIT, HAMSTER, TURTLE",
            ]
            return word_lists[self._mock_index % len(word_lists)]
        
        # For category prompts, return simple categories
        if 'category' in prompt.lower():
            categories = [
                "Category: Types of Fruit\nWords: APPLE, BANANA, ORANGE, GRAPE",
                "Category: Musical Instruments\nWords: PIANO, GUITAR, DRUMS, VIOLIN",
                "Category: Colors\nWords: RED, BLUE, GREEN, YELLOW",
                "Category: Pets\nWords: DOG, CAT, BIRD, FISH",
            ]
            return categories[self._mock_index % len(categories)]
        
        response = mock_puzzles[self._mock_index % len(mock_puzzles)]
        self._mock_index += 1
        return response
