"""
NYT Connections Puzzle Generator - Core Module
Contains: Data structures, enums, utilities, prompt templates
"""

# ============================================================
# IMPORTS
# ============================================================

import os
# Environment-aware cache configuration
# Check if running in container environment (Kubernetes PVC)
if os.path.exists('/pvcvolume'):
    # Container environment - use PVC paths
    CACHE_BASE = '/pvcvolume'
else:
    # Local environment - use home directory
    CACHE_BASE = os.path.expanduser('~/.cache/connections_puzzle')

# Set up HuggingFace cache directories
# HF_HOME is the main cache location (preferred in transformers v5+)
os.environ['HF_HOME'] = os.path.join(CACHE_BASE, 'huggingface')
os.environ['TMPDIR'] = os.path.join(CACHE_BASE, 'tmp')

# Create directories if they don't exist
os.makedirs(os.path.join(CACHE_BASE, 'huggingface'), exist_ok=True)
os.makedirs(os.path.join(CACHE_BASE, 'tmp'), exist_ok=True)


import json
import random
import numpy as np
from typing import List, Dict, Tuple, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import itertools
from collections import defaultdict, Counter
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_similarity, pairwise_distances
from sklearn.feature_extraction.text import TfidfVectorizer
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from transformers import AutoTokenizer, AutoModelForCausalLM
import warnings
import pickle
from pathlib import Path
import copy
from scipy.spatial.distance import jensenshannon
from scipy.stats import entropy
import re
import time
import difflib

warnings.filterwarnings('ignore')

# Try to import phonetics library for TriCO
try:
    import phonetics
    PHONETICS_AVAILABLE = True
except ImportError:
    PHONETICS_AVAILABLE = False
    print("Warning: phonetics library not available, using fallback for phonetic similarity")

# Load environment variables
load_dotenv()


# ============================================================
# ENUMS AND CONFIGURATION
# ============================================================

class PuzzleMode(Enum):
    """Different puzzle generation modes"""
    ONE_STEP = "one_step"
    INTENTIONAL_OVERLAP = "intentional_overlap"
    FALSE_GROUP = "false_group"
    FALSE_GROUP_SEEDED = "false_group_seeded"
    TREE_OF_THOUGHTS = "tree_of_thoughts"
    TRICO = "trico"


class ModelBackend(Enum):
    """Model backend options"""
    MOCK = "mock"
    OPENAI = "openai"
    OPEN_SOURCE = "open_source"


class DifficultyColor(Enum):
    """Difficulty levels with colors from paper"""
    YELLOW = (0.4017, 0.0285)  # Easy - highest similarity
    GREEN = (0.3536, 0.0214)   
    BLUE = (0.2905, 0.0123)    
    PURPLE = (0.2664, 0.0108)  # Hard - lowest similarity


class PlayerStrategy(Enum):
    """Player strategies for simulation"""
    RANDOM = "random"
    GREEDY_EMBEDDING = "greedy_embedding"
    LLM_REASONING = "llm_reasoning"
    HYBRID = "hybrid"
    HUMAN_LIKE = "human_like"


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class WordGroup:
    """Represents a group of 4 connected words"""
    words: List[str]
    category: str
    difficulty: DifficultyColor
    similarity_score: float = 0.0
    alternate_meanings: List[str] = field(default_factory=list)
    semantic_field: Optional[str] = None
    primary_view: Optional[str] = None  # For TriCO
    category_style: Optional[str] = None
    confidence: float = 1.0  # How confident we are in this grouping


@dataclass
class ConnectionsPuzzle:
    """Complete Connections puzzle"""
    groups: List[WordGroup]
    false_group: Optional[WordGroup] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def validate(self) -> bool:
        """Validate puzzle constraints from paper"""
        if len(self.groups) != 4:
            return False
        
        all_words = []
        for group in self.groups:
            if len(group.words) != 4:
                return False
            all_words.extend(group.words)
        
        # Check unique words
        if len(all_words) != len(set(all_words)):
            return False
            
        # Check exactly one of each difficulty
        difficulties = [g.difficulty for g in self.groups]
        if len(set(difficulties)) != 4:
            return False
            
        return True
    
    def get_all_words(self) -> List[str]:
        """Get all 16 words in the puzzle"""
        words = []
        for group in self.groups:
            words.extend(group.words)
        return words
    
    def get_word_to_group_map(self) -> Dict[str, int]:
        """Map each word to its group index"""
        mapping = {}
        for i, group in enumerate(self.groups):
            for word in group.words:
                mapping[word] = i
        return mapping


@dataclass
class PlayResult:
    """Result of a single puzzle play attempt"""
    solved: bool
    mistakes: int
    groups_found: List[List[str]]
    guess_history: List[Tuple[List[str], bool]]
    time_taken: float = 0.0
    strategy_used: str = ""
    reasoning_traces: List[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Result of multiple simulation runs"""
    num_simulations: int
    solve_rate: float
    mean_mistakes: float
    std_mistakes: float
    mean_groups_found: float
    individual_results: List[PlayResult]
    strategy_breakdown: Dict[str, float] = field(default_factory=dict)


# ============================================================
# OPEN SOURCE LLM WRAPPER
# ============================================================

class OpenSourceLLM:
    """Wrapper for open source language models"""
    
    RECOMMENDED_MODELS = [
        ("mistralai/Mistral-7B-Instruct-v0.2", "Mistral 7B - Best balance (13GB)"),
        ("HuggingFaceH4/zephyr-7b-beta", "Zephyr 7B - Fine-tuned (13GB)"),
        ("teknium/OpenHermes-2.5-Mistral-7B", "OpenHermes 2.5 (13GB)"),
        ("microsoft/phi-2", "Phi-2 - Lightweight (2.7GB)"),
        ("TinyLlama/TinyLlama-1.1B-Chat-v1.0", "TinyLlama (2GB)"),
        ("stabilityai/stablelm-3b-4e1t", "StableLM 3B (3GB)"),
        ("mistralai/Mixtral-8x7B-Instruct-v0.1", "Mixtral 8x7B (93GB)"),
        ("meta-llama/Llama-2-7b-chat-hf", "Llama 2 7B (13GB)"),
    ]
    
    def __init__(self, model_name: str = None):
        """Initialize with a specific model"""
        if model_name is None:
            model_name = "mistralai/Mistral-7B-Instruct-v0.2"
            print(f"No model specified, defaulting to {model_name}")
        
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"Loading {model_name}...")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            
            # Configure based on model size
            if "70b" in model_name.lower() or "67b" in model_name.lower():
                from transformers import BitsAndBytesConfig
                quantization_config = BitsAndBytesConfig(
                    load_in_8bit=True,
                    bnb_8bit_compute_dtype=torch.float16
                )
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    quantization_config=quantization_config,
                    device_map="auto",
                    trust_remote_code=True
                )
            elif "7b" in model_name.lower() or "7B" in model_name:
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    device_map="auto",
                    trust_remote_code=True
                )
            elif "mixtral" in model_name.lower() or "8x7b" in model_name.lower():
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16,
                    device_map="auto",
                    trust_remote_code=True
                )
            else:
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name, 
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    device_map="auto" if self.device == "cuda" else None,
                    trust_remote_code=True
                )
                if self.device == "cpu":
                    self.model = self.model.to(self.device)
            
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
                
            print(f"Model loaded successfully on {self.device}")
        except Exception as e:
            print(f"Error loading model: {e}")
            print("Falling back to microsoft/phi-2")
            self.model_name = "microsoft/phi-2"
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto" if self.device == "cuda" else None,
                trust_remote_code=True
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
    
    def generate(self, prompt: str, max_length: int = 500, temperature: float = 0.8) -> str:
        """Generate text from prompt"""
        if "mixtral" in self.model_name.lower() or "llama" in self.model_name.lower():
            temperature = 0.7
            top_p = 0.9
            repetition_penalty = 1.1
        else:
            top_p = 0.95
            repetition_penalty = 1.0
        
        inputs = self.tokenizer(prompt, return_tensors="pt", padding=True, truncation=True, max_length=2048)
        
        if self.device == "cuda":
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_length,
                temperature=temperature,
                do_sample=True,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                pad_token_id=self.tokenizer.pad_token_id
            )
        
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        response = response[len(prompt):].strip()
        
        return response


# ============================================================
# TREE OF THOUGHTS NODE
# ============================================================

class TreeOfThoughtsNode:
    """Node for Tree of Thoughts reasoning"""
    
    def __init__(self, state: Dict[str, Any], parent: Optional['TreeOfThoughtsNode'] = None):
        self.state = state
        self.parent = parent
        self.children = []
        self.score = 0.0
        self.visits = 0
        self.reasoning = ""
        
    def add_child(self, child_state: Dict[str, Any]) -> 'TreeOfThoughtsNode':
        child = TreeOfThoughtsNode(child_state, self)
        self.children.append(child)
        return child
    
    def ucb_score(self, exploration_weight: float = 1.414) -> float:
        """Upper Confidence Bound score for MCTS-like selection"""
        if self.visits == 0:
            return float('inf')
        exploitation = self.score / self.visits
        exploration = exploration_weight * np.sqrt(np.log(self.parent.visits + 1) / self.visits)
        return exploitation + exploration


# ============================================================
# REINFORCEMENT LEARNING BUFFER
# ============================================================

class ReinforcementLearningBuffer:
    """Buffer for storing and learning from puzzle feedback"""
    
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.buffer = []
        self.save_path = Path("puzzle_feedback.pkl")
        self.load_buffer()
    
    def add(self, puzzle: ConnectionsPuzzle, feedback: Dict[str, Any]):
        """Add puzzle and feedback to buffer"""
        self.buffer.append({
            'puzzle': puzzle,
            'feedback': feedback,
            'timestamp': np.datetime64('now')
        })
        
        if len(self.buffer) > self.capacity:
            self.buffer.pop(0)
        
        self.save_buffer()
    
    def get_statistics(self) -> Dict[str, float]:
        """Get statistics from buffer"""
        if not self.buffer:
            return {}
        
        solve_rates = [item['feedback'].get('solve_rate', 0.5) for item in self.buffer]
        enjoyment_scores = [item['feedback'].get('enjoyment', 0.5) for item in self.buffer]
        
        return {
            'avg_solve_rate': np.mean(solve_rates),
            'avg_enjoyment': np.mean(enjoyment_scores),
            'total_puzzles': len(self.buffer)
        }
    
    def save_buffer(self):
        """Persist buffer to disk"""
        try:
            with open(self.save_path, 'wb') as f:
                pickle.dump(self.buffer, f)
        except Exception as e:
            pass  # Silently fail
    
    def load_buffer(self):
        """Load buffer from disk"""
        if self.save_path.exists():
            try:
                with open(self.save_path, 'rb') as f:
                    self.buffer = pickle.load(f)
            except Exception as e:
                pass


# ============================================================
# ENHANCED DIFFICULTY PREDICTOR (NEURAL NETWORK)
# ============================================================

class EnhancedDifficultyPredictor(nn.Module):
    """Neural network to predict puzzle difficulty"""
    
    def __init__(self, input_dim: int = 768, hidden_dim: int = 256):
        super().__init__()
        
        self.word_encoder = nn.Linear(input_dim, hidden_dim)
        self.group_encoder = nn.Linear(hidden_dim * 4, hidden_dim)
        self.puzzle_encoder = nn.Linear(hidden_dim * 4, hidden_dim)
        
        self.fc1 = nn.Linear(hidden_dim, 128)
        self.fc2 = nn.Linear(128, 64)
        self.fc3 = nn.Linear(64, 1)
        
        self.dropout = nn.Dropout(0.3)
        self.layer_norm1 = nn.LayerNorm(hidden_dim)
        self.layer_norm2 = nn.LayerNorm(128)
        
        self.sigmoid = nn.Sigmoid()
        
        self.optimizer = optim.Adam(self.parameters(), lr=0.001)
        self.criterion = nn.MSELoss()
        
    def forward(self, word_embeddings: torch.Tensor) -> torch.Tensor:
        """Forward pass"""
        batch_size = word_embeddings.shape[0]
        word_features = F.relu(self.word_encoder(word_embeddings))
        
        word_features = word_features.reshape(batch_size, 4, 4, -1)
        group_features = word_features.mean(dim=2)
        group_features = group_features.reshape(batch_size, -1)
        group_features = F.relu(self.group_encoder(group_features))
        group_features = self.layer_norm1(group_features)
        
        x = self.dropout(group_features)
        x = F.relu(self.fc1(x))
        x = self.layer_norm2(x)
        x = self.dropout(x)
        x = F.relu(self.fc2(x))
        x = self.sigmoid(self.fc3(x))
        
        return x
    
    def predict(self, puzzle: ConnectionsPuzzle, embedder) -> float:
        """Predict solve rate for a puzzle"""
        self.eval()
        
        words = []
        for group in puzzle.groups:
            words.extend(group.words)
        
        embeddings = embedder.encode(words)
        input_tensor = torch.FloatTensor(embeddings).unsqueeze(0)
        
        with torch.no_grad():
            prediction = self.forward(input_tensor)
        
        return prediction.item()


# ============================================================
# TRICO SIMILARITY CALCULATOR
# ============================================================

class TriCOSimilarityCalculator:
    """Calculate tri-view similarities for TriCO approach"""
    
    def __init__(self, embedder):
        self.embedder = embedder
        self.tfidf = None
        
    def _jaro_winkler(self, a: str, b: str) -> float:
        """Calculate Jaro-Winkler similarity"""
        return difflib.SequenceMatcher(None, a, b).ratio()
    
    def _char_ngram_cosine(self, words: List[str], n: int = 3) -> np.ndarray:
        """Calculate character n-gram cosine similarity"""
        vec = TfidfVectorizer(analyzer='char', ngram_range=(n, n))
        try:
            X = vec.fit_transform([w.lower() for w in words])
            S = 1.0 - pairwise_distances(X, metric='cosine')
            return S
        except:
            # Fallback if TF-IDF fails
            N = len(words)
            return np.eye(N)
    
    def _phonetic_sim(self, words: List[str]) -> np.ndarray:
        """Calculate phonetic similarity matrix"""
        N = len(words)
        S = np.zeros((N, N))
        
        if PHONETICS_AVAILABLE:
            try:
                keys = [(phonetics.dmetaphone(w)[0] or w) for w in words]
                for i in range(N):
                    for j in range(N):
                        S[i, j] = self._jaro_winkler(keys[i].lower(), keys[j].lower())
                return S
            except:
                pass
        
        # Fallback to Jaro-Winkler on raw words
        for i in range(N):
            for j in range(N):
                S[i, j] = self._jaro_winkler(words[i].lower(), words[j].lower())
        return S
    
    def _semantic_sim(self, words: List[str]) -> np.ndarray:
        """Calculate semantic similarity using embeddings"""
        E = self.embedder.encode(words)
        E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-8)
        return E @ E.T
    
    def build_triview_sims(self, words: List[str]) -> Dict[str, np.ndarray]:
        """Build all three similarity matrices"""
        S_sem = self._semantic_sim(words)
        S_pho = self._phonetic_sim(words)
        S_orth = self._char_ngram_cosine(words, n=3)
        
        return {
            'sem': S_sem,
            'pho': S_pho,
            'orth': S_orth
        }


# ============================================================
# SEMANTIC KNOWLEDGE BASE
# ============================================================

class SemanticKnowledgeBase:
    """Knowledge base for word associations and category patterns"""
    
    def __init__(self):
        self.category_patterns = self._load_category_patterns()
        self.semantic_networks = self._build_semantic_networks()
        self.wordplay_patterns = self._load_wordplay_patterns()
        
    def _load_category_patterns(self) -> Dict[str, List[str]]:
        """Extended category patterns based on NYT analysis"""
        return {
            "synonyms": ["Words meaning X", "Types of Y", "Kinds of Z", "Forms of X"],
            "wordplay": ["Rhymes with X", "Contains Y", "Anagrams of Z", "Sounds like X"],
            "fill_blank": ["____ X", "X ____", "X Y ____", "____ X Y"],
            "slang": ["Slang for X", "Internet terms for Y", "Nicknames for Z"],
            "specific": ["5-letter words", "Names", "Verbs", "Adjectives"],
            "homophones": ["Homophones of X", "Sounds like Y"],
            "compounds": ["X + Y", "Compound words with X"],
            "abbreviations": ["Short for X", "Initials of Y"],
            "pop_culture": ["Characters from X", "Songs by Y", "Movies with Z"],
            "technical": ["Programming terms", "Medical terms", "Legal terms"],
            "historical": ["Ancient X", "Medieval Y", "Modern Z"],
            "geographical": ["Cities in X", "Rivers of Y", "Mountains in Z"],
            "double_meaning": ["Words that mean both X and Y"],
            "prefix_suffix": ["Words ending in X", "Words starting with Y"],
            "letter_patterns": ["Words with double letters", "Palindromes"],
        }
    
    def _build_semantic_networks(self) -> Dict[str, List[str]]:
        """Build rich semantic networks"""
        return {
            "sports": ["FOOTBALL", "BASKETBALL", "TENNIS", "SOCCER", "BASEBALL", 
                      "HOCKEY", "GOLF", "SWIMMING", "RUNNING", "CYCLING",
                      "VOLLEYBALL", "CRICKET", "RUGBY", "BOXING", "WRESTLING"],
            "technology": ["COMPUTER", "PHONE", "TABLET", "SOFTWARE", "HARDWARE",
                          "INTERNET", "CLOUD", "DATA", "ALGORITHM", "CODE",
                          "PYTHON", "JAVA", "SERVER", "DATABASE", "NETWORK"],
            "food": ["PIZZA", "PASTA", "BURGER", "SALAD", "SOUP", "SANDWICH",
                    "RICE", "BREAD", "CHEESE", "FRUIT", "SUSHI", "CURRY",
                    "STEAK", "CHICKEN", "FISH"],
            "music": ["JAZZ", "ROCK", "POP", "CLASSICAL", "BLUES", "COUNTRY",
                     "METAL", "FOLK", "ELECTRONIC", "RAP", "SOUL", "REGGAE",
                     "OPERA", "SYMPHONY", "BAND"],
            "nature": ["TREE", "MOUNTAIN", "RIVER", "OCEAN", "FOREST", "DESERT",
                      "VALLEY", "LAKE", "MEADOW", "CANYON", "ISLAND", "BEACH",
                      "VOLCANO", "GLACIER", "REEF"],
            "colors": ["RED", "BLUE", "GREEN", "YELLOW", "PURPLE", "ORANGE",
                      "BLACK", "WHITE", "PINK", "BROWN", "GRAY", "GOLD",
                      "SILVER", "TEAL", "MAROON"],
            "animals": ["DOG", "CAT", "BIRD", "FISH", "HORSE", "COW", "PIG",
                       "SHEEP", "LION", "TIGER", "BEAR", "WOLF", "FOX",
                       "DEER", "RABBIT"],
            "professions": ["DOCTOR", "TEACHER", "ENGINEER", "LAWYER", "ARTIST",
                           "CHEF", "PILOT", "NURSE", "WRITER", "ACTOR",
                           "SCIENTIST", "MUSICIAN", "ATHLETE", "DESIGNER", "MANAGER"],
        }
    
    def _load_wordplay_patterns(self) -> Dict[str, Callable]:
        """Patterns for detecting wordplay"""
        return {
            "palindrome": lambda w: w.upper() == w.upper()[::-1],
            "double_letter": lambda w: any(w[i] == w[i+1] for i in range(len(w)-1)),
            "starts_with_vowel": lambda w: w[0].upper() in "AEIOU",
            "ends_with_vowel": lambda w: w[-1].upper() in "AEIOU",
            "alternating_vowels": lambda w: all(
                (c.upper() in "AEIOU") == (i % 2 == 0) 
                for i, c in enumerate(w) if c.isalpha()
            ),
        }
    
    def find_related_words(self, seed_word: str, count: int = 10) -> List[str]:
        """Find words related to a seed word"""
        related = []
        seed_lower = seed_word.lower()
        
        for network_name, words in self.semantic_networks.items():
            if seed_word.upper() in words:
                # Found the network, return other words
                related.extend([w for w in words if w != seed_word.upper()])
        
        return related[:count]
    
    def detect_category_type(self, words: List[str], category: str) -> str:
        """Detect the type of category based on words and name"""
        category_lower = category.lower()
        
        # Check for fill-in-blank
        if "___" in category or "blank" in category_lower:
            return "fill_blank"
        
        # Check for wordplay indicators
        wordplay_keywords = ["rhyme", "sound", "letter", "start", "end", "contain"]
        if any(kw in category_lower for kw in wordplay_keywords):
            return "wordplay"
        
        # Check for synonym patterns
        if any(kw in category_lower for kw in ["meaning", "synonym", "type", "kind"]):
            return "synonyms"
        
        # Check for pop culture
        if any(kw in category_lower for kw in ["movie", "song", "book", "character", "show"]):
            return "pop_culture"
        
        return "general"


# ============================================================
# PROMPT TEMPLATES (ENHANCED FOR DIFFICULTY)
# ============================================================

class PromptTemplates:
    """Centralized prompt templates for HARD puzzle generation"""
    
    # Real NYT purple category examples for inspiration
    HARD_CATEGORY_EXAMPLES = [
        "___ MONKEY (Spider, Grease, Powder, Brass)",
        "Words before HOUSE (Power, Open, White, Full)",
        "Things that can be ELECTRIC (Slide, Chair, Fence, Eel)",
        "Slang for $1000 (Grand, Stack, Band, Rack)",
        "NBA team names minus a letter (Eat, Kin, Bul, Cavs->Cas)",
        "Poker terms (Fold, Check, Raise, Call)",
        "Words spelled with Roman numerals (Civil, Livid, Mild, Dill)",
        "Types of KEYS (Florida, Piano, Skeleton, Car)",
        "Sounds a cat makes + S (Meows, Purrs, Hisses, Mews)",
        "BANANA ___ (Split, Republic, Bread, Peel)"
    ]
    
    @staticmethod
    def one_step(theme: Optional[str] = None) -> str:
        prompt = """Generate a DECEPTIVELY DIFFICULT Connections puzzle with 4 groups of 4 words.

CRITICAL REQUIREMENTS FOR DIFFICULTY:
1. Include at least 3 words with MULTIPLE MEANINGS spread across different groups
   (e.g., BARK in "Dog sounds" but could trick players into "Tree parts")
2. Create at least one FALSE CONNECTION - 4 words from different groups that SEEM related
   (e.g., CHERRY, LIME, LEMON, ORANGE could seem like fruits but belong to different categories)
3. PURPLE category MUST be abstract: wordplay, fill-in-blank, cultural reference, or lateral thinking

CATEGORY TYPE REQUIREMENTS:
- YELLOW: Straightforward but include 1 word with alternate meaning
- GREEN: Less obvious connection, include 1-2 trap words
- BLUE: Require knowledge or lateral thinking
- PURPLE: Must be one of these types:
  * "_____ WORD" (fill in blank before)
  * "WORD _____" (fill in blank after)  
  * Words that can follow/precede a common word
  * Slang terms for something
  * Words sharing hidden property (spelled with only certain letters, etc.)

TRAP WORD EXAMPLES (words that bridge categories):
- SPRING: season / metal coil / water source / to jump
- CRANE: bird / construction equipment / to stretch neck
- BASS: fish / musical instrument / low frequency
- SEAL: marine animal / to close / stamp of approval
- JAM: fruit spread / traffic / music session / to force

Include at least 4 such multi-meaning words scattered across your groups!

Output format:
YELLOW: [category] - word1, word2, word3, word4
GREEN: [category] - word1, word2, word3, word4
BLUE: [category] - word1, word2, word3, word4
PURPLE: [category] - word1, word2, word3, word4"""
        
        if theme:
            prompt += f"\n\nTheme hint (incorporate loosely): {theme}"
        return prompt
    
    @staticmethod
    def intentional_overlap_root(theme: Optional[str] = None) -> str:
        prompt = """Generate 4 words that ALL have MULTIPLE DIFFERENT MEANINGS.
These will be "trap words" in a Connections puzzle - each will go in a DIFFERENT category
but players might mistakenly group them together.

EXCELLENT multi-meaning words:
- PITCHER (baseball player / container for liquid)
- BANK (financial institution / river edge / to tilt)
- MATCH (fire starter / contest / to pair)
- CLUB (weapon / organization / playing card suit / nightclub)
- POUND (unit of weight / British currency / to hit / dog shelter)
- SINK (kitchen fixture / to descend / to invest heavily)
- BARK (dog sound / tree covering / sailing ship)
- NAIL (finger part / hardware / to succeed at)

Output exactly 4 multi-meaning words, comma-separated:
Words:"""
        if theme:
            prompt = f"Theme context: {theme}\n\n" + prompt
        return prompt
    
    @staticmethod
    def intentional_overlap_extension(word: str, previous_groups: List[WordGroup]) -> str:
        groups_desc = "\n".join([f"- {g.category}: {', '.join(g.words)}" for g in previous_groups])
        return f"""The word "{word}" has multiple meanings. Create a category using ONE specific meaning.

Previous groups (use DIFFERENT meanings than these):
{groups_desc}

REQUIREMENTS:
1. Pick a DIFFERENT meaning of "{word}" than any used above
2. Create a category that's NOT immediately obvious
3. Include 3 other words that ALSO have alternate meanings (to create more traps)
4. The category should require some thought to identify

GOOD alternate meaning categories:
- If SPRING was used as "season", use it as "things that bounce" or "water sources"
- If BANK was used as "financial", use it as "river edges" or "actions (bank a shot)"
- If CLUB was used as "organization", use it as "weapons" or "card suits"

Format:
Category: [specific name, not generic]
Meaning of {word} used: [which meaning]
Words: word1, word2, word3 (each should have alternate meanings too!)"""
    
    @staticmethod
    def false_group_alternate(word: str, category: str, all_words: List[str]) -> str:
        return f"""The word "{word}" is in category "{category}".

Create a DECEPTIVE alternate category where "{word}" could fit.
The goal is to TRICK players into wrong guesses.

Requirements:
1. The alternate category should seem very plausible for "{word}"
2. Provide 7 words for this category - some should ALSO have alternate meanings
3. Make the category specific enough to be believable

Good deception examples:
- MERCURY: Planet category vs. Element category vs. Queen singer
- TURKEY: Country category vs. Bird category vs. Bowling terms
- AMAZON: Company category vs. River category vs. Mythology

Format:
Deceptive category: [name]
Why {word} fits: [brief explanation]
7 words: word1, word2, word3, word4, word5, word6, word7"""
    
    @staticmethod
    def tree_of_thoughts_categories(theme: Optional[str] = None) -> str:
        return f"""Design 4 CHALLENGING category types for an expert-level Connections puzzle.
{"Theme hint: " + theme if theme else ""}

You MUST include at least 2 of these difficult category types:
1. FILL-IN-BLANK: "_____ X" or "X _____" patterns
2. WORDPLAY: Rhymes, homophones, anagrams, letter patterns
3. HIDDEN PROPERTY: Words spelled only with letters from MONDAY, words with double letters, etc.
4. SLANG/IDIOM: Informal terms for money, approval, failure, etc.
5. POP CULTURE: Specific references requiring knowledge
6. LATERAL THINKING: Unexpected connections (things that are blue, things you spin, etc.)

BAD (too easy): "Types of trees", "Colors", "Animals", "Foods"
GOOD (challenging): "Things you can throw", "___ BALL", "Slang for money", "Words before JACK"

Output exactly 4 challenging category types, one per line:"""
    
    @staticmethod
    def tree_of_thoughts_words(category_type: str, theme: Optional[str] = None) -> str:
        return f"""Generate 8 words for the category: {category_type}
{"Theme context: " + theme if theme else ""}

CRITICAL: Choose words that could ALSO fit other categories!
Each word should ideally have an alternate meaning or belong to multiple groups.

Example: For "Things that are ORANGE":
- CARROT (vegetable), TIGER (animal), PUMPKIN (Halloween), GOLDFISH (pet)
These are good because they could trick players into grouping by their OTHER properties.

Output 8 words, comma-separated:"""
    
    @staticmethod
    def trico_category(words: List[str], primary_view: str) -> str:
        view_descriptions = {
            'sem': "conceptually/semantically connected",
            'pho': "phonetically similar (sound alike)",
            'orth': "orthographically similar (look alike, share letter patterns)"
        }
        view_desc = view_descriptions.get(primary_view, "connected")
        
        return f"""These four words are {view_desc}. Provide a concise category (2-5 words) that captures the connection.

Words: {', '.join(words)}

Category:"""
    
    @staticmethod
    def smart_player_guess(remaining_words: List[str], found_groups: List[List[str]], 
                          mistakes: int, previous_guesses: List[Tuple[List[str], bool]]) -> str:
        found_desc = ""
        if found_groups:
            found_desc = "\nAlready found groups:\n" + "\n".join([f"- {', '.join(g)}" for g in found_groups])
        
        prev_desc = ""
        if previous_guesses:
            wrong_guesses = [g for g, correct in previous_guesses if not correct]
            if wrong_guesses:
                prev_desc = "\nWrong guesses to avoid:\n" + "\n".join([f"- {', '.join(g)}" for g in wrong_guesses[-3:]])
        
        return f"""You are playing NYT Connections. Find 4 words that share a hidden connection.

Remaining words: {', '.join(remaining_words)}
{found_desc}
{prev_desc}
Mistakes remaining: {4 - mistakes}

Think step by step:
1. Look for obvious categories first (same topic, same pattern)
2. Consider wordplay (rhymes, prefixes, suffixes, hidden words)
3. Think about double meanings and alternate definitions
4. Look for fill-in-the-blank patterns (___X or X___)

Choose exactly 4 words that form a group. Output ONLY the 4 words, comma-separated:"""


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def parse_puzzle_response(response: str) -> List[WordGroup]:
    """Parse LLM response into WordGroup objects"""
    groups = []
    lines = response.strip().split('\n')
    
    color_map = {
        'YELLOW': DifficultyColor.YELLOW,
        'GREEN': DifficultyColor.GREEN,
        'BLUE': DifficultyColor.BLUE,
        'PURPLE': DifficultyColor.PURPLE
    }
    
    for line in lines:
        if not line.strip():
            continue
            
        for color_name, color_enum in color_map.items():
            if line.upper().startswith(color_name):
                try:
                    parts = line.split(':', 1)[1].strip()
                    
                    if '-' in parts:
                        category, words_str = parts.split('-', 1)
                    elif '–' in parts:
                        category, words_str = parts.split('–', 1)
                    else:
                        category = f"{color_name} Category"
                        words_str = parts
                    
                    category = category.strip().strip('[]').strip()
                    words = [w.strip().upper() for w in words_str.split(',')]
                    
                    if len(words) == 4:
                        groups.append(WordGroup(
                            words=words,
                            category=category,
                            difficulty=color_enum
                        ))
                except Exception as e:
                    pass
                break
    
    return groups


def parse_puzzle_response_robust(response: str) -> List[WordGroup]:
    """Robust parsing that handles various formats"""
    # Try standard parsing first
    groups = parse_puzzle_response(response)
    if len(groups) >= 4:
        return groups[:4]
    
    # Fallback: look for any comma-separated word groups
    groups = []
    lines = response.strip().split('\n')
    
    color_map = {
        'YELLOW': DifficultyColor.YELLOW,
        'GREEN': DifficultyColor.GREEN,
        'BLUE': DifficultyColor.BLUE,
        'PURPLE': DifficultyColor.PURPLE
    }
    
    seen_words = set()
    current_color_idx = 0
    colors = list(color_map.keys())
    
    for line in lines:
        if not line.strip():
            continue
        
        # Look for comma-separated words
        if ',' in line:
            # Extract potential words
            potential_words = re.findall(r'\b[A-Z][A-Z0-9\']+\b', line.upper())
            if len(potential_words) >= 4:
                words = []
                for w in potential_words:
                    if w not in seen_words and len(words) < 4:
                        words.append(w)
                        seen_words.add(w)
                
                if len(words) == 4:
                    # Determine color
                    color = DifficultyColor.YELLOW
                    for color_name, color_enum in color_map.items():
                        if color_name in line.upper():
                            color = color_enum
                            break
                    
                    # Extract category if present
                    category = f"Group {len(groups) + 1}"
                    if ':' in line:
                        cat_part = line.split(':')[0]
                        for color_name in color_map.keys():
                            cat_part = cat_part.upper().replace(color_name, '').strip()
                        if cat_part:
                            category = cat_part.strip('[]').strip()
                    
                    groups.append(WordGroup(
                        words=words,
                        category=category,
                        difficulty=color
                    ))
    
    return groups


def generate_fallback_group(used_words: Set[str] = None, embedder=None, knowledge_base=None) -> WordGroup:
    """
    Generate a fallback group DYNAMICALLY when LLM fails.
    Uses semantic networks and embeddings - minimal hardcoding!
    
    Args:
        used_words: Words already used in the puzzle
        embedder: SentenceTransformer for computing similarities
        knowledge_base: SemanticKnowledgeBase with semantic networks
    """
    if used_words is None:
        used_words = set()
    used_upper = {w.upper() for w in used_words}
    
    # Strategy 1: Use semantic knowledge base networks (genuinely defined categories)
    if knowledge_base is not None:
        networks = knowledge_base.semantic_networks
        categories = list(networks.keys())
        random.shuffle(categories)
        
        for category in categories:
            words = [w.upper() for w in networks[category] if w.upper() not in used_upper]
            if len(words) >= 4:
                # If we have embedder, pick most coherent 4
                if embedder is not None and len(words) > 4:
                    embeddings = embedder.encode(words)
                    sim_matrix = cosine_similarity(embeddings)
                    
                    # Score each word by average similarity to others
                    scores = []
                    for i in range(len(words)):
                        avg_sim = (sim_matrix[i].sum() - 1) / (len(words) - 1)
                        scores.append((words[i], avg_sim, i))
                    
                    scores.sort(key=lambda x: x[1], reverse=True)
                    selected = [s[0] for s in scores[:4]]
                    avg_coherence = np.mean([s[1] for s in scores[:4]])
                else:
                    selected = random.sample(words, 4)
                    avg_coherence = 0.5
                
                return WordGroup(
                    words=selected,
                    category=category.replace('_', ' ').title(),
                    difficulty=DifficultyColor.YELLOW,
                    similarity_score=avg_coherence
                )
    
    # Strategy 2: Generate from embedding space using seed concepts
    if embedder is not None:
        # These are SEED concepts, not full word lists - the embedder finds related words
        seed_concepts = [
            ("Mathematical Constants", ["PI", "PHI", "EULER", "INFINITY"]),
            ("Greek Letters", ["ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON", "OMEGA"]),
            ("Compass Points", ["NORTH", "SOUTH", "EAST", "WEST"]),
            ("Primary Colors", ["RED", "BLUE", "YELLOW"]),
            ("Noble Gases", ["HELIUM", "NEON", "ARGON", "KRYPTON"]),
            ("Planets", ["MARS", "VENUS", "SATURN", "JUPITER", "MERCURY", "NEPTUNE"]),
        ]
        
        random.shuffle(seed_concepts)
        
        for category, seeds in seed_concepts:
            available = [w for w in seeds if w not in used_upper]
            if len(available) >= 4:
                # Use embeddings to verify coherence
                embeddings = embedder.encode(available)
                sim_matrix = cosine_similarity(embeddings)
                
                # Find best 4 by coherence
                if len(available) > 4:
                    best_quartet = None
                    best_score = -1
                    
                    for combo in itertools.combinations(range(len(available)), 4):
                        sub_sim = sim_matrix[np.ix_(combo, combo)]
                        score = (sub_sim.sum() - 4) / 12
                        if score > best_score:
                            best_score = score
                            best_quartet = combo
                    
                    if best_quartet:
                        selected = [available[i] for i in best_quartet]
                        return WordGroup(
                            words=selected,
                            category=category,
                            difficulty=DifficultyColor.YELLOW,
                            similarity_score=best_score
                        )
                else:
                    return WordGroup(
                        words=available[:4],
                        category=category,
                        difficulty=DifficultyColor.YELLOW,
                        similarity_score=0.5
                    )
    
    # Strategy 3: Emergency fallback with minimal fixed list (only used if embedder unavailable)
    emergency_categories = [
        ("Greek Letters", ["ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON", "ZETA"]),
        ("Roman Numerals", ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX"]),
    ]
    
    for category, words in emergency_categories:
        available = [w for w in words if w not in used_upper]
        if len(available) >= 4:
            return WordGroup(
                words=available[:4],
                category=category,
                difficulty=DifficultyColor.YELLOW,
                similarity_score=0.3
            )
    
    # Absolute last resort
    return WordGroup(
        words=["ITEM", "THING", "OBJECT", "PIECE"],
        category="Generic Terms",
        difficulty=DifficultyColor.YELLOW,
        similarity_score=0.2
    )


def calculate_intra_group_similarity(words: List[str], embedder) -> float:
    """Calculate average pairwise similarity within a group"""
    if len(words) < 2:
        return 0.0
    
    embeddings = embedder.encode(words)
    similarities = cosine_similarity(embeddings)
    
    n = len(similarities)
    total_sim = (similarities.sum() - n) / (n * (n - 1))
    return total_sim


def calculate_cross_group_similarity(group1_words: List[str], group2_words: List[str], embedder) -> float:
    """Calculate average similarity between two groups"""
    emb1 = embedder.encode(group1_words)
    emb2 = embedder.encode(group2_words)
    
    cross_sim = cosine_similarity(emb1, emb2)
    return cross_sim.mean()


def is_valid_word(word: str) -> bool:
    """
    Check if a string is a valid puzzle word.
    Rejects sentences, words with numbers, excessive punctuation, etc.
    """
    if not word or not isinstance(word, str):
        return False
    
    word = word.strip()
    
    # Reject empty strings
    if len(word) == 0:
        return False
    
    # Reject very long strings (likely sentences)
    if len(word) > 20:
        return False
    
    # Reject strings with ANY spaces (valid words don't have spaces)
    if ' ' in word:
        return False
    
    # Reject strings with colons (like "Words:" prefix)
    if ':' in word:
        return False
    
    # Reject strings ending with punctuation (sentences)
    if word[-1] in '.!?;':
        return False
    
    # Reject strings starting with quotes or special chars
    if word[0] in '"\'([{':
        return False
    
    # Reject strings with digits (like WORD1, FUSILLI1)
    if any(c.isdigit() for c in word):
        return False
    
    # Reject common sentence starters/phrases
    lower = word.lower()
    bad_patterns = ['refers', 'meaning', 'italian', 'which', 'also', 'type', 
                    'kind', 'example', 'words', 'category', 'group']
    if lower in bad_patterns:
        return False
    
    # Must have at least 2 letters
    letter_count = sum(1 for c in word if c.isalpha())
    if letter_count < 2:
        return False
    
    # Must be primarily letters (allow apostrophes and hyphens)
    valid_chars = sum(1 for c in word if c.isalpha() or c in "-'")
    if valid_chars < len(word) * 0.8:
        return False
    
    return True


def clean_word(word: str) -> str:
    """Clean a word by removing invalid characters and prefixes"""
    if not word:
        return ""
    
    word = word.strip()
    
    # Remove leading numbers with dots/parentheses (e.g., "3. BOWL", "1) WORD", "7.TRUNK")
    # Pattern: digits followed by optional space and punctuation
    leading_num_pattern = re.match(r'^[\d]+[\.\)\:\-\s]+\s*', word)
    if leading_num_pattern:
        word = word[leading_num_pattern.end():]
    
    # Remove common prefixes like "Words:", "Category:", etc.
    prefixes_to_remove = ['words:', 'word:', 'category:', 'three:', 'four:', 
                          'output:', 'answer:', 'result:', 'group:']
    lower = word.lower()
    for prefix in prefixes_to_remove:
        if lower.startswith(prefix):
            word = word[len(prefix):].strip()
            break
    
    # Remove quotes and brackets
    word = word.strip('"\'[](){}')
    
    # Remove trailing punctuation
    while word and word[-1] in '.,;:!?':
        word = word[:-1]
    
    # Remove leading punctuation
    while word and word[0] in '.,;:!?-':
        word = word[1:]
    
    # Remove any trailing numbers (like WORD1 -> WORD)
    while word and word[-1].isdigit():
        word = word[:-1]
    
    # Remove any leading numbers that slipped through
    while word and word[0].isdigit():
        word = word[1:]
    
    # Final cleanup
    word = word.strip()
    
    return word.upper() if word else ""


def extract_valid_words(text: str, existing_words: Set[str] = None) -> List[str]:
    """
    Extract valid words from LLM response text.
    Filters out sentences, explanations, and invalid entries.
    """
    if existing_words is None:
        existing_words = set()
    
    valid_words = []
    
    # First try comma-separated
    if ',' in text:
        candidates = text.split(',')
    else:
        candidates = text.split()
    
    for candidate in candidates:
        cleaned = clean_word(candidate)
        
        if cleaned and is_valid_word(cleaned) and cleaned not in existing_words:
            valid_words.append(cleaned)
            existing_words.add(cleaned)
    
    return valid_words
