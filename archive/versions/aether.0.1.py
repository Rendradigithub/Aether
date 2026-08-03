#!/usr/bin/env python3
# =============================================================================
# AETHER v0.1: Adaptive Extensible Heuristic Engine with Training & Evolution
# =============================================================================
# UPGRADES from v1.0.0:
#   - Continuous Evaluator (0.0 - 1.0 score)
#   - Retry Loop with multiple attempts
#   - Failure Classification (syntax, type, logic, unknown)
#   - Best Result Selection (deploy highest score)
#   - Primitive Learning Loop architecture
#
# CORE PRINCIPLES:
#   1. No consciousness -- pure computation, pattern matching, optimization
#   2. No internet required -- fully offline after initial setup
#   3. Safety layers -- core engine protected, sandbox testing mandatory
#   4. Transparent -- all modifications logged, inspectable, reversible
#
# USAGE:
#   python aether_0_1.py --demo     # Run autonomous demonstration
#   python aether_0_1.py            # Interactive mode
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
            'str': str, 'int': int, 'float': float,
            'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
            'sum': sum, 'min': min, 'max': max,
            'abs': abs, 'round': round,
            'enumerate': enumerate, 'zip': zip,
            'map': map, 'filter': filter,
            'sorted': sorted, 'reversed': reversed,
            'any': any, 'all': all,
            'Exception': Exception, 'TypeError': TypeError,
            'ValueError': ValueError, 'KeyError': KeyError,
            'math': math, 'random': random, 're': re,
            'np': np, 'numpy': np,
            'json': json, 'hashlib': hashlib,
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
# LAYER 4: AETHER MAIN AGENT v0.1 (Orchestrator with Primitive Learning Loop)
# =============================================================================

class Aether:
    """
    AETHER v0.1 -- Self-improving AI system with PRIMITIVE LEARNING LOOP.

    NEW IN v0.1:
        - Continuous Evaluator (0.0 - 1.0 score)
        - Retry Loop with MAX_ATTEMPTS
        - Failure Classification (syntax, type, logic, unknown)
        - Best Result Selection
        - Quality-aware deployment

    CAPABILITIES:
        - introspect()         : View current source and state
        - analyze(task)        : Identify capability gaps
        - improve(task)        : Generate, evaluate, retry, deploy best
        - execute(skill, *args) : Run a deployed capability
        - evolve()             : Trigger meta-learning update
        - status()             : Show system state

    USAGE:
        aether = Aether()
        aether.improve("I need a function to check palindromes")
        result = aether.execute("is_palindrome", "A man a plan a canal Panama")
    """

    MAX_ATTEMPTS = 3

    def __init__(self):
        print("=" * 60)
        print("  AETHER v0.1 -- Adaptive Extensible Heuristic Engine")
        print("  with Training & Evolution Routines")
        print("  v0.1.0 | Offline Mode | English Interface | Primitive Learning Loop")
        print("=" * 60)

        self.core = AetherCore()
        self.generator = CapabilityGenerator(self.core)
        self.meta = MetaLearningEngine(self.core)

        self.loaded_modules = {}
        self._refresh_modules()

        print(f"\n[System] Initialized with {len(self.loaded_modules)} modules")
        print(f"[System] Knowledge base: {json.dumps(self.core.get_capability_list(), indent=2)}")
        print(f"[System] Meta-learning generation: {self.core.meta_state.get('generation', 0)}")
        print("[System] Ready for commands. Type 'help' for assistance.\n")

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

NEW IN v0.1:
  - improve() now uses PRIMITIVE LEARNING LOOP:
      generate -> evaluate -> compare -> retry -> select best -> deploy
  - Continuous scoring (0.0 - 1.0)
  - Failure classification and memory
  - Best result selection (not just first success)

Example:
  aether.improve("I need to multiply two numbers")
  aether.execute("multiply", 4, 5)

Note: All operations are OFFLINE. No internet required.
      All modifications are LOGGED and REVERSIBLE.
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


# =============================================================================
# INTERACTIVE SHELL
# =============================================================================

def main():
    """Interactive Aether shell."""
    aether = Aether()

    print("\n" + "=" * 60)
    print("INTERACTIVE MODE v0.1")
    print("Type 'help' for commands, 'exit' to quit")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("Aether> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ['exit', 'quit', 'bye']:
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

        except KeyboardInterrupt:
            print("\n\n[Interrupt] Use 'exit' to quit properly.")
        except EOFError:
            break

    print("\n[Session End]")


# =============================================================================
# DEMO / AUTO-RUN
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        print("RUNNING AUTONOMOUS DEMONSTRATION v0.1\n")

        aether = Aether()

        # Demo 1: Math capability with retry potential
        aether.improve("I need a function to multiply two numbers")
        aether.execute("multiply", 7, 8)

        # Demo 2: String capability
        aether.improve("Can you check if a text is palindrome?")
        aether.execute("is_palindrome", "radar")

        # Demo 3: Data capability
        aether.improve("I want to filter even numbers from a list")
        aether.execute("filter_even", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

        # Demo 4: Algorithm capability
        aether.improve("I need binary search implementation")
        aether.execute("binary_search", [1, 3, 5, 7, 9, 11], 5)

        # Demo 5: Meta-learning evolution
        aether.evolve()

        # Final status
        aether.status()

        print("\n" + "=" * 60)
        print("DEMONSTRATION COMPLETE")
        print("Check the 'aether_project/' directory for:")
        print("  - modules/     : Generated capabilities")
        print("  - backups/     : Backup files")
        print("  - *.json       : Knowledge and history")
        print("=" * 60)

    else:
        main()
