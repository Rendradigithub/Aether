import re

with open("archive/versions/aether.0.20.0.py", "r") as f:
    content = f.read()

# Replace self.representation_dim with getattr(self, 'representation_dim', None)
content = content.replace(
    "DimensionalityProjector.project(sig_art, self.representation_dim or HardConfig.VECTOR_DIM)",
    "DimensionalityProjector.project(sig_art, getattr(self, 'representation_dim', None) or HardConfig.VECTOR_DIM)"
)
content = content.replace(
    "DimensionalityProjector.project(next_sig, self.representation_dim or HardConfig.VECTOR_DIM)",
    "DimensionalityProjector.project(next_sig, getattr(self, 'representation_dim', None) or HardConfig.VECTOR_DIM)"
)

with open("archive/versions/aether.0.20.0.py", "w") as f:
    f.write(content)
print("Patched archive getattr for representation_dim")
