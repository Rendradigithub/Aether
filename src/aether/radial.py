import math

import numpy as np

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[Warning] Pillow not installed. Install with: pip install Pillow")

try:
    from .shape_generator import ShapeAwareGenerator
except ImportError:
    from shape_generator import ShapeAwareGenerator


class RadialSignature:
    @staticmethod
    def from_image(image_path, size=64, num_rays=36):
        if not PIL_AVAILABLE:
            raise ImportError("Pillow required")
        img = Image.open(image_path).convert('L')
        img = img.resize((size, size), Image.Resampling.LANCZOS)
        arr = np.array(img, dtype=np.float32) / 255.0
        gx = np.abs(np.diff(arr, axis=1, append=arr[:,-1:]))
        gy = np.abs(np.diff(arr, axis=0, append=arr[-1:,:]))
        edge = np.maximum(gx, gy)
        edge = (edge > 0.2).astype(np.float32)
        cx, cy = size//2, size//2
        max_r = size
        signature = []
        for i in range(num_rays):
            angle = 2 * math.pi * i / num_rays
            dx = math.cos(angle)
            dy = math.sin(angle)
            found = False
            for r in range(1, max_r):
                x = int(cx + r * dx)
                y = int(cy + r * dy)
                if x < 0 or x >= size or y < 0 or y >= size:
                    signature.append(r)
                    found = True
                    break
                if edge[y, x] > 0:
                    signature.append(r)
                    found = True
                    break
            if not found:
                signature.append(max_r)
        signature = np.array(signature, dtype=np.float32) / max_r
        return signature

    @staticmethod
    def from_ascii_art(art, num_rays=36, contour_only=True):
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines:
            return np.zeros(num_rays)
        h, w = len(lines), max(len(l) for l in lines)
        grid = np.zeros((h, w), dtype=np.float32)
        for y, line in enumerate(lines):
            for x, ch in enumerate(line.ljust(w)):
                if ch != ' ':
                    grid[y, x] = 1.0
        if contour_only:
            gx = np.abs(np.diff(grid, axis=1, append=grid[:,-1:]))
            gy = np.abs(np.diff(grid, axis=0, append=grid[-1:,:]))
            edge = np.maximum(gx, gy)
            edge = (edge > 0).astype(np.float32)
        else:
            edge = grid
        cx, cy = w/2, h/2
        max_r = max(h, w)
        signature = []
        for i in range(num_rays):
            angle = 2 * math.pi * i / num_rays
            dx = math.cos(angle)
            dy = math.sin(angle)
            found = False
            for r in range(1, max_r):
                x = int(cx + r * dx)
                y = int(cy + r * dy)
                if x < 0 or x >= w or y < 0 or y >= h:
                    signature.append(r)
                    found = True
                    break
                if edge[y, x] > 0:
                    signature.append(r)
                    found = True
                    break
            if not found:
                signature.append(max_r)
        signature = np.array(signature, dtype=np.float32) / max_r
        return signature

    @staticmethod
    def cross_correlation(sig1, sig2):
        if np.std(sig1) == 0 or np.std(sig2) == 0:
            return 0.5
        corr = np.corrcoef(sig1, sig2)[0,1]
        return max(0.0, min(1.0, (corr + 1) / 2))

    @staticmethod
    def ideal_contour_from_params(shape_param, symmetry, density, noise, w=52, h=18, num_rays=36):
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        cx, cy = w//2, h//2
        size = min(w,h)//4
        if shape_param < 0.33:
            r = int(size * (0.5 + shape_param*1.5))
            ShapeAwareGenerator.draw_circle(grid, cx, cy, r, char='█')
        elif shape_param < 0.66:
            sz = int(size * (0.5 + (shape_param-0.33)*3))
            ShapeAwareGenerator.draw_square(grid, cx, cy, sz, char='█')
        else:
            sz = int(size * (0.5 + (shape_param-0.66)*3))
            ShapeAwareGenerator.draw_triangle(grid, cx, cy, sz, char='█')
        binary = [[1 if c != ' ' else 0 for c in row] for row in grid]
        arr = np.array(binary, dtype=np.float32)
        gx = np.abs(np.diff(arr, axis=1, append=arr[:,-1:]))
        gy = np.abs(np.diff(arr, axis=0, append=arr[-1:,:]))
        edge = np.maximum(gx, gy)
        edge = (edge > 0).astype(np.float32)
        max_r = max(h,w)
        signature = []
        for i in range(num_rays):
            angle = 2 * math.pi * i / num_rays
            dx = math.cos(angle)
            dy = math.sin(angle)
            found = False
            for r in range(1, max_r):
                x = int(cx + r * dx)
                y = int(cy + r * dy)
                if x < 0 or x >= w or y < 0 or y >= h:
                    signature.append(r)
                    found = True
                    break
                if edge[y, x] > 0:
                    signature.append(r)
                    found = True
                    break
            if not found:
                signature.append(max_r)
        signature = np.array(signature, dtype=np.float32) / max_r
        return signature

    @staticmethod
    def contour_consistency(sig_art, ideal_sig):
        return RadialSignature.cross_correlation(sig_art, ideal_sig)


class AreaCoherence:
    @staticmethod
    def largest_connected_component_ratio(art):
        lines = [l.rstrip('\n') for l in art.split('\n') if l.strip()]
        if not lines:
            return 0.0
        h, w = len(lines), max(len(l) for l in lines)
        grid = [[1 if ch != ' ' else 0 for ch in line.ljust(w)] for line in lines]
        visited = [[False]*w for _ in range(h)]
        def dfs(y, x):
            stack = [(y, x)]
            count = 0
            while stack:
                cy, cx = stack.pop()
                if cy<0 or cy>=h or cx<0 or cx>=w or visited[cy][cx] or grid[cy][cx]==0:
                    continue
                visited[cy][cx] = True
                count += 1
                stack.extend([(cy+1,cx), (cy-1,cx), (cy,cx+1), (cy,cx-1)])
            return count
        max_comp = 0
        total = 0
        for y in range(h):
            for x in range(w):
                if grid[y][x] == 1:
                    total += 1
                    if not visited[y][x]:
                        comp = dfs(y, x)
                        if comp > max_comp:
                            max_comp = comp
        if total == 0:
            return 0.0
        return max_comp / total
