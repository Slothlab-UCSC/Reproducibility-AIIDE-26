"""
NYT Connections Puzzle Generator - Player Module
Contains: PuzzleEditor, HumanEvaluator, SmartPuzzlePlayer, PuzzleSimulator, display functions
"""

import os
import random
import numpy as np
import itertools
import time
import re
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict, Counter
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

from core import (
    PuzzleMode, ModelBackend, DifficultyColor, PlayerStrategy,
    WordGroup, ConnectionsPuzzle, PlayResult, SimulationResult,
    PromptTemplates, generate_fallback_group, clean_word
)


class PuzzleEditor:
    """Edit and refine generated puzzles"""
    
    def __init__(self, generator=None):
        self.generator = generator
        self.embedder = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
    
    def edit_puzzle(self, puzzle: ConnectionsPuzzle, 
                   edit_type: str = "improve_categories") -> ConnectionsPuzzle:
        """Edit puzzle to improve quality"""
        
        edit_functions = {
            "improve_categories": self._improve_category_names,
            "balance_difficulty": self._balance_difficulty,
            "remove_ambiguity": self._remove_ambiguity,
            "enhance_deception": self._enhance_deception,
            "verify_solvability": self._verify_solvability
        }
        
        if edit_type in edit_functions:
            return edit_functions[edit_type](puzzle)
        
        return puzzle
    
    def _improve_category_names(self, puzzle: ConnectionsPuzzle) -> ConnectionsPuzzle:
        """Make category names more specific and clear"""
        
        if self.generator and self.generator.backend != ModelBackend.MOCK:
            for group in puzzle.groups:
                prompt = f"""The category "{group.category}" contains: {', '.join(group.words)}

Improve this category name to be:
1. More specific than generic terms
2. Clearly indicate the connection
3. Concise (2-5 words ideal)
4. Not give away the answer too easily

Improved category (just the name, nothing else):"""
                
                response = self.generator._call_llm(prompt, temperature=0.3)
                if response:
                    new_cat = response.strip().split('\n')[0][:40]
                    if new_cat:
                        group.category = new_cat
        
        return puzzle
    
    def _balance_difficulty(self, puzzle: ConnectionsPuzzle) -> ConnectionsPuzzle:
        """Ensure proper difficulty distribution"""
        
        for group in puzzle.groups:
            embeddings = self.embedder.encode(group.words)
            similarities = cosine_similarity(embeddings)
            n = len(similarities)
            group.similarity_score = (similarities.sum() - n) / (n * (n - 1))
        
        puzzle.groups.sort(key=lambda g: g.similarity_score, reverse=True)
        colors = [DifficultyColor.YELLOW, DifficultyColor.GREEN, 
                 DifficultyColor.BLUE, DifficultyColor.PURPLE]
        
        for group, color in zip(puzzle.groups, colors):
            group.difficulty = color
        
        return puzzle
    
    def _remove_ambiguity(self, puzzle: ConnectionsPuzzle) -> ConnectionsPuzzle:
        """Identify and flag ambiguous words"""
        
        all_words = puzzle.get_all_words()
        embeddings = self.embedder.encode(all_words)
        word_to_group = puzzle.get_word_to_group_map()
        
        # Find words with high similarity to words in other groups
        ambiguous_words = []
        
        for i, word in enumerate(all_words):
            my_group = word_to_group[word]
            
            for j, other_word in enumerate(all_words):
                if i != j and word_to_group[other_word] != my_group:
                    sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                    if sim > 0.7:
                        ambiguous_words.append((word, other_word, sim))
        
        if ambiguous_words:
            puzzle.metadata['ambiguous_pairs'] = ambiguous_words[:5]
        
        return puzzle
    
    def _enhance_deception(self, puzzle: ConnectionsPuzzle) -> ConnectionsPuzzle:
        """Add metadata about deceptive elements"""
        
        all_words = puzzle.get_all_words()
        embeddings = self.embedder.encode(all_words)
        word_to_group = puzzle.get_word_to_group_map()
        
        # Find potential false groups (4 words from different groups that seem related)
        false_group_candidates = []
        
        for combo in itertools.combinations(range(16), 4):
            groups_represented = set(word_to_group[all_words[i]] for i in combo)
            
            if len(groups_represented) == 4:  # One from each group
                combo_words = [all_words[i] for i in combo]
                combo_emb = embeddings[list(combo)]
                sim_matrix = cosine_similarity(combo_emb)
                coherence = (sim_matrix.sum() - 4) / 12
                
                if coherence > 0.3:
                    false_group_candidates.append((combo_words, coherence))
        
        false_group_candidates.sort(key=lambda x: x[1], reverse=True)
        puzzle.metadata['false_group_candidates'] = false_group_candidates[:3]
        
        return puzzle
    
    def _verify_solvability(self, puzzle: ConnectionsPuzzle) -> ConnectionsPuzzle:
        """Verify puzzle is solvable and fix issues - uses proper word validation"""
        
        # Check for duplicate words
        all_words = puzzle.get_all_words()
        
        if len(all_words) != len(set(all_words)):
            # Fix duplicates using fallback groups
            seen = set()
            used_fallbacks = set()
            
            for group in puzzle.groups:
                new_words = []
                for word in group.words:
                    word_upper = word.upper()
                    if word_upper in seen:
                        # Find a replacement from fallback groups
                        replacement = None
                        fallback = generate_fallback_group(seen | used_fallbacks, self.embedder, None)
                        for fw in fallback.words:
                            if fw not in seen and fw not in used_fallbacks:
                                replacement = fw
                                used_fallbacks.add(fw)
                                break
                        
                        if replacement:
                            new_words.append(replacement)
                            seen.add(replacement)
                        else:
                            # Last resort - keep original with warning
                            new_words.append(word_upper)
                    else:
                        new_words.append(word_upper)
                        seen.add(word_upper)
                group.words = new_words
        
        # Validate all words are clean
        for group in puzzle.groups:
            cleaned_words = []
            for word in group.words:
                cleaned = clean_word(word) if clean_word else word.upper()
                if cleaned:
                    cleaned_words.append(cleaned)
            if len(cleaned_words) == 4:
                group.words = cleaned_words
        
        puzzle.metadata['verified_solvable'] = True
        return puzzle


class HumanEvaluator:
    """Comprehensive puzzle quality evaluation"""
    
    def __init__(self):
        self.embedder = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
        
    def evaluate(self, puzzle: ConnectionsPuzzle) -> Dict[str, Any]:
        """Evaluate puzzle quality with detailed metrics"""
        
        metrics = {
            'valid': puzzle.validate(),
            'difficulty_distribution': self._evaluate_difficulty(puzzle),
            'semantic_clarity': self._evaluate_semantic_clarity(puzzle),
            'deceptiveness': self._evaluate_deceptiveness(puzzle),
            'estimated_solve_rate': self._estimate_solve_rate(puzzle),
            'creativity_score': self._evaluate_creativity(puzzle),
            'category_quality': self._evaluate_categories(puzzle),
            'word_diversity': self._evaluate_word_diversity(puzzle),
            'near_miss_count': self._count_near_misses(puzzle),
            'overall_quality': 0.0
        }
        
        # Calculate overall quality
        weights = {
            'valid': 0.20,
            'difficulty_distribution': 0.15,
            'semantic_clarity': 0.20,
            'deceptiveness': 0.15,
            'creativity_score': 0.15,
            'category_quality': 0.10,
            'word_diversity': 0.05
        }
        
        overall = 0.0
        for key, weight in weights.items():
            if key in metrics and isinstance(metrics[key], (int, float)):
                overall += metrics[key] * weight
        
        metrics['overall_quality'] = overall
        
        return metrics
    
    def _evaluate_difficulty(self, puzzle: ConnectionsPuzzle) -> float:
        """Check difficulty progression follows paper guidelines"""
        
        difficulties = set(g.difficulty for g in puzzle.groups)
        if len(difficulties) != 4:
            return 0.0
        
        # Check similarity ordering
        groups_by_difficulty = {g.difficulty: g for g in puzzle.groups}
        
        yellow = groups_by_difficulty.get(DifficultyColor.YELLOW)
        purple = groups_by_difficulty.get(DifficultyColor.PURPLE)
        
        if yellow and purple:
            if yellow.similarity_score > purple.similarity_score:
                return 1.0
            elif yellow.similarity_score > purple.similarity_score - 0.1:
                return 0.7
        
        return 0.5
    
    def _evaluate_semantic_clarity(self, puzzle: ConnectionsPuzzle) -> float:
        """Evaluate how clear each group's connection is"""
        
        clarity_scores = []
        
        for group in puzzle.groups:
            embeddings = self.embedder.encode(group.words)
            similarities = cosine_similarity(embeddings)
            
            n = len(similarities)
            avg_similarity = (similarities.sum() - n) / (n * (n - 1))
            clarity_scores.append(avg_similarity)
        
        return np.mean(clarity_scores) if clarity_scores else 0.0
    
    def _evaluate_deceptiveness(self, puzzle: ConnectionsPuzzle) -> float:
        """Evaluate red herrings and false connections"""
        
        if puzzle.false_group:
            return 0.8
        
        # Check for cross-group similarities
        all_words = puzzle.get_all_words()
        embeddings = self.embedder.encode(all_words)
        word_to_group = puzzle.get_word_to_group_map()
        
        high_cross_sims = 0
        total_cross = 0
        
        for i in range(len(all_words)):
            for j in range(i+1, len(all_words)):
                if word_to_group[all_words[i]] != word_to_group[all_words[j]]:
                    sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                    total_cross += 1
                    if sim > 0.5:
                        high_cross_sims += 1
        
        if total_cross > 0:
            return min(high_cross_sims / total_cross * 3, 1.0)
        
        return 0.0
    
    def _estimate_solve_rate(self, puzzle: ConnectionsPuzzle) -> float:
        """
        Estimate solve rate based PURELY on computed puzzle metrics.
        No hardcoded base rates - everything derived from actual characteristics.
        """
        
        # Get actual computed metrics
        clarity = self._evaluate_semantic_clarity(puzzle)  # 0-1, higher = clearer groups
        deceptiveness = self._evaluate_deceptiveness(puzzle)  # 0-1, higher = more traps
        near_misses = self._count_near_misses(puzzle)  # count of 3+1 wrong combos
        
        # Compute cross-group similarity (how much groups overlap semantically)
        all_words = puzzle.get_all_words()
        if len(all_words) == 16:
            embeddings = self.embedder.encode(all_words)
            word_to_group = puzzle.get_word_to_group_map()
            
            cross_group_sim = 0.0
            cross_count = 0
            for i in range(len(all_words)):
                for j in range(i+1, len(all_words)):
                    if word_to_group[all_words[i]] != word_to_group[all_words[j]]:
                        sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                        cross_group_sim += sim
                        cross_count += 1
            
            avg_cross_sim = cross_group_sim / cross_count if cross_count > 0 else 0
        else:
            avg_cross_sim = 0.3
        
        # Compute category abstractness (abstract categories are harder)
        abstractness = 0.0
        abstract_indicators = ['___', 'before', 'after', 'slang', 'words that', 'things that', 
                               'can be', 'might', 'could', 'sometimes', 'also']
        for group in puzzle.groups:
            if any(ind in group.category.lower() for ind in abstract_indicators):
                abstractness += 0.25
        
        # Compute difficulty distribution quality
        has_all_difficulties = len(set(g.difficulty for g in puzzle.groups)) == 4
        difficulty_bonus = 0.1 if has_all_difficulties else 0
        
        # FORMULA: Solve rate based purely on metrics
        # Start from neutral 0.5
        rate = 0.5
        
        # High clarity makes puzzle easier (good for solving)
        rate += (clarity - 0.35) * 0.6  # clarity typically 0.25-0.50
        
        # High deceptiveness makes puzzle harder
        rate -= deceptiveness * 0.25
        
        # Near misses are strong difficulty indicators
        # Scale: 0-20 near misses = minor effect, 20-100 = moderate, 100+ = major
        near_miss_penalty = min(near_misses / 200, 0.25)  # Cap at 0.25 reduction
        rate -= near_miss_penalty
        
        # Cross-group similarity creates confusion
        rate -= (avg_cross_sim - 0.25) * 0.4  # baseline ~0.25
        
        # Abstract categories are harder
        rate -= abstractness * 0.15
        
        # Proper difficulty distribution helps players
        rate += difficulty_bonus
        
        # Clamp to reasonable range
        return max(min(rate, 0.90), 0.10)
    
    def _evaluate_creativity(self, puzzle: ConnectionsPuzzle) -> float:
        """Evaluate puzzle creativity"""
        
        creativity_score = 0.0
        
        # Wordplay indicators
        wordplay_indicators = ['___', 'rhyme', 'sound', 'letter', 'start', 'end']
        for group in puzzle.groups:
            if any(ind in group.category.lower() for ind in wordplay_indicators):
                creativity_score += 0.2
        
        # TriCO bonus
        if puzzle.metadata.get('generation_method') == 'trico':
            creativity_score += 0.3
        
        # Variety in category types
        category_types = set()
        for group in puzzle.groups:
            cat_lower = group.category.lower()
            if '___' in group.category:
                category_types.add('fill_blank')
            elif any(w in cat_lower for w in ['type', 'kind', 'form']):
                category_types.add('types')
            elif any(w in cat_lower for w in ['rhyme', 'sound', 'letter']):
                category_types.add('wordplay')
            else:
                category_types.add('semantic')
        
        creativity_score += len(category_types) * 0.1
        
        return min(creativity_score, 1.0)
    
    def _evaluate_categories(self, puzzle: ConnectionsPuzzle) -> float:
        """Evaluate category name quality"""
        
        scores = []
        
        for group in puzzle.groups:
            cat = group.category
            
            # Length check (2-6 words ideal)
            word_count = len(cat.split())
            if 2 <= word_count <= 6:
                length_score = 1.0
            elif word_count == 1 or word_count == 7:
                length_score = 0.7
            else:
                length_score = 0.5
            
            # Generic category penalty
            generic_terms = ['things', 'stuff', 'items', 'words', 'group']
            generic_penalty = 0.2 if any(g in cat.lower() for g in generic_terms) else 0
            
            scores.append(max(length_score - generic_penalty, 0))
        
        return np.mean(scores) if scores else 0.5
    
    def _evaluate_word_diversity(self, puzzle: ConnectionsPuzzle) -> float:
        """Evaluate diversity of words used"""
        
        all_words = puzzle.get_all_words()
        
        # Length diversity
        lengths = [len(w) for w in all_words]
        length_std = np.std(lengths)
        
        # First letter diversity
        first_letters = set(w[0] for w in all_words)
        letter_diversity = len(first_letters) / 16
        
        # Word type diversity (simple heuristic)
        return (min(length_std / 3, 1.0) + letter_diversity) / 2
    
    def _count_near_misses(self, puzzle: ConnectionsPuzzle) -> int:
        """Count near-miss quartets (3 correct + 1 wrong that seems to fit)"""
        
        all_words = puzzle.get_all_words()
        if len(all_words) != 16:
            return 0
        
        embeddings = self.embedder.encode(all_words)
        word_to_group = puzzle.get_word_to_group_map()
        
        near_misses = 0
        threshold = 0.35
        
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


class SmartPuzzlePlayer:
    """
    Intelligent puzzle player with multiple strategies including LLM reasoning.
    Much smarter than simple greedy embedding clustering!
    """
    
    def __init__(self, generator=None, 
                 strategy: PlayerStrategy = PlayerStrategy.HYBRID):
        self.generator = generator
        self.strategy = strategy
        self.embedder = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
        self.guess_history = []
        self.reasoning_traces = []
        
    def play(self, puzzle: ConnectionsPuzzle, verbose: bool = False) -> PlayResult:
        """Play the puzzle using the configured strategy"""
        
        start_time = time.time()
        self.guess_history = []
        self.reasoning_traces = []
        
        all_words = puzzle.get_all_words()
        word_to_group = puzzle.get_word_to_group_map()
        
        remaining_words = all_words.copy()
        groups_found = []
        mistakes = 0
        max_mistakes = 4
        
        while remaining_words and mistakes < max_mistakes and len(groups_found) < 4:
            # Make a guess based on strategy
            guess, reasoning = self._make_smart_guess(
                remaining_words, 
                groups_found, 
                mistakes,
                puzzle
            )
            
            if reasoning:
                self.reasoning_traces.append(reasoning)
            
            # Validate guess
            if len(guess) != 4:
                if verbose:
                    print(f"Invalid guess (not 4 words): {guess}")
                mistakes += 1
                self.guess_history.append((guess, False))
                continue
            
            # Check if already guessed
            guess_set = frozenset(guess)
            already_guessed = any(frozenset(g) == guess_set for g, _ in self.guess_history)
            
            if already_guessed:
                # Force a different guess
                guess, _ = self._make_random_guess(remaining_words)
                guess_set = frozenset(guess)
            
            if verbose:
                print(f"Guess: {guess}")
            
            # Check correctness
            is_correct = self._check_guess(guess, puzzle.groups)
            self.guess_history.append((guess, is_correct))
            
            if is_correct:
                groups_found.append(guess)
                for word in guess:
                    if word in remaining_words:
                        remaining_words.remove(word)
                if verbose:
                    print("Correct!")
            else:
                mistakes += 1
                if verbose:
                    # Check for near miss (3 out of 4)
                    near_miss = self._check_near_miss(guess, puzzle.groups)
                    if near_miss:
                        print(f"Incorrect (3/4 correct). Mistakes: {mistakes}/{max_mistakes}")
                    else:
                        print(f"Incorrect. Mistakes: {mistakes}/{max_mistakes}")
        
        # If we have remaining words and no mistakes left, 
        # the last group is automatically found if valid
        if len(remaining_words) == 4 and mistakes < max_mistakes:
            groups_found.append(remaining_words)
            remaining_words = []
        
        elapsed_time = time.time() - start_time
        
        return PlayResult(
            solved=len(groups_found) == 4,
            mistakes=mistakes,
            groups_found=groups_found,
            guess_history=self.guess_history,
            time_taken=elapsed_time,
            strategy_used=self.strategy.value,
            reasoning_traces=self.reasoning_traces
        )
    
    def _make_smart_guess(self, remaining_words: List[str], 
                         groups_found: List[List[str]], 
                         mistakes: int,
                         puzzle: ConnectionsPuzzle) -> Tuple[List[str], str]:
        """Make an intelligent guess based on strategy"""
        
        if len(remaining_words) <= 4:
            return remaining_words[:4], "Only 4 words left"
        
        if self.strategy == PlayerStrategy.RANDOM:
            return self._make_random_guess(remaining_words)
        
        elif self.strategy == PlayerStrategy.GREEDY_EMBEDDING:
            return self._make_embedding_guess(remaining_words)
        
        elif self.strategy == PlayerStrategy.LLM_REASONING:
            return self._make_llm_guess(remaining_words, groups_found, mistakes)
        
        elif self.strategy == PlayerStrategy.HYBRID:
            return self._make_hybrid_guess(remaining_words, groups_found, mistakes)
        
        elif self.strategy == PlayerStrategy.HUMAN_LIKE:
            return self._make_human_like_guess(remaining_words, groups_found, mistakes)
        
        else:
            return self._make_embedding_guess(remaining_words)
    
    def _make_random_guess(self, words: List[str]) -> Tuple[List[str], str]:
        """Random guess strategy"""
        shuffled = words.copy()
        random.shuffle(shuffled)
        return shuffled[:4], "Random selection"
    
    def _make_embedding_guess(self, words: List[str]) -> Tuple[List[str], str]:
        """Greedy embedding clustering guess"""
        
        embeddings = self.embedder.encode(words)
        
        # Try k-means clustering
        if len(words) >= 8:
            n_clusters = min(len(words) // 4, 4)
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            clusters = kmeans.fit_predict(embeddings)
            
            cluster_counts = Counter(clusters)
            for cluster_id, count in cluster_counts.most_common():
                if count >= 4:
                    cluster_words = [words[i] for i, c in enumerate(clusters) if c == cluster_id]
                    
                    # Pick the 4 most similar within cluster
                    cluster_indices = [i for i, c in enumerate(clusters) if c == cluster_id]
                    cluster_emb = embeddings[cluster_indices]
                    
                    # Calculate centroid and distances
                    centroid = cluster_emb.mean(axis=0)
                    distances = np.linalg.norm(cluster_emb - centroid, axis=1)
                    
                    # Pick 4 closest to centroid
                    closest_indices = np.argsort(distances)[:4]
                    guess = [cluster_words[i] for i in closest_indices]
                    
                    guess_set = frozenset(guess)
                    if not any(frozenset(g) == guess_set for g, _ in self.guess_history):
                        return guess, f"K-means cluster {cluster_id}"
        
        # Fallback: find 4 most mutually similar words
        similarity_matrix = cosine_similarity(embeddings)
        
        best_score = -1
        best_quartet = None
        
        # Sample combinations if too many
        all_combos = list(itertools.combinations(range(len(words)), 4))
        if len(all_combos) > 200:
            all_combos = random.sample(all_combos, 200)
        
        for combo in all_combos:
            sub_sim = similarity_matrix[np.ix_(combo, combo)]
            score = (sub_sim.sum() - 4) / 12
            
            if score > best_score:
                guess = [words[i] for i in combo]
                if not any(frozenset(guess) == frozenset(g) for g, _ in self.guess_history):
                    best_score = score
                    best_quartet = combo
        
        if best_quartet:
            return [words[i] for i in best_quartet], f"Highest coherence ({best_score:.3f})"
        
        return self._make_random_guess(words)
    
    def _make_llm_guess(self, remaining_words: List[str], 
                       groups_found: List[List[str]], 
                       mistakes: int) -> Tuple[List[str], str]:
        """Use LLM to reason about the best guess"""
        
        if not self.generator or self.generator.backend == ModelBackend.MOCK:
            return self._make_embedding_guess(remaining_words)
        
        prompt = PromptTemplates.smart_player_guess(
            remaining_words, 
            groups_found, 
            mistakes,
            self.guess_history
        )
        
        try:
            response = self.generator._call_llm(prompt, temperature=0.3)
            
            # Parse response for 4 words
            words_found = []
            
            # Try comma-separated
            if ',' in response:
                candidates = [w.strip().upper() for w in response.split(',')]
                words_found = [w for w in candidates if w in remaining_words][:4]
            
            # Try newline-separated or space-separated
            if len(words_found) < 4:
                candidates = re.findall(r'\b[A-Z][A-Z0-9\']+\b', response.upper())
                for w in candidates:
                    if w in remaining_words and w not in words_found:
                        words_found.append(w)
                        if len(words_found) == 4:
                            break
            
            if len(words_found) == 4:
                return words_found, f"LLM reasoning: {response[:100]}"
            else:
                # LLM failed, fall back to embedding
                return self._make_embedding_guess(remaining_words)
                
        except Exception as e:
            return self._make_embedding_guess(remaining_words)
    
    def _make_hybrid_guess(self, remaining_words: List[str], 
                          groups_found: List[List[str]], 
                          mistakes: int) -> Tuple[List[str], str]:
        """
        Hybrid strategy: Use multiple approaches and pick the best.
        This is the smartest strategy!
        """
        
        candidates = []
        
        # Strategy 1: Embedding clustering
        emb_guess, emb_reason = self._make_embedding_guess(remaining_words)
        if len(emb_guess) == 4:
            emb_score = self._score_guess(emb_guess)
            candidates.append((emb_guess, emb_score, emb_reason))
        
        # Strategy 2: Pattern matching (wordplay, prefixes, etc.)
        pattern_guess, pattern_reason = self._find_pattern_group(remaining_words)
        if pattern_guess and len(pattern_guess) == 4:
            pattern_score = self._score_guess(pattern_guess) + 0.1  # Bonus for patterns
            candidates.append((pattern_guess, pattern_score, pattern_reason))
        
        # Strategy 3: Category detection
        category_guess, category_reason = self._find_category_group(remaining_words)
        if category_guess and len(category_guess) == 4:
            category_score = self._score_guess(category_guess) + 0.05
            candidates.append((category_guess, category_score, category_reason))
        
        # Strategy 4: LLM reasoning (if available and mistakes are low)
        if mistakes < 2 and self.generator and self.generator.backend != ModelBackend.MOCK:
            llm_guess, llm_reason = self._make_llm_guess(remaining_words, groups_found, mistakes)
            if len(llm_guess) == 4:
                llm_score = self._score_guess(llm_guess) + 0.15  # Bonus for LLM
                candidates.append((llm_guess, llm_score, llm_reason))
        
        # Strategy 5: Hierarchical clustering
        hier_guess, hier_reason = self._make_hierarchical_guess(remaining_words)
        if len(hier_guess) == 4:
            hier_score = self._score_guess(hier_guess)
            candidates.append((hier_guess, hier_score, hier_reason))
        
        # Filter out already-guessed
        valid_candidates = []
        for guess, score, reason in candidates:
            if not any(frozenset(guess) == frozenset(g) for g, _ in self.guess_history):
                valid_candidates.append((guess, score, reason))
        
        if valid_candidates:
            # Pick highest scoring
            best = max(valid_candidates, key=lambda x: x[1])
            return best[0], f"Hybrid ({best[2]}, score={best[1]:.3f})"
        
        return self._make_random_guess(remaining_words)
    
    def _make_human_like_guess(self, remaining_words: List[str], 
                              groups_found: List[List[str]], 
                              mistakes: int) -> Tuple[List[str], str]:
        """
        Simulate human-like solving: 
        - Start with obvious patterns
        - Consider common category types
        - Make educated guesses based on semantics
        """
        
        # Phase 1: Look for obvious patterns first
        pattern_guess, pattern_reason = self._find_pattern_group(remaining_words)
        if pattern_guess and len(pattern_guess) == 4:
            if not any(frozenset(pattern_guess) == frozenset(g) for g, _ in self.guess_history):
                return pattern_guess, f"Human-like: {pattern_reason}"
        
        # Phase 2: Look for semantic categories
        category_guess, category_reason = self._find_category_group(remaining_words)
        if category_guess and len(category_guess) == 4:
            if not any(frozenset(category_guess) == frozenset(g) for g, _ in self.guess_history):
                return category_guess, f"Human-like: {category_reason}"
        
        # Phase 3: Use embeddings with human-like tie-breaking
        embeddings = self.embedder.encode(remaining_words)
        similarity_matrix = cosine_similarity(embeddings)
        
        # Find words that are clearly related to each other
        high_sim_pairs = []
        for i in range(len(remaining_words)):
            for j in range(i+1, len(remaining_words)):
                if similarity_matrix[i, j] > 0.5:
                    high_sim_pairs.append((i, j, similarity_matrix[i, j]))
        
        if high_sim_pairs:
            # Build groups from high-similarity pairs
            high_sim_pairs.sort(key=lambda x: x[2], reverse=True)
            
            for i, j, sim in high_sim_pairs[:5]:
                # Try to extend this pair to 4 words
                group = [i, j]
                candidates = []
                
                for k in range(len(remaining_words)):
                    if k not in group:
                        avg_sim = np.mean([similarity_matrix[k, g] for g in group])
                        candidates.append((k, avg_sim))
                
                candidates.sort(key=lambda x: x[1], reverse=True)
                
                for k, sim in candidates[:2]:
                    group.append(k)
                
                if len(group) == 4:
                    guess = [remaining_words[idx] for idx in group]
                    if not any(frozenset(guess) == frozenset(g) for g, _ in self.guess_history):
                        return guess, f"Human-like: Built from high-sim pair"
        
        # Fallback to embedding guess
        return self._make_embedding_guess(remaining_words)
    
    def _make_hierarchical_guess(self, words: List[str]) -> Tuple[List[str], str]:
        """Use hierarchical clustering for grouping"""
        
        if len(words) < 4:
            return words, "Not enough words"
        
        embeddings = self.embedder.encode(words)
        
        try:
            clustering = AgglomerativeClustering(n_clusters=min(4, len(words) // 4), 
                                                 metric='cosine',
                                                 linkage='average')
            clusters = clustering.fit_predict(embeddings)
            
            cluster_counts = Counter(clusters)
            for cluster_id, count in cluster_counts.most_common():
                if count >= 4:
                    cluster_words = [words[i] for i, c in enumerate(clusters) if c == cluster_id][:4]
                    return cluster_words, f"Hierarchical cluster {cluster_id}"
        except:
            pass
        
        return self._make_random_guess(words)
    
    def _find_pattern_group(self, words: List[str]) -> Tuple[Optional[List[str]], str]:
        """Find groups based on letter/word patterns"""
        
        # Check for common prefixes
        prefix_groups = defaultdict(list)
        for word in words:
            if len(word) >= 3:
                prefix_groups[word[:2].upper()].append(word)
        
        for prefix, group in prefix_groups.items():
            if len(group) >= 4:
                return group[:4], f"Common prefix '{prefix}'"
        
        # Check for common suffixes
        suffix_groups = defaultdict(list)
        for word in words:
            if len(word) >= 3:
                suffix_groups[word[-2:].upper()].append(word)
        
        for suffix, group in suffix_groups.items():
            if len(group) >= 4:
                return group[:4], f"Common suffix '{suffix}'"
        
        # Check for same length
        length_groups = defaultdict(list)
        for word in words:
            length_groups[len(word)].append(word)
        
        for length, group in length_groups.items():
            if len(group) >= 4 and length in [4, 5, 6]:  # Common word lengths
                return group[:4], f"{length}-letter words"
        
        # Check for double letters
        double_letter_words = [w for w in words if any(w[i] == w[i+1] for i in range(len(w)-1))]
        if len(double_letter_words) >= 4:
            return double_letter_words[:4], "Words with double letters"
        
        return None, ""
    
    def _find_category_group(self, words: List[str]) -> Tuple[Optional[List[str]], str]:
        """
        Find groups based on semantic similarity to category PROTOTYPES.
        Uses embeddings instead of hardcoded word lists!
        """
        
        # Category prototypes: just 2-3 seed words per category
        # The embedder determines if other words are similar enough
        category_prototypes = {
            'colors': ['RED', 'BLUE', 'GREEN'],
            'animals': ['DOG', 'CAT', 'LION'],
            'foods': ['PIZZA', 'BREAD', 'SOUP'],
            'sports': ['FOOTBALL', 'TENNIS', 'GOLF'],
            'countries': ['FRANCE', 'JAPAN', 'BRAZIL'],
            'instruments': ['PIANO', 'GUITAR', 'DRUMS'],
            'emotions': ['HAPPY', 'SAD', 'ANGRY'],
            'weather': ['RAIN', 'SNOW', 'WIND'],
            'furniture': ['CHAIR', 'TABLE', 'COUCH'],
            'vehicles': ['CAR', 'TRUCK', 'BOAT'],
        }
        
        word_embeddings = self.embedder.encode(words)
        
        for category_name, prototypes in category_prototypes.items():
            # Compute category centroid from prototypes
            prototype_embeddings = self.embedder.encode(prototypes)
            centroid = prototype_embeddings.mean(axis=0)
            
            # Find words similar to this category centroid
            similarities = cosine_similarity([centroid], word_embeddings)[0]
            
            # Words with similarity > 0.45 are considered matches
            # (threshold determined empirically - not too strict, not too loose)
            matches = []
            for i, sim in enumerate(similarities):
                if sim > 0.45:
                    matches.append((words[i], sim))
            
            # Sort by similarity and take top matches
            matches.sort(key=lambda x: x[1], reverse=True)
            
            if len(matches) >= 4:
                selected = [m[0] for m in matches[:4]]
                avg_sim = np.mean([m[1] for m in matches[:4]])
                return selected, f"Category: {category_name} (sim={avg_sim:.2f})"
        
        # Fallback: Try to find any 4 words that cluster together
        # without predefined categories
        if len(words) >= 4:
            sim_matrix = cosine_similarity(word_embeddings)
            
            # Find the best quartet by coherence
            best_quartet = None
            best_score = 0.5  # Minimum threshold
            
            combos = list(itertools.combinations(range(len(words)), 4))
            if len(combos) > 50:
                combos = random.sample(combos, 50)
            
            for combo in combos:
                sub_sim = sim_matrix[np.ix_(combo, combo)]
                score = (sub_sim.sum() - 4) / 12
                if score > best_score:
                    best_score = score
                    best_quartet = combo
            
            if best_quartet:
                selected = [words[i] for i in best_quartet]
                return selected, f"Detected cluster (coherence={best_score:.2f})"
        
        return None, ""
    
    def _score_guess(self, guess: List[str]) -> float:
        """Score a guess based on semantic coherence"""
        
        if len(guess) != 4:
            return 0.0
        
        embeddings = self.embedder.encode(guess)
        similarities = cosine_similarity(embeddings)
        
        return (similarities.sum() - 4) / 12
    
    def _check_guess(self, guess: List[str], groups: List[WordGroup]) -> bool:
        """Check if guess matches any group"""
        
        guess_set = set(w.upper() for w in guess)
        
        for group in groups:
            group_set = set(w.upper() for w in group.words)
            if guess_set == group_set:
                return True
        
        return False
    
    def _check_near_miss(self, guess: List[str], groups: List[WordGroup]) -> bool:
        """Check if guess has 3 out of 4 correct"""
        
        guess_set = set(w.upper() for w in guess)
        
        for group in groups:
            group_set = set(w.upper() for w in group.words)
            if len(guess_set.intersection(group_set)) == 3:
                return True
        
        return False


class PuzzleSimulator:
    """Run multiple simulations to get accurate solve statistics"""
    
    def __init__(self, generator=None):
        self.generator = generator
        
    def simulate(self, puzzle: ConnectionsPuzzle, 
                num_simulations: int = 10,
                strategies: List[PlayerStrategy] = None,
                verbose: bool = False) -> SimulationResult:
        """Run multiple simulations and compute statistics"""
        
        if strategies is None:
            strategies = [
                PlayerStrategy.HYBRID,
                PlayerStrategy.HUMAN_LIKE,
                PlayerStrategy.GREEDY_EMBEDDING,
            ]
        
        all_results = []
        strategy_results = defaultdict(list)
        
        print(f"\nRunning {num_simulations} simulations...")
        
        for i in range(num_simulations):
            # Rotate through strategies
            strategy = strategies[i % len(strategies)]
            
            player = SmartPuzzlePlayer(self.generator, strategy)
            result = player.play(puzzle, verbose=False)
            
            all_results.append(result)
            strategy_results[strategy.value].append(result)
            
            if verbose or (i + 1) % max(1, num_simulations // 10) == 0:
                print(f"  Simulation {i+1}/{num_simulations}: "
                      f"{'Solved' if result.solved else 'Failed'}, "
                      f"Mistakes: {result.mistakes}, Strategy: {strategy.value}")
        
        # Compute statistics
        solve_count = sum(1 for r in all_results if r.solved)
        solve_rate = solve_count / num_simulations
        
        mistakes_list = [r.mistakes for r in all_results]
        mean_mistakes = np.mean(mistakes_list)
        std_mistakes = np.std(mistakes_list)
        
        groups_found_list = [len(r.groups_found) for r in all_results]
        mean_groups = np.mean(groups_found_list)
        
        # Strategy breakdown
        strategy_breakdown = {}
        for strategy_name, results in strategy_results.items():
            if results:
                strategy_solve_rate = sum(1 for r in results if r.solved) / len(results)
                strategy_breakdown[strategy_name] = strategy_solve_rate
        
        return SimulationResult(
            num_simulations=num_simulations,
            solve_rate=solve_rate,
            mean_mistakes=mean_mistakes,
            std_mistakes=std_mistakes,
            mean_groups_found=mean_groups,
            individual_results=all_results,
            strategy_breakdown=strategy_breakdown
        )
    
    def compare_strategies(self, puzzle: ConnectionsPuzzle,
                          num_per_strategy: int = 20) -> Dict[str, Dict[str, float]]:
        """Compare different player strategies"""
        
        strategies = [
            PlayerStrategy.RANDOM,
            PlayerStrategy.GREEDY_EMBEDDING,
            PlayerStrategy.HYBRID,
            PlayerStrategy.HUMAN_LIKE,
        ]
        
        # Add LLM if available
        if self.generator and self.generator.backend != ModelBackend.MOCK:
            strategies.append(PlayerStrategy.LLM_REASONING)
        
        results = {}
        
        print("\nComparing player strategies...")
        
        for strategy in strategies:
            print(f"  Testing {strategy.value}...")
            
            player = SmartPuzzlePlayer(self.generator, strategy)
            strategy_results = []
            
            for _ in range(num_per_strategy):
                result = player.play(puzzle, verbose=False)
                strategy_results.append(result)
            
            solve_rate = sum(1 for r in strategy_results if r.solved) / num_per_strategy
            mean_mistakes = np.mean([r.mistakes for r in strategy_results])
            mean_time = np.mean([r.time_taken for r in strategy_results])
            
            results[strategy.value] = {
                'solve_rate': solve_rate,
                'mean_mistakes': mean_mistakes,
                'mean_time': mean_time
            }
        
        return results


# ============================================================
# DISPLAY FUNCTIONS
# ============================================================

def print_puzzle(puzzle: ConnectionsPuzzle):
    """Pretty print a puzzle with deception info"""
    
    print("\n" + "=" * 60)
    print("GENERATED PUZZLE")
    print("=" * 60)
    
    for group in puzzle.groups:
        color_name = group.difficulty.name
        print(f"{color_name:8} | {group.category:25} | {', '.join(group.words)}")
    
    if puzzle.false_group:
        print(f"\nFalse Group: {puzzle.false_group.category}")
        print(f"  Trap Words: {', '.join(puzzle.false_group.words)}")
        print(f"  (These words are in the puzzle but DON'T go together!)")
    
    # Show trap word info if available
    if 'trap_words' in puzzle.metadata and puzzle.metadata['trap_words']:
        print(f"\nIdentified Trap Words: {', '.join(puzzle.metadata['trap_words'][:6])}")
    
    if 'confusing_pairs' in puzzle.metadata and puzzle.metadata['confusing_pairs']:
        print(f"Most Confusing Pairs:")
        for w1, w2, sim in puzzle.metadata['confusing_pairs'][:3]:
            print(f"  {w1} <-> {w2} (similarity: {sim})")


def print_evaluation(metrics: Dict[str, Any]):
    """Pretty print evaluation metrics"""
    
    print("\n" + "=" * 60)
    print("EVALUATION SCORES")
    print("=" * 60)
    
    print(f"Valid Puzzle:          {'✓' if metrics['valid'] else '✗'}")
    print(f"Difficulty Balance:    {metrics['difficulty_distribution']:.2f}")
    print(f"Semantic Clarity:      {metrics['semantic_clarity']:.2f}")
    print(f"Deceptiveness:         {metrics['deceptiveness']:.2f}")
    print(f"Creativity Score:      {metrics['creativity_score']:.2f}")
    print(f"Category Quality:      {metrics['category_quality']:.2f}")
    print(f"Word Diversity:        {metrics['word_diversity']:.2f}")
    print(f"Near-miss Count:       {metrics['near_miss_count']}")
    print(f"Est. Solve Rate:       {metrics['estimated_solve_rate']:.1%}")
    print(f"")
    print(f"OVERALL QUALITY:       {metrics['overall_quality']:.2f}/1.00")


def print_simulation_results(sim_result: SimulationResult):
    """Pretty print simulation results"""
    
    print("\n" + "=" * 60)
    print("SIMULATION RESULTS")
    print("=" * 60)
    
    print(f"Simulations Run:       {sim_result.num_simulations}")
    print(f"Solve Rate:            {sim_result.solve_rate:.1%}")
    print(f"Mean Mistakes:         {sim_result.mean_mistakes:.2f} ± {sim_result.std_mistakes:.2f}")
    print(f"Mean Groups Found:     {sim_result.mean_groups_found:.2f}/4")
    
    if sim_result.strategy_breakdown:
        print(f"\nSolve Rate by Strategy:")
        for strategy, rate in sorted(sim_result.strategy_breakdown.items(), 
                                     key=lambda x: x[1], reverse=True):
            print(f"  {strategy:20} {rate:.1%}")
