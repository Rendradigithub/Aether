import math
import numpy as np

class ArtEmbedder:
    @staticmethod
    def embed(art):
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines: return np.zeros(8, dtype=np.float32)
        h,w = len(lines), max(len(l) for l in lines)
        padded = [l.ljust(w) for l in lines]
        total = h*w
        non = sum(c!=' ' for line in padded for c in line)
        den = non/total
        h_sym=0; cnt=0
        for line in padded:
            s=line.rstrip()
            if len(s)>2:
                mid=len(s)//2; left=s[:mid]; right=s[mid:][::-1]
                n=min(len(left),len(right))
                if n>0:
                    m=sum(1 for i in range(n) if left[i]==right[i] and left[i]!=' ')
                    h_sym+=m/n; cnt+=1
        sym = h_sym/max(1,cnt)
        allc = [c for line in padded for c in line if c!=' ']
        var = np.std([ord(c) for c in allc])/128.0 if allc else 0.0
        cx, cy = w/2, h/2
        max_r = min(w,h)/2
        inner = 0; outer = 0
        for y in range(h):
            for x in range(w):
                if padded[y][x] != ' ':
                    dist = math.sqrt((x-cx)**2 + (y-cy)**2)
                    if dist < max_r*0.6: inner += 1
                    elif dist > max_r*0.8: outer += 1
        circ = ((inner - outer) / non + 1)/2 if non>0 else 0.5
        vec = np.array([den, sym, var, circ], dtype=np.float32)
        vec = np.pad(vec, (0, 8-len(vec)))
        return vec/(np.linalg.norm(vec)+1e-8)

class DimensionalityProjector:
    """Provides semantic-preserving or deterministic dimension adapters for Aether representations."""
    @staticmethod
    def project(vector, target_dim):
        """Projects a 1D vector to the target dimension using linear interpolation."""
        vector = np.asarray(vector, dtype=np.float64)
        if len(vector) == target_dim:
            return vector
        
        # Simple interpolation preserves spatial/sequence structure (like radial bins)
        x = np.linspace(0, 1, len(vector))
        x_new = np.linspace(0, 1, target_dim)
        projected = np.interp(x_new, x, vector)
        
        # Normalize to prevent unbounded magnitude growth during continuous loops
        norm = np.linalg.norm(projected)
        if norm > 1e-8:
            projected = projected / norm
            
        return projected
