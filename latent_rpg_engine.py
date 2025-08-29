# latent_rpg_engine.py
# Core embedding and resolution engine for the latent-stat RPG system

import math
import random
import hashlib
import warnings
import os
from typing import List, Dict, Tuple, Optional
from fastembed import TextEmbedding

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# ====== CONSTANTS ======
D = 384  # FastEmbed's BAAI/bge-small-en-v1.5 dimension
PROBES = [
    "agility","balance","grace","speed","precision","endurance","toughness","power",
    "stealth","cunning","deception","perception","insight","focus","will","discipline",
    "empathy","presence","charm","wit","learning","memory","craft","luck"
]
K = len(PROBES)

PROBE_KEYWORDS = {
    "agility": ["nimble","agile","quick","spry"],
    "balance": ["balance","acrobatic","tightrope","poise"],
    "grace": ["grace","elegant","fluid","dance"],
    "speed": ["fast","speed","swift","dash","sprint"],
    "precision": ["precise","surgical","aim","accuracy","sniper"],
    "endurance": ["endure","stamina","long","marathon","tireless"],
    "toughness": ["tough","sturdy","grit","rugged","hardy"],
    "power": ["strong","power","mighty","heave","lift","strike"],
    "stealth": ["stealth","sneak","hide","shadow","quiet"],
    "cunning": ["cunning","trick","scheme","guile","fox"],
    "deception": ["deceive","lie","mask","bluff","con"],
    "perception": ["notice","spot","perceive","listen","watch"],
    "insight": ["insight","intuit","read","understand","motives"],
    "focus": ["focus","concentrate","meditate","calm"],
    "will": ["will","resolve","courage","fearless"],
    "discipline": ["discipline","trained","rigorous","ascetic"],
    "empathy": ["empathy","compassion","comfort","soothe"],
    "presence": ["presence","aura","authority","command"],
    "charm": ["charm","flirt","smile","pleasant"],
    "wit": ["wit","quip","banter","clever"],
    "learning": ["study","learn","book","scholar"],
    "memory": ["memory","recall","remember"],
    "craft": ["craft","forge","carve","tinker","artisan"],
    "luck": ["luck","fortune","chance","serendipity"]
}

# ====== GLOBAL STATE ======
EMBEDDING_MODEL = None
EMBEDDING_CACHE = {}

# ====== UTILITY FUNCTIONS ======
def dot(a: List[float], b: List[float]) -> float:
    return sum(x*y for x, y in zip(a, b))

def norm(a: List[float]) -> float:
    return math.sqrt(sum(x*x for x in a)) + 1e-12

def normalize(a: List[float]) -> List[float]:
    n = norm(a)
    return [x / n for x in a]

def add(a: List[float], b: List[float]) -> List[float]:
    return [x + y for x, y in zip(a, b)]

def scal(a: List[float], s: float) -> List[float]:
    return [x * s for x in a]

def zeros(d: int) -> List[float]:
    return [0.0]*d

def text_seed(s: str) -> int:
    h = hashlib.sha256(s.strip().lower().encode("utf-8")).hexdigest()
    return int(h[:16], 16)

# ====== EMBEDDING FUNCTIONS ======
def get_embedding_model():
    """Get or initialize the global FastEmbed model"""
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        EMBEDDING_MODEL = TextEmbedding()  # defaults to BAAI/bge-small-en-v1.5
    return EMBEDDING_MODEL

def get_cached_embedding(text: str, prefix: str = "") -> List[float]:
    """Get embedding for text with caching"""
    cache_key = f"{prefix}::{text.strip().lower()}"
    if cache_key not in EMBEDDING_CACHE:
        model = get_embedding_model()
        # FastEmbed returns a generator, convert to list and get first (and only) embedding
        embedding = list(model.embed([text]))[0]
        # Convert numpy array to list for consistency with rest of code
        EMBEDDING_CACHE[cache_key] = embedding.tolist()
    return EMBEDDING_CACHE[cache_key]

def score_probe_from_text(text: str, probe: str) -> float:
    """Score how much a text relates to a specific probe using keyword matching + jitter"""
    tokens = text.lower()
    base = sum(tokens.count(w) for w in PROBE_KEYWORDS.get(probe, []))
    s = f"{probe}::{text}"
    rng = random.Random(text_seed(s))
    jitter = rng.uniform(-0.2, 0.2)
    return base + jitter

# ====== CHARACTER & TASK ENCODING ======
def encode_character(description: str):
    """Tier B: Use FastEmbed for character encoding while keeping probe scores for interpretability"""
    # Get the main embedding vector from FastEmbed (this is now the core representation)
    vec = get_cached_embedding(description, "CHARACTER")
    vec = normalize(vec)
    
    # Still compute probe scores for interpretability/display purposes
    scores = [score_probe_from_text(description, p) for p in PROBES]
    
    # Generate a consistent seed for any remaining randomness
    seed = text_seed(description)
    
    return {"seed": seed, "scores": scores, "vec": vec}

def encode_task_axis(task_text: str):
    """Tier B: Use FastEmbed for task encoding while keeping probe scores for interpretability"""
    # Get the main embedding vector from FastEmbed (this is now the core representation)
    axis = get_cached_embedding(task_text, "TASK")
    axis = normalize(axis)
    
    # Still compute probe scores for interpretability/display purposes
    scores = [score_probe_from_text(task_text, p) for p in PROBES]
    
    # Generate a consistent seed for any remaining randomness
    seed = text_seed("TASK::" + task_text)
    
    return {"seed": seed, "scores": scores, "axis": axis}

# ====== RESOLUTION & ANALYSIS ======
def resolve_check(char_vec, task_axis,
                  alpha: float = 2.0, beta: float = 0.0, noise: float = 0.5,
                  advantage: int = 0, assist_vecs = None, rng: Optional[random.Random] = None):
    """Core resolution function - unchanged from original"""
    if rng is None:
        rng = random.Random(1337)
    c = normalize(char_vec)
    t = normalize(task_axis)
    if assist_vecs:
        helper = normalize([sum(v[i] for v in assist_vecs)/len(assist_vecs) for i in range(D)])
        c = normalize([0.9*c[i] + 0.1*helper[i] for i in range(D)])
    draws = 1 + abs(advantage)
    scores = []
    for _ in range(draws):
        s = alpha * dot(c, t) + beta + rng.gauss(0.0, noise)
        scores.append(s)
    if advantage > 0:
        s_final = max(scores)
    elif advantage < 0:
        s_final = min(scores)
    else:
        s_final = scores[0]
    p = 1.0 / (1.0 + math.exp(-s_final))
    roll = rng.random()
    return {"logit": s_final, "p": p, "success": roll < p, "roll": roll}

def top_probes_for_character(char_vec, top_n: int = 5):
    """Tier B: Use FastEmbed to get probe embeddings for similarity comparison"""
    scores = []
    char_norm = normalize(char_vec)
    
    for probe in PROBES:
        # Get embedding for the probe name itself
        probe_vec = get_cached_embedding(probe, "PROBE")
        probe_norm = normalize(probe_vec)
        sc = dot(char_norm, probe_norm)
        scores.append((probe, sc))
    
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_n]

def task_probe_weights(task_scores, top_n: int = 5):
    """Show which probes a task calls on most - unchanged from original"""
    pairs = list(zip(PROBES, task_scores))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:top_n]

# ====== CACHE MANAGEMENT ======
def clear_embedding_cache():
    """Clear the embedding cache (useful for testing or memory management)"""
    global EMBEDDING_CACHE
    EMBEDDING_CACHE = {}

def get_cache_info():
    """Get information about the current embedding cache"""
    return {
        "cache_size": len(EMBEDDING_CACHE),
        "cached_keys": list(EMBEDDING_CACHE.keys())
    }
