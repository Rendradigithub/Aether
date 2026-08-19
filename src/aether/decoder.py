import numpy as np

try:
    from .config import HardConfig
except ImportError:
    from config import HardConfig


class NeuralDecoder:
    def __init__(self, input_dim=HardConfig.NN_INPUT_DIM,
                 hidden1=HardConfig.NN_HIDDEN_1,
                 hidden2=HardConfig.NN_HIDDEN_2,
                 hidden3=HardConfig.NN_HIDDEN_3,
                 output_dim=HardConfig.NN_OUTPUT_DIM):
        self.W1 = np.random.randn(hidden1, input_dim) * np.sqrt(2.0 / input_dim)
        self.b1 = np.zeros(hidden1)
        self.W2 = np.random.randn(hidden2, hidden1) * np.sqrt(2.0 / hidden1)
        self.b2 = np.zeros(hidden2)
        self.W3 = np.random.randn(hidden3, hidden2) * np.sqrt(2.0 / hidden2)
        self.b3 = np.zeros(hidden3)
        self.W4 = np.random.randn(output_dim, hidden3) * np.sqrt(2.0 / hidden3)
        self.b4 = np.zeros(output_dim)
        self.input_dim = input_dim
        self.training_buffer = []
        self.is_trained = False
        self.loss_history = []
        self.best_loss = float('inf')
        self.best_weights = None
        self.current_threshold = HardConfig.NN_SAMPLE_THRESHOLD_INITIAL

    def _params_to_target(self, params):
        patterns = HardConfig.PATTERNS
        pat_idx = patterns.index(params['pattern']) / (len(patterns)-1)
        return np.array([pat_idx, params['symmetry'], params['density'],
                         params['complexity'], params['noise'], params['shape_param']])

    def forward(self, x, cache=False):
        if x.ndim == 1:
            x = x.reshape(1, -1)
        z1 = x @ self.W1.T + self.b1
        a1 = np.tanh(z1)
        z2 = a1 @ self.W2.T + self.b2
        a2 = np.tanh(z2)
        z3 = a2 @ self.W3.T + self.b3
        a3 = np.tanh(z3)
        out = a3 @ self.W4.T + self.b4
        if cache:
            return out, (x, z1, a1, z2, a2, z3, a3)
        return out

    def predict_params(self, stimulus_vec):
        out = self.forward(stimulus_vec)
        if out.ndim == 2:
            out = out[0]
        patterns = HardConfig.PATTERNS
        pattern_idx = int(np.clip(out[0] * (len(patterns)-1), 0, len(patterns)-1))
        pattern = patterns[pattern_idx]
        symmetry = float(np.clip(out[1], 0, 1))
        density = float(np.clip(out[2], 0.05, 0.95))
        complexity = float(np.clip(out[3], 0.1, 0.9))
        noise = float(np.clip(out[4], 0, 0.6))
        shape_param = float(np.clip(out[5], 0, 1))
        return {
            'pattern': pattern,
            'symmetry': symmetry,
            'density': density,
            'complexity': complexity,
            'noise': noise,
            'shape_param': shape_param
        }

    def collect_sample(self, stimulus_vec, generator_params):
        if generator_params.get('pattern') != 'shape':
            return
        target = self._params_to_target(generator_params)
        self.training_buffer.append((stimulus_vec.copy(), target))
        if len(self.training_buffer) > 2000:
            self.training_buffer.pop(0)
        progress = min(1.0, len(self.training_buffer) / 200)
        self.current_threshold = HardConfig.NN_SAMPLE_THRESHOLD_INITIAL + \
            (HardConfig.NN_SAMPLE_THRESHOLD_MAX - HardConfig.NN_SAMPLE_THRESHOLD_INITIAL) * progress

    def train(self, epochs=None, batch_size=None, lr=None):
        if epochs is None:
            epochs = HardConfig.NN_TRAINING_EPOCHS
        if batch_size is None:
            batch_size = HardConfig.NN_BATCH_SIZE
        if lr is None:
            lr = HardConfig.NN_LEARNING_RATE
        if len(self.training_buffer) < batch_size:
            return
        for ep in range(epochs):
            np.random.shuffle(self.training_buffer)
            total_loss = 0.0
            num_batches = 0
            for i in range(0, len(self.training_buffer), batch_size):
                batch = self.training_buffer[i:i+batch_size]
                X = np.array([b[0] for b in batch])
                Y = np.array([b[1] for b in batch])
                out, cache = self.forward(X, cache=True)
                loss = np.mean((out - Y)**2)
                total_loss += loss
                num_batches += 1
                dout = 2 * (out - Y) / batch_size
                x, z1, a1, z2, a2, z3, a3 = cache
                dW4 = dout.T @ a3
                db4 = np.sum(dout, axis=0)
                da3 = dout @ self.W4
                dz3 = da3 * (1 - np.tanh(z3)**2)
                dW3 = dz3.T @ a2
                db3 = np.sum(dz3, axis=0)
                da2 = dz3 @ self.W3
                dz2 = da2 * (1 - np.tanh(z2)**2)
                dW2 = dz2.T @ a1
                db2 = np.sum(dz2, axis=0)
                da1 = dz2 @ self.W2
                dz1 = da1 * (1 - np.tanh(z1)**2)
                dW1 = dz1.T @ x
                db1 = np.sum(dz1, axis=0)
                self.W1 -= lr * dW1; self.b1 -= lr * db1
                self.W2 -= lr * dW2; self.b2 -= lr * db2
                self.W3 -= lr * dW3; self.b3 -= lr * db3
                self.W4 -= lr * dW4; self.b4 -= lr * db4
            avg_loss = total_loss / max(1, num_batches)
            self.loss_history.append(avg_loss)
            if avg_loss < self.best_loss:
                self.best_loss = avg_loss
                self.best_weights = (self.W1.copy(), self.b1.copy(),
                                      self.W2.copy(), self.b2.copy(),
                                      self.W3.copy(), self.b3.copy(),
                                      self.W4.copy(), self.b4.copy())
        self.is_trained = True
        print(f"[Decoder] Trained, loss: {self.loss_history[-1]:.4f}, buffer: {len(self.training_buffer)}")

    def save_weights(self, path):
        if self.best_weights:
            np.savez(path,
                     W1=self.best_weights[0], b1=self.best_weights[1],
                     W2=self.best_weights[2], b2=self.best_weights[3],
                     W3=self.best_weights[4], b3=self.best_weights[5],
                     W4=self.best_weights[6], b4=self.best_weights[7])
        else:
            np.savez(path,
                     W1=self.W1, b1=self.b1,
                     W2=self.W2, b2=self.b2,
                     W3=self.W3, b3=self.b3,
                     W4=self.W4, b4=self.b4)

    def load_weights(self, path):
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
        return True
