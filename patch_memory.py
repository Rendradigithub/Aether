import re

old_novelty = """    def novelty(self, vec):
        if not self.vectors:
            return 1.0
        norm_vec = np.linalg.norm(vec)
        if norm_vec < 1e-8:
            return 0.0
        sims = [np.dot(vec, v) / (norm_vec * np.linalg.norm(v) + 1e-8) for v in self.vectors[-10:]]
        return 1.0 - max(sims) if sims else 1.0"""

new_novelty = """    def novelty(self, vec):
        if not self.vectors:
            return 1.0
        norm_vec = np.linalg.norm(vec)
        if norm_vec < 1e-8:
            return 0.0
        
        sims = []
        for v in self.vectors[-10:]:
            norm_v = np.linalg.norm(v)
            if norm_v < 1e-8:
                continue
            if len(vec) != len(v):
                x_vec = np.linspace(0, 1, len(vec))
                x_v = np.linspace(0, 1, len(v))
                safe_vec = np.interp(x_v, x_vec, vec)
                norm_safe_vec = np.linalg.norm(safe_vec)
                if norm_safe_vec < 1e-8:
                    continue
                sim = np.dot(safe_vec, v) / (norm_safe_vec * norm_v + 1e-8)
            else:
                sim = np.dot(vec, v) / (norm_vec * norm_v + 1e-8)
            sims.append(sim)
            
        return 1.0 - max(sims) if sims else 1.0"""

for filename in ["src/aether/memory.py", "archive/versions/aether.0.20.0.py"]:
    with open(filename, "r") as f:
        content = f.read()
    if old_novelty in content:
        content = content.replace(old_novelty, new_novelty)
        with open(filename, "w") as f:
            f.write(content)
        print(f"Patched {filename}")
    else:
        print(f"Old novelty line not found in {filename}")
