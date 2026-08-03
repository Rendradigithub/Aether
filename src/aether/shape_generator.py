import math
import random


class ShapeAwareGenerator:
    @staticmethod
    def draw_circle(grid, cx, cy, r, char='█'):
        h, w = len(grid), len(grid[0])
        for y in range(h):
            for x in range(w):
                dx = x - cx; dy = y - cy
                if abs(math.sqrt(dx*dx+dy*dy) - r) < 0.8:
                    grid[y][x] = char
    @staticmethod
    def draw_square(grid, cx, cy, size, char='█'):
        h, w = len(grid), len(grid[0])
        half = size // 2
        for y in range(cy-half, cy+half+1):
            if 0 <= y < h:
                for x in range(cx-half, cx+half+1):
                    if 0 <= x < w and (y == cy-half or y == cy+half or x == cx-half or x == cx+half):
                        grid[y][x] = char
    @staticmethod
    def draw_triangle(grid, cx, cy, size, char='█'):
        h, w = len(grid), len(grid[0])
        for i in range(size):
            y = cy - i
            if y < 0 or y >= h: continue
            x_start = cx - (size-i)//2
            x_end = cx + (size-i)//2
            for x in range(x_start, x_end+1):
                if 0 <= x < w and (i==0 or i==size-1 or x==x_start or x==x_end):
                    grid[y][x] = char

    @staticmethod
    def generate_shape(shape_param, symmetry, density, noise, w=52, h=18):
        grid = [[' ' for _ in range(w)] for _ in range(h)]
        cx, cy = w//2, h//2
        size = min(w,h)//4
        if shape_param < 0.33:
            r = int(size * (0.5 + shape_param*1.5))
            ShapeAwareGenerator.draw_circle(grid, cx, cy, r, '█')
        elif shape_param < 0.66:
            sz = int(size * (0.5 + (shape_param-0.33)*3))
            ShapeAwareGenerator.draw_square(grid, cx, cy, sz, '█')
        else:
            sz = int(size * (0.5 + (shape_param-0.66)*3))
            ShapeAwareGenerator.draw_triangle(grid, cx, cy, sz, '█')
        if density > 0.3:
            if shape_param < 0.33:
                r_inner = max(1, r-2)
                for y in range(h):
                    for x in range(w):
                        if grid[y][x] == ' ':
                            dist = math.sqrt((x-cx)**2 + (y-cy)**2)
                            if dist < r_inner:
                                if random.random() < density:
                                    grid[y][x] = random.choice('░▒▓')
            elif shape_param < 0.66:
                half = sz//2
                for y in range(cy-half+1, cy+half):
                    for x in range(cx-half+1, cx+half):
                        if grid[y][x] == ' ':
                            if random.random() < density:
                                grid[y][x] = random.choice('░▒▓')
            else:
                for y in range(cy-sz+1, cy+1):
                    wdt = int((sz - (cy - y)) * 2)
                    x_start = cx - wdt//2
                    x_end = cx + wdt//2
                    for x in range(max(0,x_start), min(w,x_end+1)):
                        if grid[y][x] == ' ':
                            if random.random() < density:
                                grid[y][x] = random.choice('░▒▓')
        if noise > 0:
            for y in range(h):
                for x in range(w):
                    if random.random() < noise*0.3:
                        if grid[y][x] == ' ':
                            grid[y][x] = random.choice(' .:oO0@')
                        elif random.random() < 0.5:
                            grid[y][x] = ' '
        return '\n'.join(''.join(row) for row in grid)
