# character_comparison.py
# Visualize and compare character trait embeddings side by side

import matplotlib.pyplot as plt
import numpy as np
from latent_rpg_engine import encode_character, get_cached_embedding, normalize, dot, PROBES

def get_all_probe_similarities(char_vec, probe_names):
    """Get similarity scores for all probes, not just top N"""
    scores = []
    char_norm = normalize(char_vec)
    
    for probe in probe_names:
        # Get embedding for the probe name itself
        probe_vec = get_cached_embedding(probe, "PROBE")
        probe_norm = normalize(probe_vec)
        similarity = dot(char_norm, probe_norm)
        scores.append(similarity)
    
    return scores

def visualize_character_comparison():
    """Create a side-by-side bar chart comparing character traits"""
    
    # Character descriptions (same as in demo)
    az_desc = "A stoic wanderer who relies on cunning and speed; nimble, focused, with a quiet presence."
    br_desc = "A boisterous sellsword of great strength and heart; tough, powerful, and tireless with poor subtlety."
    
    print("Encoding characters and computing trait similarities...")
    
    # Encode characters
    azrael = encode_character(az_desc)
    brom = encode_character(br_desc)
    
    # Get all probe similarities
    azrael_scores = get_all_probe_similarities(azrael['vec'], PROBES)
    brom_scores = get_all_probe_similarities(brom['vec'], PROBES)
    
    # Create the plot
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # Set up bar positions
    x = np.arange(len(PROBES))
    width = 0.35
    
    # Create bars
    bars1 = ax.bar(x - width/2, azrael_scores, width, label='Azrael (Cunning Wanderer)', 
                   color='steelblue', alpha=0.8)
    bars2 = ax.bar(x + width/2, brom_scores, width, label='Brom (Strong Sellsword)', 
                   color='crimson', alpha=0.8)
    
    # Customize the plot
    ax.set_xlabel('Character Traits', fontsize=12, fontweight='bold')
    ax.set_ylabel('Semantic Similarity Score', fontsize=12, fontweight='bold')
    ax.set_title('Character Trait Comparison: Semantic Embedding Analysis', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(PROBES, rotation=45, ha='right')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars for better readability
    def add_value_labels(bars):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.2f}',
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 3),  # 3 points vertical offset
                       textcoords="offset points",
                       ha='center', va='bottom',
                       fontsize=8, rotation=90)
    
    # Add labels to bars (commented out as it might be too cluttered with 24 traits)
    # add_value_labels(bars1)
    # add_value_labels(bars2)
    
    # Adjust layout to prevent label cutoff
    plt.tight_layout()
    
    # Show some stats
    print("\n=== Character Trait Analysis ===")
    print(f"Azrael's strongest traits:")
    az_top = sorted(zip(PROBES, azrael_scores), key=lambda x: x[1], reverse=True)[:5]
    for trait, score in az_top:
        print(f"  {trait}: {score:.3f}")
    
    print(f"\nBrom's strongest traits:")
    br_top = sorted(zip(PROBES, brom_scores), key=lambda x: x[1], reverse=True)[:5]
    for trait, score in br_top:
        print(f"  {trait}: {score:.3f}")
    
    print(f"\nBiggest differences (Brom - Azrael):")
    differences = [(PROBES[i], brom_scores[i] - azrael_scores[i]) for i in range(len(PROBES))]
    differences.sort(key=lambda x: abs(x[1]), reverse=True)
    for trait, diff in differences[:5]:
        sign = "higher" if diff > 0 else "lower"
        print(f"  {trait}: Brom {diff:+.3f} ({sign} than Azrael)")
    
    # Display the plot
    plt.show()

if __name__ == "__main__":
    visualize_character_comparison()
