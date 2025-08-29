# latent_rpg_mvp.py
# Demo for the latent-stat RPG system using real embeddings

import random
from latent_rpg_engine import encode_character, encode_task_axis, resolve_check, top_probes_for_character, task_probe_weights

def demo():
    print("=== Latent-Stat RPG MVP Demo ===\n")
    
    # Character descriptions
    az_desc = "A stoic wanderer who relies on cunning and speed; nimble, focused, with a quiet presence."
    br_desc = "A boisterous sellsword of great strength and heart; tough, powerful, and tireless with poor subtlety."
    
    # Encode characters using the engine
    az = encode_character(az_desc)
    br = encode_character(br_desc)
    
    # Task descriptions
    t1_text = "Cross a swaying tightrope over a deep chasm as gusts buffet you from the side."
    t2_text = "Convince a wary guard captain that you belong inside the restricted keep."
    t3_text = "Force open a rusted iron gate wedged by fallen stones."
    
    # Encode tasks using the engine
    t1 = encode_task_axis(t1_text)
    t2 = encode_task_axis(t2_text)
    t3 = encode_task_axis(t3_text)
    
    # Set up randomness
    rng = random.Random(20250829)

    def run(char, name, task, task_text):
        res = resolve_check(char['vec'], task['axis'], alpha=2.0, beta=0.0, noise=0.5, rng=rng)
        c_top = top_probes_for_character(char['vec'])
        t_top = task_probe_weights(task['scores'])
        print(f"{name} attempts: {task_text}")
        print(f"  chance = {res['p']*100:.1f}% -> {'SUCCESS' if res['success'] else 'fail'} (roll {res['roll']:.3f})")
        print("  your top traits: " + ", ".join([f"{p}({v:+.2f})" for p,v in c_top]))
        print("  task calls on: " + ", ".join([f"{p}:{v:.2f}" for p,v in t_top]))
        print()

    # Run all test scenarios
    run(az, "Azrael", t1, t1_text)
    run(az, "Azrael", t2, t2_text)
    run(az, "Azrael", t3, t3_text)
    run(br, "Brom", t1, t1_text)
    run(br, "Brom", t2, t2_text)
    run(br, "Brom", t3, t3_text)

if __name__ == "__main__":
    demo()
