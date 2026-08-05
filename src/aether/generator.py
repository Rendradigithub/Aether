import math
import random

try:
    from .config import HardConfig
    from .shape_generator import ShapeAwareGenerator
except ImportError:
    from config import HardConfig
    from shape_generator import ShapeAwareGenerator


class Generator:
    PATTERNS = HardConfig.PATTERNS
    def __init__(self):
        self.params = {
            'pattern': random.choice(self.PATTERNS),
            'symmetry': random.uniform(0.3,0.8),
            'density': random.uniform(0.2,0.6),
            'complexity': random.uniform(0.3,0.7),
            'noise': random.uniform(0.1,0.4),
            'shape_param': random.uniform(0,1)
        }
    def generate(self, blocked):
        if self.params['pattern'] in blocked:
            raise ValueError(f"Pattern '{self.params['pattern']}' blocked")
        if self.params['pattern'] == 'shape':
            art = ShapeAwareGenerator.generate_shape(
                self.params['shape_param'], self.params['symmetry'],
                self.params['density'], self.params['noise']
            )
            return art, 'shape'
        w, h = 52, 18
        grid = [[' ']*w for _ in range(h)]
        td = max(0.1, min(0.9, self.params['density']+random.uniform(-0.1,0.1)))
        ts = max(0.0, min(1.0, self.params['symmetry']+random.uniform(-0.1,0.1)))
        tn = max(0.0, min(0.6, self.params['noise']+random.uniform(-0.1,0.15)))
        pat = self.params['pattern']
        if pat == 'wave':
            fx = random.uniform(0.1,0.6); fy = random.uniform(0.1,0.5)
            for y in range(h):
                for x in range(w):
                    v = math.sin(x*fx)*math.cos(y*fy)+math.sin(x*0.8)*0.3+math.cos(y*0.6)*0.3+random.uniform(-0.1,0.1)*tn
                    if (v+1)/2 > 1 - td: grid[y][x] = random.choice('░▒▓█')
        elif pat == 'fractal':
            depth = max(1, int(self.params['complexity']*4)+random.randint(0,2))
            self._draw_fractal(grid, w//2, h//2, min(w,h)//6, depth, tn)
        elif pat == 'cellular':
            grid = self._cellular(w, h, td, tn)
        elif pat == 'lsystem':
            grid = self._lsystem(w, h, tn)
        else:
            for y in range(h):
                for x in range(w):
                    v = math.sin(x*0.3)*math.cos(y*0.3)+random.uniform(-0.1,0.1)*tn
                    if (v+1)/2 > 1 - td: grid[y][x] = random.choice('░▒▓█')
        if random.random() < ts:
            for y in range(h):
                for x in range(w//2):
                    if grid[y][x]!=' ': grid[y][w-1-x]=grid[y][x]
                    elif grid[y][w-1-x]!=' ': grid[y][x]=grid[y][w-1-x]
        self._adjust(grid, td)
        if tn>0:
            for y in range(h):
                for x in range(w):
                    if random.random()<tn*0.4:
                        if grid[y][x]==' ': grid[y][x]=random.choice(' .:oO0@')
                        elif random.random()<0.5: grid[y][x]=' '
        return '\n'.join(''.join(row) for row in grid), pat

    def _draw_fractal(self, grid, x, y, s, d, n):
        if d<=0 or s<1: return
        for i in range(-s,s+1):
            if 0<=x+i<len(grid[0]) and 0<=y<len(grid) and random.random()>n: grid[y][x+i]='█'
            if 0<=x<len(grid[0]) and 0<=y+i<len(grid) and random.random()>n: grid[y+i][x]='█'
        self._draw_fractal(grid, x+s+1, y, s//2, d-1, n)
        self._draw_fractal(grid, x-s-1, y, s//2, d-1, n)
        self._draw_fractal(grid, x, y+s+1, s//2, d-1, n)
        self._draw_fractal(grid, x, y-s-1, s//2, d-1, n)
    def _cellular(self, w, h, den, n):
        grid = [[1 if random.random()<den else 0 for _ in range(w)] for _ in range(h)]
        for _ in range(3+int(n*3)):
            new = [[0]*w for _ in range(h)]
            for y in range(h):
                for x in range(w):
                    neigh = sum(grid[(y+dy)%h][(x+dx)%w] for dy in(-1,0,1) for dx in(-1,0,1) if not(dy==0 and dx==0))
                    new[y][x] = 1 if (grid[y][x] and neigh in(2,3)) or (not grid[y][x] and neigh==3) else 0
            grid = new
        return [[' ' if not c else random.choice('░▒▓') for c in row] for row in grid]
    def _lsystem(self, w, h, n):
        seq = 'F'
        for _ in range(3+int(n*2)): seq = seq.replace('F','F+F-F-F+F')
        grid = [[' ']*w for _ in range(h)]
        x,y,angle = w//2, h//2, 0
        for c in seq[:400]:
            if c=='F':
                dx = int(round(math.cos(math.radians(angle))+random.uniform(-0.1,0.1)*n))
                dy = int(round(math.sin(math.radians(angle))+random.uniform(-0.1,0.1)*n))
                nx,ny = x+dx, y+dy
                if 0<=nx<w and 0<=ny<h and random.random()>n*0.3: grid[ny][nx]=random.choice('oO0')
                x,y=nx,ny
            elif c=='+': angle+=90
            elif c=='-': angle-=90
        return grid
    def _adjust(self, grid, target):
        h,w = len(grid), len(grid[0])
        total = h*w
        non = sum(c!=' ' for row in grid for c in row)
        if non/total < target:
            need = int(total*target)-non
            pos = [(y,x) for y in range(h) for x in range(w) if grid[y][x]==' ']
            random.shuffle(pos)
            for _ in range(min(need,len(pos))): y,x=pos.pop(); grid[y][x]=random.choice('░▒▓█')
        elif non/total > target:
            need = non - int(total*target)
            pos = [(y,x) for y in range(h) for x in range(w) if grid[y][x]!=' ']
            random.shuffle(pos)
            for _ in range(min(need,len(pos))): y,x=pos.pop(); grid[y][x]=' '
    def set_params(self, p):
        self.params.update(p)
    def mutate(self, intensity=0.2):
        for k in ['symmetry','density','complexity','noise','shape_param']:
            if random.random() < intensity:
                self.params[k] += random.uniform(-0.15,0.15)
                if k == 'shape_param':
                    self.params[k] = max(0.0, min(1.0, self.params[k]))
                else:
                    self.params[k] = max(0.05, min(0.95, self.params[k]))
        if random.random() < intensity:
            self.params['pattern'] = random.choice(self.PATTERNS)
    def crossover_with_memory(self, other):
        for k in self.params:
            if k == 'pattern':
                if random.random() < 0.5:
                    self.params[k] = other.get(k, self.params[k])
            elif isinstance(other.get(k), (int, float)):
                self.params[k] = (self.params[k] + other[k]) / 2.0
