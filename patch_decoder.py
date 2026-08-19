import re

# Patch src/aether/decoder.py
with open("src/aether/decoder.py", "r") as f:
    content = f.read()

old_load = """    def load_weights(self, path):
        data = np.load(path)
        self.W1 = data['W1']; self.b1 = data['b1']
        self.W2 = data['W2']; self.b2 = data['b2']
        self.W3 = data['W3']; self.b3 = data['b3']
        self.W4 = data['W4']; self.b4 = data['b4']
        self.best_weights = [self.W1.copy(), self.b1.copy(),
                             self.W2.copy(), self.b2.copy(),
                             self.W3.copy(), self.b3.copy(),
                             self.W4.copy(), self.b4.copy()]
        self.is_trained = True
        self.current_threshold = 0.15
        print(f"[Decoder] Weights loaded from {path}")"""

new_load = """    def load_weights(self, path):
        data = np.load(path)
        w1_loaded = data['W1']
        if w1_loaded.shape[1] != self.input_dim:
            print(f"[Decoder] Incompatible weights dimension (found {w1_loaded.shape[1]}, expected {self.input_dim}). Ignoring saved weights.")
            return False

        self.W1 = w1_loaded; self.b1 = data['b1']
        self.W2 = data['W2']; self.b2 = data['b2']
        self.W3 = data['W3']; self.b3 = data['b3']
        self.W4 = data['W4']; self.b4 = data['b4']
        self.best_weights = [self.W1.copy(), self.b1.copy(),
                             self.W2.copy(), self.b2.copy(),
                             self.W3.copy(), self.b3.copy(),
                             self.W4.copy(), self.b4.copy()]
        self.is_trained = True
        self.current_threshold = 0.15
        print(f"[Decoder] Weights loaded from {path}")
        return True"""

content = content.replace(old_load, new_load)
with open("src/aether/decoder.py", "w") as f:
    f.write(content)

# Patch archive/versions/aether.0.20.0.py decoder too
with open("archive/versions/aether.0.20.0.py", "r") as f:
    archive_content = f.read()
if old_load in archive_content:
    archive_content = archive_content.replace(old_load, new_load)
    with open("archive/versions/aether.0.20.0.py", "w") as f:
        f.write(archive_content)
    print("Archive patched.")

print("Decoder patched.")
