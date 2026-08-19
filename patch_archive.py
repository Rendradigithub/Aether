with open("archive/versions/aether.0.20.0.py", "r") as f:
    content = f.read()

projector_code = """
class DimensionalityProjector:
    @staticmethod
    def project(vector, target_dim):
        import numpy as np
        vector = np.asarray(vector, dtype=np.float64)
        if len(vector) == target_dim:
            return vector
        x = np.linspace(0, 1, len(vector))
        x_new = np.linspace(0, 1, target_dim)
        projected = np.interp(x_new, x, vector)
        norm = np.linalg.norm(projected)
        if norm > 1e-8:
            projected = projected / norm
        return projected
"""

if "class DimensionalityProjector" not in content:
    content = projector_code + "\n" + content
    with open("archive/versions/aether.0.20.0.py", "w") as f:
        f.write(content)
    print("Injected DimensionalityProjector into archive")
