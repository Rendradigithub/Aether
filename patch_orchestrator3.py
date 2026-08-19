import re

with open("src/aether/orchestrator.py", "r") as f:
    content = f.read()

old_novelty = "novelty = self.memory.novelty(sig_art) if hasattr(self.memory, 'novelty') else 0.5"
new_novelty = """proj_sig_art = DimensionalityProjector.project(sig_art, self.representation_dim or HardConfig.VECTOR_DIM)
        novelty = self.memory.novelty(proj_sig_art) if hasattr(self.memory, 'novelty') else 0.5"""

if old_novelty in content:
    content = content.replace(old_novelty, new_novelty)
    with open("src/aether/orchestrator.py", "w") as f:
        f.write(content)
    print("Patched orchestrator.py")
else:
    print("Old novelty line not found in orchestrator.py")

with open("archive/versions/aether.0.20.0.py", "r") as f:
    content2 = f.read()

if old_novelty in content2:
    content2 = content2.replace(old_novelty, new_novelty)
    with open("archive/versions/aether.0.20.0.py", "w") as f:
        f.write(content2)
    print("Patched archive orchestrator")
else:
    print("Old novelty line not found in archive")
