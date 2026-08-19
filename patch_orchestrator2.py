import re

with open("src/aether/orchestrator.py", "r") as f:
    content = f.read()

# 1. Import
if "DimensionalityProjector" not in content:
    content = content.replace("from .world_model import PredictiveWorldModel",
                              "from .world_model import PredictiveWorldModel\nfrom .embedding import DimensionalityProjector")

# 2. _compute_reward
old_reward = """        sig_art = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
        if self.stimulus_radial is not None:
            radial_sim = RadialSignature.cross_correlation(self.stimulus_radial, sig_art)
        else:
            radial_sim = 0.5"""

new_reward = """        sig_art = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
        if self.stimulus_radial is not None:
            if len(self.stimulus_radial) == len(sig_art):
                radial_sim = RadialSignature.cross_correlation(self.stimulus_radial, sig_art)
            else:
                proj_sig = DimensionalityProjector.project(sig_art, len(self.stimulus_radial))
                cos_sim = np.dot(self.stimulus_radial, proj_sig) / (np.linalg.norm(self.stimulus_radial) * np.linalg.norm(proj_sig) + 1e-8)
                radial_sim = max(0.0, float(cos_sim + 1.0) / 2.0)
        else:
            radial_sim = 0.5"""

content = content.replace(old_reward, new_reward)

# 3. next_sig projections
# We will do a generic replacement for next_sig generation.
content = content.replace(
    "next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)",
    "next_sig = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)\n            next_sig = DimensionalityProjector.project(next_sig, self.representation_dim or HardConfig.VECTOR_DIM)"
)

# 4. In _compute_reward, we also replaced next_sig ... wait! 
# sig_art = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)
# The above replace will change it too if the indentation matches, but the indentation in _compute_reward is 8 spaces!
# Let's fix the extra indentation that might have been added to _compute_reward.
content = content.replace(
    "        sig_art = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)\n            next_sig = DimensionalityProjector.project(next_sig, self.representation_dim or HardConfig.VECTOR_DIM)",
    "        sig_art = RadialSignature.from_ascii_art(art, num_rays=36, contour_only=True)"
)

with open("src/aether/orchestrator.py", "w") as f:
    f.write(content)
print("Patch 2 applied.")
