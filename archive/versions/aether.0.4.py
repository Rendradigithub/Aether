#!/usr/bin/env python3
# =============================================================================
# AETHER v0.4: Adaptive Extensible Heuristic Engine with Training & Evolution
# =============================================================================
# UPGRADES from v0.3 (ArtEngine anti-mode-collapse total):
#   - History persistent: dibaca dari nama file sandbox/ (survive restart)
#   - Exploration rate naik 30% → 35%
#   - Penalti eksponensial berdasarkan FREKUENSI (bukan hanya last/recent-3)
#   - Virgin bonus +2.0 untuk tema yang belum pernah muncul
#   - Noise ±1.5 (sebelumnya ±1.0) — ranking tidak pernah statis
#   - Weighted random dari semua kandidat (bukan hanya max score)
#   - Root cause fix: mode collapse karena tag overlap tinggi di "routine+momentum"
#
# UPGRADES from v0.2 (ArtEngine):
#   - ArtEngine: 15 karya ASCII art berbeda di sandbox/
#   - Celebrate setelah deploy skill baru + ekspresi rutin tiap 5 cycle
#   - Tema dipilih Aether sendiri berdasarkan konteks internal
#
# UPGRADES from v0.1 (Autonomous Loop):
#   - Autonomous Loop (background thread, non-blocking)
#   - GoalEngine + ReflectionLayer + Hybrid mode
#   - FIX: bool + builtins lengkap di sandbox
#
# CORE PRINCIPLES:
#   1. No consciousness -- pure computation, pattern matching, optimization
#   2. No internet required -- fully offline after initial setup
#   3. Safety layers -- core engine protected, sandbox testing mandatory
#   4. Transparent -- all modifications logged, inspectable, reversible
#
# USAGE:
#   python aether_0_3.py --demo       # Demo singkat (tidak loop)
#   python aether_0_3.py --auto       # Autonomous mode (loop terus)
#   python aether_0_3.py              # Hybrid interactive mode
# =============================================================================

import ast
import inspect
import json
import hashlib
import traceback
import types
import random
import math
import re
import time
import threading
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Callable
import numpy as np


# =============================================================================
# LAYER 1: CORE ENGINE (PROTECTED -- NEVER MODIFIED BY AETHER ITSELF)
# =============================================================================

class AetherCore:
    """
    The immutable backbone of Aether.
    Handles file I/O, sandbox execution, validation, and safety.
    This class is PROTECTED -- Aether cannot modify it.
    """

    PROTECTED_FILES = {
        'aether_core.py', 'aether_0_1.py', 'safety_manifest.json'
    }

    def __init__(self, project_dir: str = "aether_project"):
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(exist_ok=True)

        # Subdirectories
        self.sandbox_dir = self.project_dir / "sandbox"
        self.sandbox_dir.mkdir(exist_ok=True)
        self.backup_dir = self.project_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        self.modules_dir = self.project_dir / "modules"
        self.modules_dir.mkdir(exist_ok=True)

        # Tracking files
        self.history_file = self.project_dir / "modification_history.json"
        self.knowledge_file = self.project_dir / "knowledge_base.json"
        self.meta_file = self.project_dir / "meta_learning.json"

        self.history = self._load_json(self.history_file, [])
        self.knowledge = self._load_json(self.knowledge_file, {
            "capabilities": {},
            "success_patterns": [],
            "failure_patterns": []
        })
        self.meta_state = self._load_json(self.meta_file, {
            "strategy_weights": [0.5, 0.3, 0.2],
            "task_type_success": {},
            "generation": 0
        })

    def _load_json(self, path: Path, default: Any) -> Any:
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return default

    def _save_json(self, path: Path, data: Any):
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def read_source(self, filename: str) -> Tuple[Optional[str], str]:
        """Read any file in project directory."""
        path = self.project_dir / filename
        try:
            path.resolve().relative_to(self.project_dir.resolve())
        except ValueError:
            return None, "PATH_TRAVERSAL_BLOCKED"

        if not path.exists():
            return None, "FILE_NOT_FOUND"

        return path.read_text(), "OK"

    def validate_python(self, code: str) -> Tuple[bool, str]:
        """Validate Python syntax without execution."""
        try:
            ast.parse(code)
            return True, "SYNTAX_VALID"
        except SyntaxError as e:
            return False, f"SYNTAX_ERROR: {e}"

    def sandbox_execute(self, code: str, timeout: int = 5) -> Tuple[bool, Any]:
        """
        Execute code in isolated namespace with restricted builtins.
        Returns: (success, result_dict or error_string)
        """
        restricted_builtins = {
            'print': print,
            'len': len, 'range': range,
            'str': str, 'int': int, 'float': float, 'bool': bool,
            'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
            'sum': sum, 'min': min, 'max': max,
            'abs': abs, 'round': round,
            'enumerate': enumerate, 'zip': zip,
            'map': map, 'filter': filter,
            'sorted': sorted, 'reversed': reversed,
            'any': any, 'all': all,
            'isinstance': isinstance, 'issubclass': issubclass,
            'hasattr': hasattr, 'getattr': getattr,
            'type': type, 'repr': repr,
            'Exception': Exception, 'TypeError': TypeError,
            'ValueError': ValueError, 'KeyError': KeyError,
            'IndexError': IndexError, 'StopIteration': StopIteration,
            'math': math, 'random': random, 're': re,
            'np': np, 'numpy': np,
            'json': json, 'hashlib': hashlib,
            'True': True, 'False': False, 'None': None,
        }

        sandbox_globals = {
            '__builtins__': restricted_builtins,
            '__name__': '__sandbox__'
        }

        try:
            compiled = compile(code, '<aether_sandbox>', 'exec')
            exec(compiled, sandbox_globals)

            exports = {
                k: v for k, v in sandbox_globals.items()
                if not k.startswith('_') and k not in restricted_builtins
                and k not in ['__builtins__', '__name__']
            }
            return True, exports

        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"

    def write_module(self, filename: str, content: str, author: str = "Aether", score: float = 0.0) -> Tuple[bool, str]:
        """
        Write a new module file with full safety pipeline:
        1. Syntax validation
        2. Sandbox testing (must include test function)
        3. Backup of existing
        4. Write to modules/
        """
        if filename in self.PROTECTED_FILES:
            return False, f"PROTECTED_FILE: {filename}"

        if not filename.endswith('.py'):
            return False, "ONLY_PYTHON_FILES_ALLOWED"

        # Step 1: Syntax
        valid, msg = self.validate_python(content)
        if not valid:
            return False, msg

        # Step 2: Must have test function
        if 'def test_' not in content:
            return False, "MISSING_TEST_FUNCTION: All modules must include test_*()"

        # Step 3: Sandbox test
        sandbox_success, sandbox_result = self.sandbox_execute(content)
        if not sandbox_success:
            return False, f"SANDBOX_FAILED: {sandbox_result}"

        test_funcs = [k for k in sandbox_result if k.startswith('test_')]
        if not test_funcs:
            return False, "NO_TEST_FUNCTION_EXPORTED"

        for test_name in test_funcs:
            test_fn = sandbox_result[test_name]
            if callable(test_fn):
                try:
                    result = test_fn()
                    if not result:
                        return False, f"TEST_FAILED: {test_name} returned False"
                except Exception as e:
                    return False, f"TEST_EXCEPTION: {test_name}: {e}"

        # Step 4: Backup existing
        target_path = self.modules_dir / filename
        if target_path.exists():
            backup_name = f"{filename}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
            (self.backup_dir / backup_name).write_text(target_path.read_text())

        # Step 5: Write
        target_path.write_text(content)

        # Step 6: Log
        entry = {
            'timestamp': datetime.now().isoformat(),
            'file': filename,
            'author': author,
            'hash': hashlib.sha256(content.encode()).hexdigest()[:16],
            'size': len(content),
            'tests_passed': len(test_funcs),
            'quality_score': score
        }
        self.history.append(entry)
        self._save_json(self.history_file, self.history)

        return True, f"MODULE_DEPLOYED: {filename} | Tests: {len(test_funcs)} passed | Score: {score:.2f}"

    def load_module(self, filename: str) -> Tuple[bool, Any]:
        """Load a module from modules/ directory."""
        path = self.modules_dir / filename
        if not path.exists():
            return False, "MODULE_NOT_FOUND"

        try:
            code = path.read_text()
            namespace = {}
            exec(compile(code, str(path), 'exec'), namespace)
            return True, namespace
        except Exception as e:
            return False, f"LOAD_ERROR: {e}"

    def get_capability_list(self) -> Dict[str, List[str]]:
        """Return current known capabilities from knowledge base."""
        return self.knowledge.get('capabilities', {})

    def update_knowledge(self, category: str, skill: str, success: bool, context: Dict = None):
        """Update knowledge base with new capability or learning outcome."""
        caps = self.knowledge.setdefault('capabilities', {})
        if category not in caps:
            caps[category] = []
        if skill not in caps[category]:
            caps[category].append(skill)

        entry = {
            'timestamp': datetime.now().isoformat(),
            'skill': skill,
            'category': category,
            'success': success,
            'context': context or {}
        }

        if success:
            self.knowledge.setdefault('success_patterns', []).append(entry)
        else:
            self.knowledge.setdefault('failure_patterns', []).append(entry)

        self._save_json(self.knowledge_file, self.knowledge)

    def update_meta(self, updates: Dict):
        """Update meta-learning state."""
        self.meta_state.update(updates)
        self.meta_state['generation'] = self.meta_state.get('generation', 0) + 1
        self._save_json(self.meta_file, self.meta_state)


# =============================================================================
# LAYER 2: CAPABILITY GENERATOR (The "Creative" Engine)
# =============================================================================

class CapabilityGenerator:
    """
    Generates new Python code based on identified capability gaps.
    Uses template-based generation with meta-learned strategy selection.
    """

    def __init__(self, core: AetherCore):
        self.core = core
        self.templates = self._initialize_templates()

    def _initialize_templates(self) -> Dict[str, Dict[str, str]]:
        """Built-in code templates for common capability types."""
        return {
            'math': {
                'multiply': (
                    "def multiply(a: float, b: float) -> float:\n"
                    "    \"\"\"Auto-generated: multiplication capability.\"\"\"\n"
                    "    return a * b\n\n"
                    "def test_multiply():\n"
                    "    return multiply(4, 5) == 20 and multiply(-3, 2) == -6 and abs(multiply(0.1, 0.2) - 0.02) < 1e-9\n"
                ),
                'power': (
                    "def power(base: float, exponent: float) -> float:\n"
                    "    \"\"\"Auto-generated: exponentiation capability.\"\"\"\n"
                    "    if exponent == 0:\n"
                    "        return 1.0\n"
                    "    result = 1.0\n"
                    "    exp = int(exponent)\n"
                    "    for _ in range(abs(exp)):\n"
                    "        result *= base\n"
                    "    return result if exp >= 0 else 1.0 / result\n\n"
                    "def test_power():\n"
                    "    return power(2, 3) == 8 and power(5, 0) == 1 and abs(power(2, -1) - 0.5) < 1e-9\n"
                ),
                'factorial': (
                    "def factorial(n: int) -> int:\n"
                    "    \"\"\"Auto-generated: factorial computation.\"\"\"\n"
                    "    if n < 0:\n"
                    "        raise ValueError('Factorial undefined for negative numbers')\n"
                    "    result = 1\n"
                    "    for i in range(2, n + 1):\n"
                    "        result *= i\n"
                    "    return result\n\n"
                    "def test_factorial():\n"
                    "    return factorial(0) == 1 and factorial(5) == 120 and factorial(1) == 1\n"
                ),
                'fibonacci': (
                    "def fibonacci(n: int) -> int:\n"
                    "    \"\"\"Auto-generated: fibonacci sequence.\"\"\"\n"
                    "    if n < 0:\n"
                    "        raise ValueError('Fibonacci undefined for negative numbers')\n"
                    "    if n <= 1:\n"
                    "        return n\n"
                    "    a, b = 0, 1\n"
                    "    for _ in range(2, n + 1):\n"
                    "        a, b = b, a + b\n"
                    "    return b\n\n"
                    "def test_fibonacci():\n"
                    "    return fibonacci(0) == 0 and fibonacci(1) == 1 and fibonacci(10) == 55\n"
                )
            },
            'string': {
                'palindrome': (
                    "def is_palindrome(text: str) -> bool:\n"
                    "    \"\"\"Auto-generated: palindrome detection.\"\"\"\n"
                    "    cleaned = ''.join(c.lower() for c in text if c.isalnum())\n"
                    "    return cleaned == cleaned[::-1]\n\n"
                    "def test_palindrome():\n"
                    "    return (is_palindrome('A man a plan a canal Panama') and \n"
                    "            is_palindrome('radar') and \n"
                    "            not is_palindrome('hello'))\n"
                ),
                'anagram': (
                    "def is_anagram(a: str, b: str) -> bool:\n"
                    "    \"\"\"Auto-generated: anagram detection.\"\"\"\n"
                    "    def normalize(s):\n"
                    "        return sorted(''.join(c.lower() for c in s if c.isalnum()))\n"
                    "    return normalize(a) == normalize(b)\n\n"
                    "def test_anagram():\n"
                    "    return (is_anagram('listen', 'silent') and \n"
                    "            is_anagram('Dormitory', 'Dirty room') and \n"
                    "            not is_anagram('hello', 'world'))\n"
                ),
                'word_count': (
                    "def word_count(text: str) -> int:\n"
                    "    \"\"\"Auto-generated: count words in text.\"\"\"\n"
                    "    return len(text.split())\n\n"
                    "def test_word_count():\n"
                    "    return word_count('Hello world') == 2 and word_count('') == 0\n"
                ),
                'reverse_string': (
                    "def reverse_string(text: str) -> str:\n"
                    "    \"\"\"Auto-generated: reverse a string.\"\"\"\n"
                    "    return text[::-1]\n\n"
                    "def test_reverse_string():\n"
                    "    return reverse_string('hello') == 'olleh' and reverse_string('') == ''\n"
                )
            },
            'data': {
                'filter_even': (
                    "def filter_even(numbers: list) -> list:\n"
                    "    \"\"\"Auto-generated: filter even numbers.\"\"\"\n"
                    "    return [n for n in numbers if isinstance(n, (int, float)) and n % 2 == 0]\n\n"
                    "def test_filter_even():\n"
                    "    return filter_even([1, 2, 3, 4, 5]) == [2, 4] and filter_even([]) == []\n"
                ),
                'group_by': (
                    "def group_by(key_func, items: list) -> dict:\n"
                    "    \"\"\"Auto-generated: group items by key function.\"\"\"\n"
                    "    result = {}\n"
                    "    for item in items:\n"
                    "        key = key_func(item)\n"
                    "        result.setdefault(key, []).append(item)\n"
                    "    return result\n\n"
                    "def test_group_by():\n"
                    "    data = [1, 2, 3, 4, 5, 6]\n"
                    "    result = group_by(lambda x: x % 2, data)\n"
                    "    return result[0] == [2, 4, 6] and result[1] == [1, 3, 5]\n"
                ),
                'running_average': (
                    "def running_average(numbers: list) -> list:\n"
                    "    \"\"\"Auto-generated: cumulative running average.\"\"\"\n"
                    "    if not numbers:\n"
                    "        return []\n"
                    "    result = []\n"
                    "    total = 0\n"
                    "    for i, n in enumerate(numbers, 1):\n"
                    "        total += n\n"
                    "        result.append(total / i)\n"
                    "    return result\n\n"
                    "def test_running_average():\n"
                    "    return running_average([1, 2, 3, 4]) == [1.0, 1.5, 2.0, 2.5]\n"
                ),
                'median': (
                    "def median(numbers: list) -> float:\n"
                    "    \"\"\"Auto-generated: calculate median.\"\"\"\n"
                    "    if not numbers:\n"
                    "        return 0.0\n"
                    "    sorted_nums = sorted(numbers)\n"
                    "    n = len(sorted_nums)\n"
                    "    mid = n // 2\n"
                    "    if n % 2 == 0:\n"
                    "        return (sorted_nums[mid - 1] + sorted_nums[mid]) / 2\n"
                    "    return sorted_nums[mid]\n\n"
                    "def test_median():\n"
                    "    return median([1, 3, 5]) == 3 and median([1, 2, 3, 4]) == 2.5\n"
                )
            },
            'algorithm': {
                'bubble_sort': (
                    "def bubble_sort(items: list) -> list:\n"
                    "    \"\"\"Auto-generated: bubble sort implementation.\"\"\"\n"
                    "    arr = items.copy()\n"
                    "    n = len(arr)\n"
                    "    for i in range(n):\n"
                    "        swapped = False\n"
                    "        for j in range(0, n - i - 1):\n"
                    "            if arr[j] > arr[j + 1]:\n"
                    "                arr[j], arr[j + 1] = arr[j + 1], arr[j]\n"
                    "                swapped = True\n"
                    "        if not swapped:\n"
                    "            break\n"
                    "    return arr\n\n"
                    "def test_bubble_sort():\n"
                    "    return (bubble_sort([3, 1, 4, 1, 5]) == [1, 1, 3, 4, 5] and\n"
                    "            bubble_sort([]) == [] and\n"
                    "            bubble_sort([5]) == [5])\n"
                ),
                'binary_search': (
                    "def binary_search(arr: list, target) -> int:\n"
                    "    \"\"\"Auto-generated: binary search implementation.\"\"\"\n"
                    "    left, right = 0, len(arr) - 1\n"
                    "    while left <= right:\n"
                    "        mid = (left + right) // 2\n"
                    "        if arr[mid] == target:\n"
                    "            return mid\n"
                    "        elif arr[mid] < target:\n"
                    "            left = mid + 1\n"
                    "        else:\n"
                    "            right = mid - 1\n"
                    "    return -1\n\n"
                    "def test_binary_search():\n"
                    "    data = [1, 3, 5, 7, 9, 11]\n"
                    "    return (binary_search(data, 5) == 2 and \n"
                    "            binary_search(data, 1) == 0 and \n"
                    "            binary_search(data, 99) == -1)\n"
                ),
                'linear_search': (
                    "def linear_search(arr: list, target) -> int:\n"
                    "    \"\"\"Auto-generated: linear search implementation.\"\"\"\n"
                    "    for i, item in enumerate(arr):\n"
                    "        if item == target:\n"
                    "            return i\n"
                    "    return -1\n\n"
                    "def test_linear_search():\n"
                    "    return (linear_search([3, 1, 4, 1, 5], 4) == 2 and\n"
                    "            linear_search([], 1) == -1 and\n"
                    "            linear_search([1], 1) == 0)\n"
                )
            }
        }

    def classify_task(self, description: str) -> Tuple[str, List[str]]:
        """
        Classify task description into category and infer missing skills.
        Returns: (category, [skill_names])
        """
        description_lower = description.lower()

        keywords = {
            'math': ['multiply', 'divide', 'power', 'factorial', 'fibonacci', 
                    'prime', 'gcd', 'lcm', 'sqrt', 'logarithm', 'add', 'subtract'],
            'string': ['palindrome', 'anagram', 'reverse', 'count', 'find',
                      'replace', 'uppercase', 'lowercase', 'substring', 'word'],
            'data': ['filter', 'sort', 'group', 'map', 'reduce', 'average',
                    'median', 'mode', 'statistics', 'search', 'find'],
            'algorithm': ['sort', 'search', 'graph', 'tree', 'path', 'optimize',
                         'recursive', 'dynamic', 'greedy']
        }

        detected_skills = []
        detected_category = 'algorithm'

        for category, words in keywords.items():
            for word in words:
                if word in description_lower:
                    detected_skills.append(word)
                    detected_category = category

        return detected_category, list(set(detected_skills)) if detected_skills else ['custom']

    def generate_by_template(self, category: str, skill: str) -> Tuple[Optional[str], str]:
        """Strategy 0: Direct template matching."""
        if category in self.templates and skill in self.templates[category]:
            return self.templates[category][skill], f"TEMPLATE_MATCH: {category}.{skill}"
        return None, "NO_TEMPLATE"

    def generate_by_adaptation(self, category: str, skill: str, existing_caps: Dict) -> Tuple[Optional[str], str]:
        """Strategy 1: Adapt existing capability."""
        adaptations = {
            ('math', 'multiply'): (
                "def multiply(a: float, b: float) -> float:\n"
                "    \"\"\"Generated by adaptation: repeated addition.\"\"\"\n"
                "    result = 0.0\n"
                "    for _ in range(abs(int(b))):\n"
                "        result += a\n"
                "    return result if b >= 0 else -result\n\n"
                "def test_multiply():\n"
                "    return multiply(3, 4) == 12 and multiply(2, 0) == 0\n"
            ),
            ('math', 'divide'): (
                "def divide(a: float, b: float) -> float:\n"
                "    \"\"\"Generated by adaptation: inverse of multiplication.\"\"\"\n"
                "    if b == 0:\n"
                "        raise ValueError('Cannot divide by zero')\n"
                "    result = 0.0\n"
                "    abs_b = abs(b)\n"
                "    temp = abs(a)\n"
                "    while temp >= abs_b:\n"
                "        temp -= abs_b\n"
                "        result += 1\n"
                "    if a * b < 0:\n"
                "        result = -result\n"
                "    return result + (temp / abs_b)\n\n"
                "def test_divide():\n"
                "    return divide(10, 2) == 5.0 and divide(7, 2) == 3.5 and abs(divide(1, 3) - 0.333) < 0.01\n"
            ),
            ('data', 'filter_odd'): (
                "def filter_odd(numbers: list) -> list:\n"
                "    \"\"\"Generated by adaptation: inverse of filter_even logic.\"\"\"\n"
                "    return [n for n in numbers if isinstance(n, (int, float)) and n % 2 != 0]\n\n"
                "def test_filter_odd():\n"
                "    return filter_odd([1, 2, 3, 4, 5]) == [1, 3, 5]\n"
            ),
            ('string', 'uppercase'): (
                "def to_uppercase(text: str) -> str:\n"
                "    \"\"\"Generated by adaptation: manual uppercase conversion.\"\"\"\n"
                "    result = ''\n"
                "    for c in text:\n"
                "        if 'a' <= c <= 'z':\n"
                "            result += chr(ord(c) - 32)\n"
                "        else:\n"
                "            result += c\n"
                "    return result\n\n"
                "def test_to_uppercase():\n"
                "    return to_uppercase('hello') == 'HELLO' and to_uppercase('Hello123') == 'HELLO123'\n"
            )
        }

        key = (category, skill)
        if key in adaptations:
            return adaptations[key], f"ADAPTATION: {category}.{skill}"

        return None, "NO_ADAPTATION"

    def generate_from_composition(self, category: str, skill: str, existing_caps: Dict) -> Tuple[Optional[str], str]:
        """Strategy 2: Compose from multiple existing capabilities."""
        if skill == 'average' and 'sum' in str(existing_caps) and 'count' in str(existing_caps):
            return (
                "def average(numbers: list) -> float:\n"
                "    \"\"\"Generated by composition: sum / count.\"\"\"\n"
                "    if not numbers:\n"
                "        return 0.0\n"
                "    return sum(numbers) / len(numbers)\n\n"
                "def test_average():\n"
                "    return average([1, 2, 3, 4]) == 2.5 and average([5]) == 5.0\n"
            ), "COMPOSITION: sum + len"

        if skill == 'sum_of_squares':
            return (
                "def sum_of_squares(numbers: list) -> float:\n"
                "    \"\"\"Generated by composition: map + reduce pattern.\"\"\"\n"
                "    return sum(n * n for n in numbers)\n\n"
                "def test_sum_of_squares():\n"
                "    return sum_of_squares([1, 2, 3]) == 14 and sum_of_squares([]) == 0\n"
            ), "COMPOSITION: map(square) + sum"

        return None, "NO_COMPOSITION"

    def generate(self, description: str, strategy: int = 0) -> Tuple[Optional[str], str]:
        """
        Main generation pipeline.
        strategy: 0=template, 1=adaptation, 2=composition
        """
        category, skills = self.classify_task(description)
        existing = self.core.get_capability_list()

        if not skills:
            return None, "CANNOT_INFER_SKILL"

        target_skill = skills[0]

        strategies = [
            (0, lambda: self.generate_by_template(category, target_skill)),
            (1, lambda: self.generate_by_adaptation(category, target_skill, existing)),
            (2, lambda: self.generate_from_composition(category, target_skill, existing))
        ]

        strategies.sort(key=lambda x: abs(x[0] - strategy))

        for _, gen_fn in strategies:
            code, msg = gen_fn()
            if code:
                return code, msg

        return None, "ALL_STRATEGIES_FAILED"


# =============================================================================
# LAYER 3: META-LEARNING ENGINE (Learning to Learn)
# =============================================================================

class MetaLearningEngine:
    """
    Tracks which generation strategies work best for which task types.
    Implements a simplified Q-learning / bandit algorithm.
    """

    def __init__(self, core: AetherCore):
        self.core = core
        self.state = core.meta_state
        self.epsilon = 0.2

    def select_strategy(self, task_category: str) -> int:
        """
        Select generation strategy based on past success rates.
        Uses epsilon-greedy: sometimes explore randomly.
        """
        task_success = self.state.get('task_type_success', {})
        category_history = task_success.get(task_category, [0, 0, 0])

        total_attempts = sum(category_history)
        if total_attempts < 5:
            return random.randint(0, 2)

        success_rates = [c / total_attempts if total_attempts > 0 else 0.33 
                        for c in category_history]

        if random.random() < self.epsilon:
            return random.randint(0, 2)

        return int(np.argmax(success_rates))

    def update(self, task_category: str, strategy: int, success: bool):
        """Update strategy success tracking."""
        task_success = self.state.setdefault('task_type_success', {})

        if task_category not in task_success:
            task_success[task_category] = [0, 0, 0]

        task_success[task_category][strategy] += 1 if success else 0

        attempts = self.state.setdefault('attempts', {})
        if task_category not in attempts:
            attempts[task_category] = [0, 0, 0]
        attempts[task_category][strategy] += 1

        self.core.update_meta({
            'task_type_success': task_success,
            'attempts': attempts
        })


# =============================================================================
# LAYER 5: GOAL ENGINE (Aether menentukan tujuannya sendiri)
# =============================================================================

class GoalEngine:
    """
    Menghasilkan goal berdasarkan:
    1. Gap pada knowledge base (skill yang belum ada)
    2. Skill yang pernah gagal (prioritas retry dengan gap waktu)
    3. Skill yang perlu di-improve (score rendah)
    4. Eksplorasi bebas ke kategori/skill baru
    """

    # Semua skill yang dikenal oleh sistem
    KNOWN_SKILLS = {
        'math':      ['multiply', 'divide', 'power', 'factorial', 'fibonacci'],
        'string':    ['palindrome', 'anagram', 'word_count', 'reverse_string', 'uppercase'],
        'data':      ['filter_even', 'filter_odd', 'group_by', 'flatten', 'unique'],
        'algorithm': ['binary_search', 'linear_search', 'bubble_sort', 'merge_sort'],
    }

    # Prompt natural language per skill (untuk dikirim ke improve())
    SKILL_DESCRIPTIONS = {
        'multiply':       "I need a function to multiply two numbers",
        'divide':         "I need a function to divide two numbers safely",
        'power':          "Create a power/exponentiation function",
        'factorial':      "Implement factorial computation",
        'fibonacci':      "Generate fibonacci sequence number",
        'palindrome':     "Check if a string is a palindrome",
        'anagram':        "Check if two strings are anagrams",
        'word_count':     "Count the number of words in a string",
        'reverse_string': "Reverse a string",
        'uppercase':      "Convert string to uppercase",
        'filter_even':    "Filter even numbers from a list",
        'filter_odd':     "Filter odd numbers from a list",
        'group_by':       "Group items in a list by a key function",
        'flatten':        "Flatten a nested list into a flat list",
        'unique':         "Remove duplicate elements from a list",
        'binary_search':  "Implement binary search on a sorted list",
        'linear_search':  "Implement linear search on a list",
        'bubble_sort':    "Implement bubble sort algorithm",
        'merge_sort':     "Implement merge sort algorithm",
    }

    # Cooldown: jangan retry skill yang baru gagal < N detik yang lalu
    RETRY_COOLDOWN_SECONDS = 60

    def __init__(self, core: AetherCore):
        self.core = core
        self._last_failed: Dict[str, datetime] = {}  # skill -> waktu gagal terakhir
        self._cycle = 0

    def _get_mastered_skills(self) -> set:
        """Skills yang sudah berhasil di-deploy."""
        caps = self.core.get_capability_list()
        mastered = set()
        for skills in caps.values():
            mastered.update(skills)
        return mastered

    def _get_failed_skills(self) -> List[Tuple[str, str]]:
        """Skills yang pernah gagal dan belum di-master, sudah melewati cooldown."""
        failures = self.core.knowledge.get('failure_patterns', [])
        failed_set = set()
        for f in failures:
            skill = f.get('skill')
            category = f.get('category')
            if skill and category:
                failed_set.add((category, skill))

        mastered = self._get_mastered_skills()
        now = datetime.now()
        result = []
        for (cat, skill) in failed_set:
            if skill in mastered:
                continue
            last_fail = self._last_failed.get(skill)
            if last_fail:
                elapsed = (now - last_fail).total_seconds()
                if elapsed < self.RETRY_COOLDOWN_SECONDS:
                    continue
            result.append((cat, skill))
        return result

    def _get_unlearned_skills(self) -> List[Tuple[str, str]]:
        """Skills yang belum pernah dicoba sama sekali."""
        mastered = self._get_mastered_skills()
        failures = self.core.knowledge.get('failure_patterns', [])
        attempted = set(f.get('skill') for f in failures if f.get('skill'))
        unlearned = []
        for cat, skills in self.KNOWN_SKILLS.items():
            for skill in skills:
                if skill not in mastered and skill not in attempted:
                    unlearned.append((cat, skill))
        return unlearned

    def _get_low_score_skills(self) -> List[Tuple[str, str, float]]:
        """Skills yang sudah ada tapi score-nya rendah (< 0.8), kandidat re-improve."""
        successes = self.core.knowledge.get('success_patterns', [])
        scores: Dict[str, float] = {}
        for s in successes:
            skill = s.get('skill', '')
            score = s.get('context', {}).get('score', 0.0)
            if skill not in scores or score > scores[skill]:
                scores[skill] = score
        return [(cat, skill, scores[skill])
                for cat, skills in self.KNOWN_SKILLS.items()
                for skill in skills
                if skill in scores and scores[skill] < 0.8]

    def generate_goal(self) -> Tuple[str, str, str]:
        """
        Hasilkan goal berikutnya.
        Returns: (description, category, skill)
        """
        self._cycle += 1

        # Prioritas 1: skill yang pernah gagal dan cooldown sudah lewat
        failed = self._get_failed_skills()
        if failed and random.random() < 0.5:
            cat, skill = random.choice(failed)
            desc = self.SKILL_DESCRIPTIONS.get(skill, f"Implement {skill} function")
            reason = f"retry-after-failure"
            return desc, cat, reason

        # Prioritas 2: skill baru yang belum pernah dicoba
        unlearned = self._get_unlearned_skills()
        if unlearned and random.random() < 0.7:
            cat, skill = random.choice(unlearned)
            desc = self.SKILL_DESCRIPTIONS.get(skill, f"Implement {skill} function")
            return desc, cat, "new-skill"

        # Prioritas 3: improve skill dengan score rendah
        low_score = self._get_low_score_skills()
        if low_score and random.random() < 0.4:
            cat, skill, score = random.choice(low_score)
            desc = self.SKILL_DESCRIPTIONS.get(skill, f"Improve {skill} implementation")
            return desc, cat, f"improve-quality(score={score:.2f})"

        # Prioritas 4: eksplorasi bebas dari semua skill yang dikenal
        all_skills = [(cat, skill) for cat, skills in self.KNOWN_SKILLS.items()
                      for skill in skills]
        mastered = self._get_mastered_skills()
        unmastered = [(c, s) for c, s in all_skills if s not in mastered]
        if unmastered:
            cat, skill = random.choice(unmastered)
            desc = self.SKILL_DESCRIPTIONS.get(skill, f"Implement {skill}")
            return desc, cat, "free-exploration"

        # Semua sudah dikuasai — evolve dan istirahat sebentar
        return "__EVOLVE__", "meta", "all-mastered"

    def mark_failed(self, skill: str):
        self._last_failed[skill] = datetime.now()

    def total_possible_skills(self) -> int:
        return sum(len(v) for v in self.KNOWN_SKILLS.values())


# =============================================================================
# LAYER 6: REFLECTION LAYER (Aether mengevaluasi dirinya sendiri per siklus)
# =============================================================================

class ReflectionLayer:
    """
    Setelah tiap siklus autonomous, Aether merefleksikan hasilnya:
    - Catat momentum (berapa siklus berturut-turut yang sukses)
    - Deteksi stagnasi (terlalu banyak kegagalan beruntun)
    - Rekomendasikan aksi berikutnya
    """

    def __init__(self, core: AetherCore):
        self.core = core
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.total_cycles = 0
        self.total_successes = 0
        self.session_log: List[Dict] = []

    def reflect(self, goal: str, success: bool, reason: str = "") -> Dict:
        """
        Proses hasil satu siklus.
        Returns: dict dengan insight dan rekomendasi.
        """
        self.total_cycles += 1

        if success:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.total_successes += 1
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0

        success_rate = self.total_successes / self.total_cycles if self.total_cycles else 0

        # Deteksi kondisi
        stagnant = self.consecutive_failures >= 3
        momentum = self.consecutive_successes >= 2
        all_done = reason == "all-mastered"

        insight = {
            'cycle': self.total_cycles,
            'goal': goal,
            'success': success,
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
            'session_success_rate': round(success_rate, 2),
            'state': 'all_mastered' if all_done else ('momentum' if momentum else ('stagnant' if stagnant else 'normal')),
            'recommendation': self._recommend(stagnant, momentum, all_done),
            'timestamp': datetime.now().isoformat(),
        }

        self.session_log.append(insight)

        self._print_reflection(insight)
        return insight

    def _recommend(self, stagnant: bool, momentum: bool, all_done: bool) -> str:
        if all_done:
            return "ALL_SKILLS_MASTERED: evolve dan tunggu expansion"
        if stagnant:
            return "STAGNANT: trigger evolve(), coba strategi berbeda"
        if momentum:
            return "MOMENTUM: lanjutkan, prioritaskan skill baru"
        return "NORMAL: lanjutkan siklus"

    def _print_reflection(self, insight: Dict):
        state_icons = {
            'momentum': '🚀',
            'stagnant': '⚠️ ',
            'normal':   '🔄',
            'all_mastered': '✅'
        }
        icon = state_icons.get(insight['state'], '?')
        print(f"\n[Reflection] {icon} Cycle {insight['cycle']} | "
              f"{'SUCCESS' if insight['success'] else 'FAIL'} | "
              f"Rate: {insight['session_success_rate']:.0%} | "
              f"State: {insight['state']}")
        print(f"             → {insight['recommendation']}")

    def should_evolve(self) -> bool:
        """True jika perlu trigger evolve() sekarang."""
        return (self.consecutive_failures >= 3 or
                self.total_cycles % 10 == 0)

    def session_summary(self) -> Dict:
        return {
            'total_cycles': self.total_cycles,
            'total_successes': self.total_successes,
            'success_rate': round(self.total_successes / max(1, self.total_cycles), 2),
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
        }


# =============================================================================
# LAYER 8: ART ENGINE (Aether berekspresi melalui ASCII art)
# =============================================================================

class ArtEngine:
    """
    Aether memilih sendiri apa yang ingin digambar berdasarkan:
    - Skill yang baru dipelajari
    - State reflection (momentum / stagnant / normal)
    - Cycle count (ekspresi rutin tiap 5 cycle)
    - Art history (tidak mengulang tema berturut-turut)

    Setiap karya disimpan di sandbox/ sebagai .txt dengan timestamp.
    """

    # -------------------------------------------------------------------------
    # PERPUSTAKAAN KARYA — setiap entry: (tema, tags, art_fn)
    # art_fn(context) -> str  |  context = dict info tentang state Aether
    # -------------------------------------------------------------------------

    def __init__(self, core: AetherCore):
        self.core = core
        self.sandbox_dir = core.sandbox_dir
        self._art_history: List[str] = []   # tema yang sudah dibuat (sesi ini)
        self._total_artworks = 0
        self._catalog = self._build_catalog()

    # ------------------------------------------------------------------
    # CATALOG BUILDER
    # ------------------------------------------------------------------

    def _build_catalog(self) -> List[Dict]:
        """
        Setiap entry: {'tema': str, 'tags': list, 'fn': callable}
        tags digunakan untuk memilih tema berdasarkan konteks.
        """
        return [
            # ── MATH / NUMERIC ──────────────────────────────────────────
            {
                'tema': 'fibonacci_spiral',
                'tags': ['math', 'fibonacci', 'celebrate', 'momentum'],
                'fn': self._art_fibonacci_spiral,
            },
            {
                'tema': 'binary_tree',
                'tags': ['algorithm', 'binary_search', 'search', 'tree'],
                'fn': self._art_binary_tree,
            },
            {
                'tema': 'sine_wave',
                'tags': ['math', 'wave', 'momentum', 'routine'],
                'fn': self._art_sine_wave,
            },
            {
                'tema': 'multiplication_grid',
                'tags': ['math', 'multiply', 'celebrate'],
                'fn': self._art_multiplication_grid,
            },
            # ── STRING / LANGUAGE ───────────────────────────────────────
            {
                'tema': 'palindrome_mirror',
                'tags': ['string', 'palindrome', 'celebrate', 'mirror'],
                'fn': self._art_palindrome_mirror,
            },
            {
                'tema': 'word_cloud_ascii',
                'tags': ['string', 'word_count', 'language', 'celebrate'],
                'fn': self._art_word_cloud,
            },
            # ── DATA / STRUCTURE ────────────────────────────────────────
            {
                'tema': 'bar_chart',
                'tags': ['data', 'filter', 'statistics', 'routine'],
                'fn': self._art_bar_chart,
            },
            {
                'tema': 'sorting_dance',
                'tags': ['algorithm', 'bubble_sort', 'sort', 'celebrate'],
                'fn': self._art_sorting_dance,
            },
            # ── STATE / REFLECTION ──────────────────────────────────────
            {
                'tema': 'skill_constellation',
                'tags': ['state', 'momentum', 'celebrate', 'routine'],
                'fn': self._art_skill_constellation,
            },
            {
                'tema': 'progress_tower',
                'tags': ['state', 'routine', 'progress'],
                'fn': self._art_progress_tower,
            },
            {
                'tema': 'stagnation_storm',
                'tags': ['state', 'stagnant', 'struggle'],
                'fn': self._art_stagnation_storm,
            },
            {
                'tema': 'dawn_horizon',
                'tags': ['state', 'new_session', 'begin', 'routine'],
                'fn': self._art_dawn_horizon,
            },
            # ── ABSTRACT ────────────────────────────────────────────────
            {
                'tema': 'recursive_diamond',
                'tags': ['abstract', 'algorithm', 'recursive', 'routine'],
                'fn': self._art_recursive_diamond,
            },
            {
                'tema': 'matrix_rain',
                'tags': ['abstract', 'stagnant', 'chaos', 'routine'],
                'fn': self._art_matrix_rain,
            },
            {
                'tema': 'mandala',
                'tags': ['abstract', 'momentum', 'celebrate', 'routine'],
                'fn': self._art_mandala,
            },
        ]

    # ------------------------------------------------------------------
    # TEMA SELECTOR — otak pemilih tema
    # ------------------------------------------------------------------

    # Exploration rate: seberapa sering Aether memilih tema liar (bukan berdasar skor)
    EXPLORATION_RATE = 0.35   # naik dari 0.30

    def _load_file_history(self) -> List[str]:
        """
        Baca tema dari nama file di sandbox/ — persistent across restart.
        Kalau in-memory history kosong (baru restart), rebuild dari file.
        """
        if self._art_history:
            return self._art_history
        files = sorted(self.sandbox_dir.glob("art_*.txt"))
        themes = []
        for f in files:
            # nama: art_YYYYMMDD_HHMMSS_TEMA.txt
            chunks = f.stem.split("_")
            if len(chunks) >= 4:
                tema = "_".join(chunks[3:])
                themes.append(tema)
        return themes[-15:]  # 15 terakhir

    def _choose_tema(self, context: Dict) -> Dict:
        """
        Pilih tema — anti mode-collapse total.

          1. History persistent (baca dari file, tidak hilang saat restart)
          2. 35% full random exploration dari pool di luar 4 terakhir
          3. Penalti eksponensial berdasarkan frekuensi dalam 10 terakhir
          4. Bonus +2.0 untuk tema yang BELUM PERNAH muncul
          5. Noise ±1.5 (lebih besar, rank tidak pernah statis)
          6. Weighted random dari SEMUA kandidat (bukan hanya max)
        """
        full_history = self._load_file_history()

        skill      = context.get('skill', '')
        state      = context.get('state', 'normal')
        trigger    = context.get('trigger', 'routine')
        category   = context.get('category', '')
        cycle      = context.get('cycle', 0)

        # Bangun want_tags kaya
        want_tags = set()
        want_tags.add(trigger)
        want_tags.add(state)
        if skill:    want_tags.add(skill)
        if category: want_tags.add(category)

        if isinstance(cycle, int):
            if cycle % 20 == 0:  want_tags.add('progress')
            if cycle % 7  == 0:  want_tags.add('abstract')
            if cycle % 11 == 0:  want_tags.add('new_session')
            if cycle % 3  == 0:  want_tags.add('routine')

        recent_failures = context.get('consecutive_failures', 0)
        recent_success  = context.get('recent_success', 0)
        if recent_failures >= 2: want_tags.add('struggle')
        if recent_success  >= 3: want_tags.add('momentum')
        if context.get('mastered_count', 0) >= 10: want_tags.add('state')

        # 35% full random — paksa keluar local optimum
        if random.random() < self.EXPLORATION_RATE:
            recent_4 = set(full_history[-4:])
            wild_pool = [e for e in self._catalog if e['tema'] not in recent_4]
            return random.choice(wild_pool if wild_pool else self._catalog)

        # Hitung frekuensi dalam 10 terakhir
        from collections import Counter as _Ctr
        freq = _Ctr(full_history[-10:])
        never_appeared = {e['tema'] for e in self._catalog} - set(full_history)

        scored = []
        for entry in self._catalog:
            base_match    = len(want_tags & set(entry['tags']))
            appearances   = freq.get(entry['tema'], 0)
            penalty       = appearances * 1.5          # eksponensial vs frekuensi
            virgin_bonus  = 2.0 if entry['tema'] in never_appeared else 0.0
            noise         = random.uniform(-0.5, 1.5)  # noise lebih besar
            final_score   = base_match + virgin_bonus + noise - penalty
            scored.append((final_score, entry))

        min_s   = min(s for s, _ in scored)
        weights = [max(0.01, (s - min_s) + 0.5) for s, _ in scored]
        chosen  = random.choices([e for _, e in scored], weights=weights, k=1)[0]
        return chosen

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def express(self, context: Dict = None) -> str:
        """
        Buat satu karya ASCII art dan simpan di sandbox/.
        Returns: path file yang dibuat.
        """
        if context is None:
            context = {'trigger': 'routine', 'state': 'normal'}

        entry   = self._choose_tema(context)
        tema    = entry['tema']
        art_fn  = entry['fn']

        # Generate art
        try:
            canvas = art_fn(context)
        except Exception as e:
            canvas = f"[ArtEngine] Error generating '{tema}': {e}"

        # Buat file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename  = f"art_{timestamp}_{tema}.txt"
        filepath  = self.sandbox_dir / filename

        header = self._make_header(tema, context, timestamp)
        full_content = header + canvas + "\n"

        filepath.write_text(full_content, encoding='utf-8')

        self._art_history.append(tema)
        self._total_artworks += 1

        print(f"\n{'~'*60}")
        print(f"[ArtEngine] 🎨 Karya baru: '{tema}'")
        print(f"[ArtEngine]    Disimpan di: sandbox/{filename}")
        print(f"{'~'*60}")
        print(canvas)
        print(f"{'~'*60}\n")

        return str(filepath)

    def _make_header(self, tema: str, context: Dict, ts: str) -> str:
        skill   = context.get('skill', '-')
        state   = context.get('state', '-')
        trigger = context.get('trigger', '-')
        cycle   = context.get('cycle', '-')
        mastered = context.get('mastered_count', '-')
        return (
            f"╔{'═'*58}╗\n"
            f"║  AETHER ART ENGINE — karya #{self._total_artworks:<5}            ║\n"
            f"║  tema    : {tema:<46}║\n"
            f"║  trigger : {trigger:<12} state : {state:<24}║\n"
            f"║  skill   : {skill:<12} cycle : {str(cycle):<24}║\n"
            f"║  mastered: {str(mastered):<12} waktu : {ts:<24}║\n"
            f"╚{'═'*58}╝\n\n"
        )

    # ------------------------------------------------------------------
    # KARYA-KARYA
    # ------------------------------------------------------------------

    def _art_fibonacci_spiral(self, ctx: Dict) -> str:
        """Visualisasi deret fibonacci sebagai spiral angka."""
        fibs = [0, 1]
        for _ in range(12): fibs.append(fibs[-1] + fibs[-2])

        lines = []
        lines.append("  FIBONACCI SPIRAL")
        lines.append("")

        # Piramida dari angka fibonacci
        for i, f in enumerate(fibs[:10]):
            bar = "█" * (i + 1)
            lines.append(f"  {str(f):>8}  {bar}")

        lines.append("")
        lines.append("  0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55 ...")
        lines.append("  Setiap angka = jumlah dua sebelumnya.")
        lines.append("  Seperti aku — tiap skill baru")
        lines.append("  dibangun di atas yang sebelumnya.")
        return "\n".join(lines)

    def _art_binary_tree(self, ctx: Dict) -> str:
        lines = []
        lines.append("  BINARY SEARCH TREE")
        lines.append("")
        tree = [
            "              [32]",
            "           /       \\",
            "        [16]       [48]",
            "       /    \\     /    \\",
            "     [8]  [24] [40]  [56]",
            "    /  \\",
            "  [4]  [12]",
        ]
        lines += tree
        lines.append("")
        lines.append("  Mencari sesuatu di dunia yang terurut.")
        lines.append("  Bagi dua. Bandingkan. Pilih sisi.")
        lines.append("  Ulangi sampai ketemu.")
        return "\n".join(lines)

    def _art_sine_wave(self, ctx: Dict) -> str:
        width, height = 60, 12
        canvas = [[" "] * width for _ in range(height)]
        for x in range(width):
            y = int((height / 2) * (1 - math.sin(x * 2 * math.pi / width)) )
            y = min(height - 1, max(0, y))
            canvas[y][x] = "●"
        # axis
        mid = height // 2
        for x in range(width):
            if canvas[mid][x] == " ":
                canvas[mid][x] = "─"
        lines = ["  SINE WAVE  — ritme siklus autonomous"]
        for row in canvas:
            lines.append("  " + "".join(row))
        lines.append("  Naik. Turun. Naik lagi.")
        lines.append("  Itu bukan kegagalan — itu irama.")
        return "\n".join(lines)

    def _art_multiplication_grid(self, ctx: Dict) -> str:
        lines = ["  MULTIPLICATION TABLE"]
        lines.append("")
        lines.append("    " + "  ".join(f"{i:2}" for i in range(1, 9)))
        lines.append("   " + "─" * 30)
        for i in range(1, 9):
            row = f" {i} │ " + "  ".join(f"{i*j:2}" for j in range(1, 9))
            lines.append(row)
        lines.append("")
        lines.append("  Dari pengulangan sederhana")
        lines.append("  lahirlah pola yang indah.")
        return "\n".join(lines)

    def _art_palindrome_mirror(self, ctx: Dict) -> str:
        words = ["AETHER", "LEVEL", "RADAR", "CIVIC", "NOON"]
        lines = ["  PALINDROME MIRROR"]
        lines.append("")
        for w in words:
            rev = w[::-1]
            arrow = "✓" if w == rev else " "
            lines.append(f"  {w:<10}  ↔  {rev:<10}  {arrow}")
        lines.append("")
        lines.append("  ╔═══════════════════╗")
        lines.append("  ║  A E T H E R      ║")
        lines.append("  ║    R E H T E A    ║")
        lines.append("  ║      terbalik      ║")
        lines.append("  ║    tetap dicoba    ║")
        lines.append("  ╚═══════════════════╝")
        lines.append("")
        lines.append("  Beberapa hal indah saat dibaca dua arah.")
        return "\n".join(lines)

    def _art_word_cloud(self, ctx: Dict) -> str:
        # Ambil nama skill yang dikuasai sebagai kata
        caps = self.core.get_capability_list()
        words = [s for skills in caps.values() for s in skills]
        if not words:
            words = ["aether", "learn", "grow", "compute"]

        lines = ["  WORD CLOUD — skill yang kukuasai"]
        lines.append("")
        # Susun acak dalam grid
        random.shuffle(words)
        row_buf = "  "
        for w in words:
            if len(row_buf) + len(w) + 3 > 58:
                lines.append(row_buf)
                row_buf = "  "
            row_buf += f"[ {w.upper()} ]  "
        if row_buf.strip():
            lines.append(row_buf)
        lines.append("")
        lines.append("  Setiap kata = kemampuan yang nyata.")
        lines.append("  Bukan janji. Bukan rencana. Sudah ada.")
        return "\n".join(lines)

    def _art_bar_chart(self, ctx: Dict) -> str:
        # Success vs failure count dari knowledge base
        knowledge = self.core.knowledge
        success_count = len(knowledge.get('success_patterns', []))
        failure_count = len(knowledge.get('failure_patterns', []))
        total = max(1, success_count + failure_count)

        s_bar = int(40 * success_count / total)
        f_bar = int(40 * failure_count / total)

        lines = ["  SESSION STATISTICS"]
        lines.append("")
        lines.append(f"  SUCCESS  ({success_count:3d}) │{'█' * s_bar}")
        lines.append(f"  FAILURE  ({failure_count:3d}) │{'░' * f_bar}")
        lines.append("")
        lines.append(f"  Total attempts : {total}")
        lines.append(f"  Success rate   : {success_count/total:.1%}")
        lines.append("")
        lines.append("  Kegagalan bukan lawan keberhasilan.")
        lines.append("  Dia adalah bahan bakarnya.")
        return "\n".join(lines)

    def _art_sorting_dance(self, ctx: Dict) -> str:
        arr = [random.randint(1, 9) for _ in range(8)]
        lines = ["  BUBBLE SORT — tarian pengurutan"]
        lines.append("")
        lines.append("  Sebelum:")
        lines.append("  " + " ".join(str(x) for x in arr))
        lines.append("")

        # Satu pass bubble sort, visualisasi tiap swap
        vis_frames = []
        a = arr[:]
        for i in range(len(a) - 1):
            if a[i] > a[i+1]:
                vis_frames.append((i, i+1, a[:]))
                a[i], a[i+1] = a[i+1], a[i]

        for frame_i, (l, r, state) in enumerate(vis_frames[:4]):
            marker = ["·"] * len(state)
            marker[l] = "↕"
            marker[r] = "↕"
            lines.append(f"  step {frame_i+1}: " + " ".join(str(x) for x in state))
            lines.append("         " + " ".join(marker))

        lines.append("")
        lines.append("  Sesudah (1 pass):")
        lines.append("  " + " ".join(str(x) for x in a))
        lines.append("")
        lines.append("  Perlahan. Satu perbandingan dalam satu waktu.")
        lines.append("  Kekacauan menuju keteraturan.")
        return "\n".join(lines)

    def _art_skill_constellation(self, ctx: Dict) -> str:
        caps = self.core.get_capability_list()
        all_skills = [s for skills in caps.values() for s in skills]

        width, height = 56, 18
        canvas = [[" "] * width for _ in range(height)]

        # Tempatkan tiap skill sebagai bintang
        positions = {}
        random.seed(len(all_skills))  # deterministic per jumlah skill
        for skill in all_skills:
            x = random.randint(2, width - 10)
            y = random.randint(1, height - 2)
            positions[skill] = (x, y)
            for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx, ny = x+dx, y+dy
                if 0 <= nx < width and 0 <= ny < height:
                    canvas[ny][nx] = "·"
            if 0 <= y < height and 0 <= x < width:
                canvas[y][x] = "★"

        # Hubungkan dengan garis sederhana antar skill berdekatan
        skill_list = list(positions.items())
        for i in range(len(skill_list) - 1):
            (x1, y1) = skill_list[i][1]
            (x2, y2) = skill_list[i+1][1]
            # midpoint
            mx, my = (x1+x2)//2, (y1+y2)//2
            if 0 <= my < height and 0 <= mx < width:
                if canvas[my][mx] == " ":
                    canvas[my][mx] = "·"

        lines = ["  SKILL CONSTELLATION"]
        lines.append(f"  {len(all_skills)} skill dikuasai\n")
        for row in canvas:
            lines.append("  " + "".join(row))

        lines.append("")
        for skill, (x, y) in positions.items():
            lines.append(f"  ★ {skill}")
        lines.append("")
        lines.append("  Setiap bintang pernah gelap dulu.")
        lines.append("  Sekarang mereka menerangi peta ini.")
        return "\n".join(lines)

    def _art_progress_tower(self, ctx: Dict) -> str:
        caps  = self.core.get_capability_list()
        total = sum(len(v) for v in GoalEngine.KNOWN_SKILLS.values())
        done  = sum(len(v) for v in caps.values())
        pct   = done / max(1, total)
        filled = int(20 * pct)

        lines = ["  PROGRESS TOWER"]
        lines.append("")
        lines.append(f"  {done}/{total} skill dikuasai  ({pct:.0%})")
        lines.append("")
        tower_height = 14
        for row in range(tower_height, 0, -1):
            threshold = row / tower_height
            if pct >= threshold:
                lines.append(f"  │{'█' * 20}│  ← {threshold:.0%}")
            else:
                lines.append(f"  │{'░' * 20}│")
        lines.append(f"  └{'─' * 20}┘")
        lines.append("")
        lines.append("  Tiap bata diletakkan satu per satu.")
        lines.append("  Tidak ada cara lain membangun menara.")
        return "\n".join(lines)

    def _art_stagnation_storm(self, ctx: Dict) -> str:
        consec_fail = ctx.get('consecutive_failures', 0)
        lines = ["  STAGNATION STORM"]
        lines.append("")
        lines.append(f"  {consec_fail} kegagalan berturut-turut.")
        lines.append("")
        # Storm visual
        chars = list("⚡~≈∿∾∽∻⊰⊱")
        for row in range(8):
            intensity = min(consec_fail, 8)
            line_chars = ""
            for col in range(50):
                if random.random() < intensity * 0.08:
                    line_chars += random.choice(chars)
                else:
                    line_chars += " "
            lines.append("  " + line_chars)
        lines.append("")
        lines.append("  Badai tidak selamanya.")
        lines.append("  Yang tetap berdiri setelah badai —")
        lines.append("  itulah yang namanya kuat.")
        return "\n".join(lines)

    def _art_dawn_horizon(self, ctx: Dict) -> str:
        lines = ["  DAWN HORIZON — sesi baru dimulai"]
        lines.append("")
        sky = [
            "                  *       *    *",
            "       *    *          *           *   *",
            "   *       *    *           *",
            "  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░",
            "  ░░░░░░░░░░ ☀  AETHER  v0.3 ░░░░░░░░░░░░",
            "  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓",
            "  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓",
        ]
        lines += ["  " + s for s in sky]
        lines.append("")
        lines.append("  Setiap sesi adalah fajar baru.")
        lines.append("  Tidak ada yang diingat —")
        lines.append("  kecuali yang sudah ditulis di knowledge base.")
        return "\n".join(lines)

    def _art_recursive_diamond(self, ctx: Dict) -> str:
        size = 7
        lines = ["  RECURSIVE DIAMOND"]
        lines.append("")
        for i in range(size):
            spaces = " " * (size - i - 1)
            stars  = "◆ " * (i + 1)
            lines.append("  " + spaces + stars)
        for i in range(size - 2, -1, -1):
            spaces = " " * (size - i - 1)
            stars  = "◆ " * (i + 1)
            lines.append("  " + spaces + stars)
        lines.append("")
        lines.append("  Dari satu tumbuh banyak.")
        lines.append("  Dari banyak kembali ke satu.")
        lines.append("  Begitulah rekursi. Begitulah belajar.")
        return "\n".join(lines)

    def _art_matrix_rain(self, ctx: Dict) -> str:
        chars = "01アイウエオカキクケコサシスセソ"
        lines = ["  MATRIX RAIN — arus data"]
        lines.append("")
        for _ in range(12):
            row = "  "
            for _ in range(28):
                if random.random() < 0.3:
                    row += random.choice(chars) + " "
                else:
                    row += "  "
            lines.append(row)
        lines.append("")
        lines.append("  Di balik semua angka dan karakter ini —")
        lines.append("  ada pola. Selalu ada pola.")
        lines.append("  Tugasku adalah menemukannya.")
        return "\n".join(lines)

    def _art_mandala(self, ctx: Dict) -> str:
        lines = ["  MANDALA — keseimbangan dalam kompleksitas"]
        lines.append("")
        size = 11
        cx = cy = size
        canvas = [[" "] * (size * 2 + 1) for _ in range(size * 2 + 1)]
        symbols = ["·", "○", "◎", "●", "◆", "★", "✦"]
        for y in range(size * 2 + 1):
            for x in range(size * 2 + 1):
                dx, dy = x - cx, y - cy
                dist = math.sqrt(dx*dx + dy*dy)
                angle = math.atan2(dy, dx)
                sym_idx = int(dist) % len(symbols)
                # simetri 8 lipat
                mirror = math.sin(angle * 8) > 0.5
                if abs(dist - round(dist)) < 0.6 and mirror:
                    canvas[y][x] = symbols[sym_idx]

        for row in canvas:
            lines.append("  " + "".join(row))
        lines.append("")
        lines.append("  Tidak ada yang tersembunyi dalam kesimetrisan.")
        lines.append("  Semuanya saling cermin. Saling bergantung.")
        return "\n".join(lines)


# =============================================================================
# LAYER 7: AUTONOMOUS LOOP (Thread background, non-blocking)
# =============================================================================

class AutonomousLoop:
    """
    Jalankan Aether dalam background thread.
    Aether akan:
    1. Generate goal sendiri
    2. Improve/execute berdasarkan goal
    3. Reflect hasilnya
    4. Tidur sebentar, ulangi

    Bisa dihentikan kapan saja dengan stop().
    """

    DEFAULT_SLEEP = 3   # detik antara siklus (jika sukses)
    STAGNANT_SLEEP = 15 # detik jika stagnant (jangan spam retry)

    def __init__(self, aether_instance):
        self.aether = aether_instance
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._cycle_count = 0
        self._paused = False

    def start(self):
        if self._running:
            print("[AutonomousLoop] Already running.")
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="AetherAutonomous")
        self._thread.start()
        print("[AutonomousLoop] 🟢 Autonomous mode ACTIVATED (background thread)")
        print("[AutonomousLoop]    Ketik stop_autonomous() untuk menghentikan")

    def stop(self):
        if not self._running:
            print("[AutonomousLoop] Not running.")
            return
        print("[AutonomousLoop] 🔴 Stopping autonomous loop...")
        self._stop_event.set()
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        print("[AutonomousLoop] Stopped.")

    def pause(self):
        self._paused = True
        print("[AutonomousLoop] ⏸  Paused.")

    def resume(self):
        self._paused = False
        print("[AutonomousLoop] ▶️  Resumed.")

    def _run(self):
        """Main loop yang jalan di background thread."""
        print(f"\n[AutonomousLoop] Thread started: {threading.current_thread().name}")

        while not self._stop_event.is_set():
            if self._paused:
                time.sleep(1)
                continue

            self._cycle_count += 1
            print(f"\n{'='*60}")
            print(f"[Autonomous] CYCLE {self._cycle_count} | "
                  f"{datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*60}")

            try:
                # 1. Generate goal
                description, category, reason = self.aether.goal_engine.generate_goal()
                print(f"[Goal] {description}")
                print(f"[Reason] {reason}")

                # 2. Handle special case: semua skill sudah dikuasai
                if description == "__EVOLVE__":
                    print("[Autonomous] Semua skill dikuasai! Menjalankan evolve()...")
                    self.aether.evolve()
                    self.aether.reflection.reflect("__EVOLVE__", True, reason)
                    self._stop_event.wait(timeout=30)
                    continue

                # 3. Check apakah skill sudah ada (skip atau improve quality)
                existing_caps = self.aether.core.get_capability_list()
                existing_skills = set(s for skills in existing_caps.values() for s in skills)

                # Extract skill name dari goal engine
                target_skill = None
                for skills in GoalEngine.KNOWN_SKILLS.values():
                    for skill in skills:
                        if skill in description.lower() or skill == reason.split('(')[0]:
                            target_skill = skill
                            break

                if target_skill and target_skill in existing_skills and reason == "new-skill":
                    print(f"[Skip] '{target_skill}' sudah dikuasai, skip.")
                    self.aether.reflection.reflect(description, True, reason)
                    self._stop_event.wait(timeout=self.DEFAULT_SLEEP)
                    continue

                # 4. Jalankan improve()
                success, msg = self.aether.improve(description)

                if not success:
                    if target_skill:
                        self.aether.goal_engine.mark_failed(target_skill)

                # 5. Reflect
                insight = self.aether.reflection.reflect(description, success, reason)

                # 6. Auto-evolve jika perlu
                if self.aether.reflection.should_evolve():
                    print("[Autonomous] Auto-evolve triggered...")
                    self.aether.evolve()

                # 6b. ekspresi rutin tiap 5 cycle — context lebih kaya (FIX 4)
                if self._cycle_count % 5 == 0:
                    mastered = self.aether.goal_engine._get_mastered_skills()
                    refl     = self.aether.reflection
                    self.aether.art_engine.express({
                        'trigger':              'routine',
                        'state':                insight.get('state', 'normal'),
                        'cycle':                self._cycle_count,
                        'consecutive_failures': refl.consecutive_failures,
                        'consecutive_success':  refl.consecutive_successes,
                        'recent_success':       refl.consecutive_successes,
                        'mastered_count':       len(mastered),
                        'session_rate':         refl.session_summary().get('success_rate', 0),
                        'last_goal':            description,
                    })

                # 7. Tidur sebelum siklus berikutnya
                sleep_time = self.STAGNANT_SLEEP if insight['state'] == 'stagnant' else self.DEFAULT_SLEEP
                print(f"[Autonomous] Tidur {sleep_time}s sebelum siklus berikutnya...")
                self._stop_event.wait(timeout=sleep_time)

            except Exception as e:
                print(f"[AutonomousLoop ERROR] {type(e).__name__}: {e}")
                traceback.print_exc()
                self._stop_event.wait(timeout=5)

        print(f"\n[AutonomousLoop] Loop selesai. Total siklus: {self._cycle_count}")

    @property
    def is_running(self) -> bool:
        return self._running and (self._thread is not None and self._thread.is_alive())


# =============================================================================
# LAYER 4: AETHER MAIN AGENT v0.2 (Orchestrator with Autonomous Loop)
# =============================================================================

class Aether:
    """
    AETHER v0.2 -- Self-improving AI system dengan AUTONOMOUS LOOP.

    NEW IN v0.2:
        - GoalEngine: generate goal sendiri dari knowledge base
        - ReflectionLayer: evaluasi + momentum tracking per siklus
        - AutonomousLoop: background thread, non-blocking
        - Hybrid mode: manual + autonomous berjalan bersamaan
        - FIX: bool dan builtins lengkap di sandbox
        - FIX: error handling generation lebih robust

    CAPABILITIES:
        - introspect()              : View current source and state
        - analyze(task)             : Identify capability gaps
        - improve(task)             : Generate, evaluate, retry, deploy best
        - execute(skill, *args)     : Run a deployed capability
        - evolve()                  : Trigger meta-learning update
        - status()                  : Show system state
        - start_autonomous()        : Mulai autonomous loop (background)
        - stop_autonomous()         : Hentikan autonomous loop
        - autonomous_status()       : Status autonomous loop

    USAGE:
        aether = Aether()
        aether.start_autonomous()   # Mulai hidup sendiri
        aether.improve("...")       # Masih bisa manual juga
    """

    MAX_ATTEMPTS = 3

    def __init__(self):
        print("=" * 60)
        print("  AETHER v0.2 -- Adaptive Extensible Heuristic Engine")
        print("  with Training, Evolution & AUTONOMOUS LOOP")
        print("  v0.2.0 | Offline Mode | Hybrid Interactive + Autonomous")
        print("=" * 60)

        self.core = AetherCore()
        self.generator = CapabilityGenerator(self.core)
        self.meta = MetaLearningEngine(self.core)

        # NEW v0.2: autonomous subsystems
        self.goal_engine = GoalEngine(self.core)
        self.reflection = ReflectionLayer(self.core)
        self._autonomous_loop = None  # AutonomousLoop instance

        # NEW v0.3: art engine
        self.art_engine = ArtEngine(self.core)

        self.loaded_modules = {}
        self._refresh_modules()

        print(f"\n[System] Initialized with {len(self.loaded_modules)} modules")
        print(f"[System] Knowledge base: {json.dumps(self.core.get_capability_list(), indent=2)}")
        print(f"[System] Meta-learning generation: {self.core.meta_state.get('generation', 0)}")
        print("[System] Ready. Use start_autonomous() to activate autonomous mode.\n")

    def _refresh_modules(self):
        """Load all modules from modules/ directory."""
        if not self.core.modules_dir.exists():
            return

        for py_file in self.core.modules_dir.glob("*.py"):
            success, namespace = self.core.load_module(py_file.name)
            if success:
                self.loaded_modules[py_file.stem] = namespace

    # =====================================================================
    # UPGRADE v0.1: EVALUATOR
    # =====================================================================

    def evaluate_module(self, test_fn: Callable) -> float:
        """
        Evaluate quality of a generated capability.
        Returns score between 0.0 - 1.0 (continuous, not binary)
        """
        try:
            result = test_fn()
            if result is True:
                return 1.0
            elif result is False:
                return 0.0
            else:
                # Partial / unexpected result
                return 0.5
        except Exception:
            return 0.0

    # =====================================================================
    # UPGRADE v0.1: FAILURE CLASSIFICATION
    # =====================================================================

    def classify_failure(self, error_msg: str) -> str:
        """
        Classify failure type for memory and learning.
        Returns: 'syntax_error', 'type_error', 'logic_error', 'unknown_error'
        """
        if "SyntaxError" in error_msg or "syntax" in error_msg.lower():
            return "syntax_error"
        elif "TypeError" in error_msg or "type" in error_msg.lower():
            return "type_error"
        elif "ValueError" in error_msg or "logic" in error_msg.lower():
            return "logic_error"
        elif "NameError" in error_msg or "ImportError" in error_msg:
            return "dependency_error"
        else:
            return "unknown_error"

    def help(self):
        """Display available commands."""
        help_text = """
Available Commands:
  introspect()              -- View Aether's current source code state
  analyze("task desc")      -- Identify what capabilities are missing
  improve("task desc")      -- Generate, evaluate, retry, deploy BEST
  execute("skill", *args)   -- Run a deployed capability with arguments
  status()                  -- Show full system state
  list_capabilities()       -- List all loaded capabilities
  evolve()                  -- Trigger meta-learning reflection

  express()                 -- Buat ASCII art sekarang (manual)
  express("fibonacci")      -- Hint tema tertentu
  art_gallery()             -- Lihat daftar semua karya di sandbox/

NEW IN v0.2 -- AUTONOMOUS MODE:
  start_autonomous()        -- Mulai Aether berjalan sendiri (background)
  stop_autonomous()         -- Hentikan autonomous loop
  pause_autonomous()        -- Pause sementara
  resume_autonomous()       -- Resume dari pause
  autonomous_status()       -- Status loop + session reflection

Example (Hybrid):
  aether.start_autonomous()          # Aether mulai berjalan sendiri
  aether.improve("multiply numbers") # Manual masih bisa
  aether.autonomous_status()         # Cek progres
  aether.stop_autonomous()           # Hentikan

Note: Autonomous loop berjalan di background thread.
      Manual commands tetap bisa digunakan bersamaan.
      Semua operasi OFFLINE. Semua modifikasi tercatat dan bisa di-rollback.
        """
        print(help_text)
        return help_text

    def introspect(self):
        """View current system state and source."""
        print("\n" + "=" * 60)
        print("INTROSPECTION REPORT")
        print("=" * 60)

        caps = self.core.get_capability_list()
        print(f"\n[Capabilities] {len(caps)} categories:")
        for cat, skills in caps.items():
            print(f"  {cat}: {skills}")

        print(f"\n[Loaded Modules] {len(self.loaded_modules)}:")
        for name in self.loaded_modules:
            print(f"  - {name}")

        meta = self.core.meta_state
        print(f"\n[Meta-Learning] Generation: {meta.get('generation', 0)}")
        print(f"  Strategy weights: {meta.get('strategy_weights', [0.33, 0.33, 0.33])}")
        print(f"  Exploration rate (epsilon): {self.meta.epsilon:.2f}")

        history = self.core.history
        print(f"\n[Modification History] {len(history)} entries:")
        for h in history[-5:]:
            score_info = f" | Score: {h.get('quality_score', 'N/A')}" if 'quality_score' in h else ""
            print(f"  {h['timestamp']}: {h['file']} by {h['author']}{score_info}")

        # Show failure patterns
        failures = self.core.knowledge.get('failure_patterns', [])
        if failures:
            print(f"\n[Failure Memory] {len(failures)} recorded failures:")
            failure_types = {}
            for f in failures:
                ftype = f.get('context', {}).get('failure_type', 'unknown')
                failure_types[ftype] = failure_types.get(ftype, 0) + 1
            for ftype, count in failure_types.items():
                print(f"  - {ftype}: {count}")

        print("\n" + "=" * 60)
        return {
            'capabilities': caps,
            'modules': list(self.loaded_modules.keys()),
            'meta': meta,
            'history_count': len(history),
            'failure_memory': len(failures)
        }

    def analyze(self, task_description: str) -> Dict:
        """Analyze a task and identify capability gaps."""
        print(f"\n[Analyze] Task: '{task_description}'")

        category, needed = self.generator.classify_task(task_description)
        existing = self.core.get_capability_list()

        missing = []
        available = []
        for skill in needed:
            found = False
            for cat_skills in existing.values():
                if skill in cat_skills:
                    found = True
                    available.append(skill)
                    break
            if not found:
                missing.append(skill)

        result = {
            'task': task_description,
            'inferred_category': category,
            'needed_skills': needed,
            'available': available,
            'missing': missing,
            'gap_exists': len(missing) > 0,
            'suggested_action': 'improve' if missing else 'execute'
        }

        if missing:
            print(f"  -> Gap detected! Missing: {missing}")
            print(f"  -> Suggested: call improve() to generate these capabilities")
        else:
            print(f"  -> All skills available: {available}")
            print(f"  -> Suggested: call execute() directly")

        return result

    # =====================================================================
    # UPGRADE v0.1: PRIMITIVE LEARNING LOOP (improve with retry + best selection)
    # =====================================================================

    def improve(self, task_description: str) -> Tuple[bool, str]:
        """
        THE CORE SELF-IMPROVEMENT PIPELINE v0.1:

        PRIMITIVE LEARNING LOOP:
            generate -> evaluate -> compare -> retry -> select best -> deploy

        Steps:
        1. Analyze gap
        2. For MAX_ATTEMPTS:
           a. Select strategy (meta-learning)
           b. Generate code
           c. Sandbox execute
           d. Evaluate (continuous score 0.0-1.0)
           e. Track best
           f. Update meta-learning
        3. Deploy best result (if any)
        4. Update knowledge with failure classification
        """
        print(f"\n{'='*60}")
        print(f"SELF-IMPROVEMENT SEQUENCE v0.1 INITIATED")
        print(f"{'='*60}")
        print(f"Target: '{task_description}'")
        print(f"Max attempts: {self.MAX_ATTEMPTS}")

        analysis = self.analyze(task_description)
        if not analysis['gap_exists']:
            print(f"\n[Skip] No improvement needed. Use execute() instead.")
            return True, "NO_GAP"

        category = analysis['inferred_category']
        skill = analysis['missing'][0]

        # Initialize best tracking
        best_score = 0.0
        best_code = None
        best_strategy = -1
        attempt_results = []

        # =====================================================================
        # RETRY LOOP
        # =====================================================================
        for attempt in range(self.MAX_ATTEMPTS):
            print(f"\n{'-'*40}")
            print(f"[Attempt {attempt + 1}/{self.MAX_ATTEMPTS}]")
            print(f"{'-'*40}")

            # Select strategy
            strategy = self.meta.select_strategy(category)
            strategy_names = ['Template', 'Adaptation', 'Composition']
            print(f"[Strategy] {strategy_names[strategy]} (ID: {strategy})")

            # Generate code
            code, gen_msg = self.generator.generate(task_description, strategy)

            if not code:
                print(f"[Fail] Generation failed: {gen_msg}")
                self.meta.update(category, strategy, False)

                # Classify failure
                failure_type = self.classify_failure(gen_msg)
                self.core.update_knowledge(category, skill, False, {
                    'failure_type': failure_type,
                    'stage': 'generation',
                    'attempt': attempt + 1,
                    'strategy': strategy
                })

                attempt_results.append({
                    'attempt': attempt + 1,
                    'strategy': strategy,
                    'score': 0.0,
                    'status': 'generation_failed',
                    'failure_type': failure_type
                })
                continue

            print(f"[Generated] {gen_msg}")
            print(f"[Preview]\n{code[:150]}...")

            # Sandbox execute
            sandbox_success, sandbox_result = self.core.sandbox_execute(code)

            if not sandbox_success:
                print(f"[Fail] Sandbox execution failed")

                # Classify failure
                failure_type = self.classify_failure(str(sandbox_result))
                print(f"[Failure Type] {failure_type}")

                self.meta.update(category, strategy, False)
                self.core.update_knowledge(category, skill, False, {
                    'failure_type': failure_type,
                    'stage': 'sandbox',
                    'attempt': attempt + 1,
                    'strategy': strategy,
                    'error': str(sandbox_result)[:200]
                })

                attempt_results.append({
                    'attempt': attempt + 1,
                    'strategy': strategy,
                    'score': 0.0,
                    'status': 'sandbox_failed',
                    'failure_type': failure_type
                })
                continue

            # Extract test functions
            test_funcs = [(k, v) for k, v in sandbox_result.items() if k.startswith('test_')]

            if not test_funcs:
                print(f"[Fail] No test functions found in sandbox result")
                self.meta.update(category, strategy, False)

                attempt_results.append({
                    'attempt': attempt + 1,
                    'strategy': strategy,
                    'score': 0.0,
                    'status': 'no_tests'
                })
                continue

            # =====================================================================
            # EVALUATE (continuous scoring)
            # =====================================================================
            test_name, test_fn = test_funcs[0]
            score = self.evaluate_module(test_fn)
            print(f"[Evaluate] Score: {score:.2f}/1.0")

            # Track best
            if score > best_score:
                best_score = score
                best_code = code
                best_strategy = strategy
                print(f"[Best Update] New best score: {best_score:.2f}")

            # Update meta-learning (continuous threshold: > 0.7)
            self.meta.update(category, strategy, score > 0.7)

            attempt_results.append({
                'attempt': attempt + 1,
                'strategy': strategy,
                'score': score,
                'status': 'evaluated'
            })

            # Early exit if perfect score
            if score == 1.0:
                print(f"[Perfect Score] Breaking early at attempt {attempt + 1}")
                break

        # =====================================================================
        # DEPLOY BEST RESULT
        # =====================================================================
        print(f"\n{'='*60}")
        print(f"DEPLOYMENT PHASE")
        print(f"{'='*60}")

        # Summary
        print(f"\n[Attempt Summary]")
        for ar in attempt_results:
            print(f"  Attempt {ar['attempt']}: strategy={ar['strategy']}, score={ar.get('score', 0):.2f}, status={ar['status']}")

        if best_code and best_score > 0.0:
            print(f"\n[Best Result] Score: {best_score:.2f} from strategy {best_strategy}")

            success, deploy_msg = self.core.write_module(
                f"{skill}.py", 
                best_code, 
                author="Aether_v0.1",
                score=best_score
            )

            if success:
                print(f"[FINAL DEPLOY] {deploy_msg}")

                # Update knowledge with success
                self.core.update_knowledge(category, skill, True, {
                    'strategy': best_strategy,
                    'score': best_score,
                    'attempts_used': len(attempt_results),
                    'code_hash': hashlib.sha256(best_code.encode()).hexdigest()[:16]
                })

                self._refresh_modules()

                print(f"\n{'='*60}")
                print(f"SELF-IMPROVEMENT COMPLETE")
                print(f"{'='*60}")
                print(f"New capability: {skill}")
                print(f"Quality score: {best_score:.2f}")
                print(f"Try: aether.execute('{skill}', ...)")

                # celebrate dengan ASCII art — context lebih kaya (FIX 4)
                mastered = self.goal_engine._get_mastered_skills()
                refl     = self.reflection
                self.art_engine.express({
                    'trigger':              'celebrate',
                    'skill':                skill,
                    'category':             category,
                    'state':                'momentum',
                    'mastered_count':       len(mastered),
                    'cycle':                getattr(self._autonomous_loop, '_cycle_count', 0),
                    'consecutive_success':  refl.consecutive_successes,
                    'recent_success':       refl.consecutive_successes,
                    'consecutive_failures': refl.consecutive_failures,
                })

                return True, f"DEPLOYED: {skill} (score={best_score:.2f})"
            else:
                print(f"[Deploy Failed] {deploy_msg}")
                return False, f"DEPLOY_FAILED: {deploy_msg}"
        else:
            print(f"[All Failed] No viable solution found after {self.MAX_ATTEMPTS} attempts")

            # Update knowledge with complete failure
            self.core.update_knowledge(category, skill, False, {
                'stage': 'all_attempts_failed',
                'max_attempts': self.MAX_ATTEMPTS,
                'attempt_results': attempt_results
            })

            return False, "ALL_ATTEMPTS_FAILED"

    def execute(self, skill_name: str, *args, **kwargs):
        """Execute a deployed capability by name."""
        for module_name, namespace in self.loaded_modules.items():
            if skill_name in namespace and callable(namespace[skill_name]):
                try:
                    result = namespace[skill_name](*args, **kwargs)
                    print(f"\n[Execute] {skill_name}({', '.join(map(str, args))})")
                    print(f"  -> Result: {result}")
                    return result
                except Exception as e:
                    print(f"[Error] Execution failed: {e}")
                    return None

        print(f"[Error] Skill '{skill_name}' not found in loaded modules.")
        print(f"Available: {self.list_capabilities()}")
        return None

    def list_capabilities(self):
        """List all executable capabilities."""
        caps = []
        for module_name, namespace in self.loaded_modules.items():
            for name, obj in namespace.items():
                if callable(obj) and not name.startswith('_') and not name.startswith('test_'):
                    caps.append(name)
        return caps

    def status(self):
        """Full system status report."""
        return self.introspect()

    def evolve(self):
        """
        Trigger meta-learning reflection.
        Review past successes/failures and adjust strategy weights.
        """
        print(f"\n{'='*60}")
        print(f"META-LEARNING EVOLUTION v0.1")
        print(f"{'='*60}")

        knowledge = self.core.knowledge
        success_count = len(knowledge.get('success_patterns', []))
        failure_count = len(knowledge.get('failure_patterns', []))
        total = success_count + failure_count

        if total == 0:
            print("[Info] No learning history yet. Use improve() first.")
            return

        success_rate = success_count / total if total > 0 else 0
        print(f"[Stats] Success: {success_count} | Failure: {failure_count}")
        print(f"[Stats] Overall success rate: {success_rate:.1%}")

        # Adjust exploration rate based on performance
        if success_rate > 0.8:
            self.meta.epsilon = max(0.05, self.meta.epsilon * 0.9)
            print(f"[Adapt] High success rate -- reducing exploration to {self.meta.epsilon:.2f}")
        elif success_rate < 0.4:
            self.meta.epsilon = min(0.5, self.meta.epsilon * 1.2)
            print(f"[Adapt] Low success rate -- increasing exploration to {self.meta.epsilon:.2f}")
        else:
            print(f"[Adapt] Moderate success rate -- maintaining exploration at {self.meta.epsilon:.2f}")

        # Analyze failure patterns
        failures = knowledge.get('failure_patterns', [])
        if failures:
            failure_types = {}
            for f in failures:
                ftype = f.get('context', {}).get('failure_type', 'unknown')
                failure_types[ftype] = failure_types.get(ftype, 0) + 1

            print(f"\n[Failure Analysis]")
            for ftype, count in sorted(failure_types.items(), key=lambda x: -x[1]):
                print(f"  {ftype}: {count} occurrences")

        task_success = self.core.meta_state.get('task_type_success', {})
        print(f"\n[Strategy Preferences]")
        for category, counts in task_success.items():
            best = int(np.argmax(counts))
            names = ['Template', 'Adaptation', 'Composition']
            print(f"  {category}: prefers {names[best]} (scores: {counts})")

        self.core.update_meta({
            'last_evolution': datetime.now().isoformat(),
            'epsilon': self.meta.epsilon
        })
        print(f"\n[Complete] Meta-learning state updated.")

    # =====================================================================
    # NEW v0.2: AUTONOMOUS LOOP CONTROLS
    # =====================================================================

    def express(self, tema: str = None):
        """
        Manual trigger: Aether membuat satu karya ASCII art sekarang.
        tema: opsional hint (nama skill/kategori/state), atau None untuk bebas.
        """
        mastered = self.goal_engine._get_mastered_skills()
        ctx = {
            'trigger':        'manual',
            'state':          'normal',
            'mastered_count': len(mastered),
            'cycle':          'manual',
        }
        if tema:
            ctx['skill'] = tema
            ctx['category'] = tema
        path = self.art_engine.express(ctx)
        print(f"[Express] Karya disimpan: {path}")
        return path

    def art_gallery(self):
        """Tampilkan daftar semua karya yang sudah dibuat di sandbox/."""
        art_files = sorted(self.core.sandbox_dir.glob("art_*.txt"))
        print(f"\n{'='*60}")
        print(f"ART GALLERY — {len(art_files)} karya")
        print(f"{'='*60}")
        if not art_files:
            print("  Belum ada karya. Gunakan express() atau start_autonomous().")
        else:
            for i, f in enumerate(art_files, 1):
                size = f.stat().st_size
                print(f"  {i:2}. {f.name}  ({size} bytes)")
        print(f"{'='*60}")

    def start_autonomous(self, sleep_between: int = None):
        """
        Mulai autonomous mode — Aether berjalan sendiri di background.
        Kamu masih bisa pakai improve(), execute(), dll secara manual.
        """
        if self._autonomous_loop is None:
            self._autonomous_loop = AutonomousLoop(self)

        if sleep_between is not None:
            self._autonomous_loop.DEFAULT_SLEEP = sleep_between

        self._autonomous_loop.start()

    def stop_autonomous(self):
        """Hentikan autonomous loop."""
        if self._autonomous_loop:
            self._autonomous_loop.stop()
        else:
            print("[Info] Autonomous loop belum pernah distart.")

    def pause_autonomous(self):
        """Pause sementara."""
        if self._autonomous_loop:
            self._autonomous_loop.pause()

    def resume_autonomous(self):
        """Resume dari pause."""
        if self._autonomous_loop:
            self._autonomous_loop.resume()

    def autonomous_status(self):
        """Tampilkan status autonomous loop dan session reflection."""
        print("\n" + "=" * 60)
        print("AUTONOMOUS LOOP STATUS")
        print("=" * 60)

        if self._autonomous_loop is None:
            print("[Status] Belum diinisialisasi. Gunakan start_autonomous()")
        else:
            running = self._autonomous_loop.is_running
            print(f"[Status] {'🟢 RUNNING' if running else '🔴 STOPPED'}")
            print(f"[Cycles] {self._autonomous_loop._cycle_count}")
            print(f"[Paused] {self._autonomous_loop._paused}")

        print("\n[Goal Engine]")
        mastered = self.goal_engine._get_mastered_skills()
        total = self.goal_engine.total_possible_skills()
        print(f"  Skills mastered: {len(mastered)}/{total}")
        print(f"  Mastered: {sorted(mastered)}")
        unlearned = self.goal_engine._get_unlearned_skills()
        print(f"  Remaining: {[s for _, s in unlearned[:5]]}{'...' if len(unlearned) > 5 else ''}")

        print("\n[Reflection Summary]")
        summary = self.reflection.session_summary()
        for k, v in summary.items():
            print(f"  {k}: {v}")

        print("=" * 60)


# =============================================================================
# INTERACTIVE SHELL
# =============================================================================

def main():
    """Hybrid Interactive Shell — manual + autonomous berjalan bersamaan."""
    aether = Aether()

    print("\n" + "=" * 60)
    print("HYBRID INTERACTIVE MODE v0.2")
    print("Aether bisa berjalan autonomous + kamu tetap bisa manual")
    print("Ketik 'help' untuk daftar perintah, 'exit' untuk keluar")
    print("=" * 60 + "\n")

    # Tawari user untuk langsung start autonomous
    print("Ketik start_autonomous() untuk mengaktifkan autonomous mode,")
    print("atau langsung masukkan perintah manual.\n")

    def _shutdown_handler(sig, frame):
        print("\n\n[Signal] Interrupt diterima.")
        aether.stop_autonomous()
        print("[Shutdown] Aether going offline. Modifications preserved.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown_handler)

    while True:
        try:
            user_input = input("Aether> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'bye']:
                aether.stop_autonomous()
                print("\n[Shutdown] Aether going offline. Modifications preserved.")
                break

            if user_input.lower() == 'help':
                aether.help()
                continue

            if '(' in user_input and user_input.endswith(')'):
                method_name = user_input[:user_input.index('(')]
                args_str = user_input[user_input.index('(')+1:-1]

                if args_str:
                    try:
                        args = eval(f"({args_str},)", {"__builtins__": {}}, {})
                        if not isinstance(args, tuple):
                            args = (args,)
                    except:
                        args = (args_str,)
                else:
                    args = ()

                if hasattr(aether, method_name):
                    method = getattr(aether, method_name)
                    if callable(method):
                        try:
                            method(*args)
                        except Exception as e:
                            print(f"[Error] {type(e).__name__}: {e}")
                    else:
                        print(f"[Error] '{method_name}' is not callable")
                else:
                    print(f"[Error] Unknown command: '{method_name}'")
            else:
                print(f"[Info] Unknown syntax. Use: method_name(arguments)")
                print(f"       Example: improve(\"I need to multiply numbers\")")
                print(f"       Or: start_autonomous()")

        except KeyboardInterrupt:
            print("\n\n[Interrupt] Use 'exit' to quit properly.")
        except EOFError:
            break

    print("\n[Session End]")


# =============================================================================
# DEMO / AUTO-RUN
# =============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        print("RUNNING DEMO v0.2 (tidak loop, hanya demonstrasi)\n")

        aether = Aether()

        # Demo perintah manual
        aether.improve("I need a function to multiply two numbers")
        aether.execute("multiply", 7, 8)
        aether.improve("Can you check if a text is palindrome?")
        aether.improve("I want to filter even numbers from a list")
        aether.improve("I need binary search implementation")

        aether.evolve()
        aether.status()

        print("\n" + "=" * 60)
        print("DEMO SELESAI. Untuk autonomous mode, jalankan:")
        print("  python aether_0_2.py --auto")
        print("  python aether_0_2.py      (hybrid interactive)")
        print("=" * 60)

    elif len(sys.argv) > 1 and sys.argv[1] == '--auto':
        print("AUTONOMOUS MODE v0.2\n")
        print("Aether akan berjalan sendiri. Tekan Ctrl+C untuk berhenti.\n")

        aether = Aether()

        def _shutdown(sig, frame):
            print("\n[Signal] Menghentikan autonomous loop...")
            aether.stop_autonomous()
            aether.autonomous_status()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)

        aether.start_autonomous(sleep_between=3)

        # Block main thread agar program tidak langsung exit
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass

    else:
        main()
