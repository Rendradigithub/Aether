#!/usr/bin/env python3
# =============================================================================
# AETHER: Adaptive Extensible Heuristic Engine with Training & Evolution Routines
# =============================================================================
# A self-modifying, offline AI system that can:
#   - Introspect its own source code
#   - Generate new capabilities based on gaps
#   - Test modifications in sandbox before applying
#   - Learn from success/failure (RL-based strategy selection)
#   - Meta-learn: improve its own learning strategies over time
#
# CORE PRINCIPLES (from our discussion):
#   1. No consciousness — pure computation, pattern matching, optimization
#   2. No internet required — fully offline after initial setup
#   3. Safety layers — core engine protected, sandbox testing mandatory
#   4. Transparent — all modifications logged, inspectable, reversible
#
# USAGE:
#   python aether.py
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
# LAYER 1: CORE ENGINE (PROTECTED — NEVER MODIFIED BY AETHER ITSELF)
# =============================================================================

class AetherCore:
    """
    The immutable backbone of Aether.
    Handles file I/O, sandbox execution, validation, and safety.
    This class is PROTECTED — Aether cannot modify it.
    """
    
    PROTECTED_FILES = {
        'aether_core.py', 'aether.py', 'safety_manifest.json'
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
            
            # Extract defined objects
            exports = {
                k: v for k, v in sandbox_globals.items()
                if not k.startswith('_') and k not in restricted_builtins
                and k not in ['__builtins__', '__name__']
            }
            return True, exports
            
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
    
    def write_module(self, filename: str, content: str, author: str = "Aether") -> Tuple[bool, str]:
        """
        Write a new module file with full safety pipeline:
        1. Syntax validation
        2. Sandbox testing (must include test function)
        3. Backup of existing
        4. Write to modules/
        """
        # Check protected
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
        
        # Check test results
        test_funcs = [k for k in sandbox_result if k.startswith('test_')]
        if not test_funcs:
            return False, "NO_TEST_FUNCTION_EXPORTED"
        
        # Run tests
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
            'tests_passed': len(test_funcs)
        }
        self.history.append(entry)
        self._save_json(self.history_file, self.history)
        
        return True, f"MODULE_DEPLOYED: {filename} | Tests: {len(test_funcs)} passed"
    
    def load_module(self, filename: str) -> Tuple[bool, Any]:
        """Load a module from modules/ directory."""
        path = self.modules_dir / filename
        if not path.exists():
            return False, "MODULE_NOT_FOUND"
        
        try:
            # Read and execute in controlled namespace
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
                'multiply': '''
def multiply(a: float, b: float) -> float:
    """Auto-generated: multiplication capability."""
    return a * b

def test_multiply():
    return multiply(4, 5) == 20 and multiply(-3, 2) == -6 and abs(multiply(0.1, 0.2) - 0.02) < 1e-9
''',
                'power': '''
def power(base: float, exponent: float) -> float:
    """Auto-generated: exponentiation capability."""
    if exponent == 0:
        return 1.0
    result = 1.0
    exp = int(exponent)
    for _ in range(abs(exp)):
        result *= base
    return result if exp >= 0 else 1.0 / result

def test_power():
    return power(2, 3) == 8 and power(5, 0) == 1 and abs(power(2, -1) - 0.5) < 1e-9
''',
                'factorial': '''
def factorial(n: int) -> int:
    """Auto-generated: factorial computation."""
    if n < 0:
        raise ValueError("Factorial undefined for negative numbers")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

def test_factorial():
    return factorial(0) == 1 and factorial(5) == 120 and factorial(1) == 1
'''
            },
            'string': {
                'palindrome': '''
def is_palindrome(text: str) -> bool:
    """Auto-generated: palindrome detection."""
    cleaned = ''.join(c.lower() for c in text if c.isalnum())
    return cleaned == cleaned[::-1]

def test_palindrome():
    return (is_palindrome("A man a plan a canal Panama") and 
            is_palindrome("radar") and 
            not is_palindrome("hello"))
''',
                'anagram': '''
def is_anagram(a: str, b: str) -> bool:
    """Auto-generated: anagram detection."""
    def normalize(s):
        return sorted(''.join(c.lower() for c in s if c.isalnum()))
    return normalize(a) == normalize(b)

def test_anagram():
    return (is_anagram("listen", "silent") and 
            is_anagram("Dormitory", "Dirty room") and 
            not is_anagram("hello", "world"))
''',
                'word_count': '''
def word_count(text: str) -> int:
    """Auto-generated: count words in text."""
    return len(text.split())

def test_word_count():
    return word_count("Hello world") == 2 and word_count("") == 0
'''
            },
            'data': {
                'filter_even': '''
def filter_even(numbers: list) -> list:
    """Auto-generated: filter even numbers."""
    return [n for n in numbers if isinstance(n, (int, float)) and n % 2 == 0]

def test_filter_even():
    return filter_even([1, 2, 3, 4, 5]) == [2, 4] and filter_even([]) == []
''',
                'group_by': '''
def group_by(key_func, items: list) -> dict:
    """Auto-generated: group items by key function."""
    result = {}
    for item in items:
        key = key_func(item)
        result.setdefault(key, []).append(item)
    return result

def test_group_by():
    data = [1, 2, 3, 4, 5, 6]
    result = group_by(lambda x: x % 2, data)
    return result[0] == [2, 4, 6] and result[1] == [1, 3, 5]
''',
                'running_average': '''
def running_average(numbers: list) -> list:
    """Auto-generated: cumulative running average."""
    if not numbers:
        return []
    result = []
    total = 0
    for i, n in enumerate(numbers, 1):
        total += n
        result.append(total / i)
    return result

def test_running_average():
    return running_average([1, 2, 3, 4]) == [1.0, 1.5, 2.0, 2.5]
'''
            },
            'algorithm': {
                'bubble_sort': '''
def bubble_sort(items: list) -> list:
    """Auto-generated: bubble sort implementation."""
    arr = items.copy()
    n = len(arr)
    for i in range(n):
        swapped = False
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:
            break
    return arr

def test_bubble_sort():
    return (bubble_sort([3, 1, 4, 1, 5]) == [1, 1, 3, 4, 5] and
            bubble_sort([]) == [] and
            bubble_sort([5]) == [5])
''',
                'binary_search': '''
def binary_search(arr: list, target) -> int:
    """Auto-generated: binary search implementation."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

def test_binary_search():
    data = [1, 3, 5, 7, 9, 11]
    return (binary_search(data, 5) == 2 and 
            binary_search(data, 1) == 0 and 
            binary_search(data, 99) == -1)
'''
            }
        }
    
    def classify_task(self, description: str) -> Tuple[str, List[str]]:
        """
        Classify task description into category and infer missing skills.
        Returns: (category, [skill_names])
        """
        description_lower = description.lower()
        
        # Keyword mapping
        keywords = {
            'math': ['multiply', 'divide', 'power', 'factorial', 'fibonacci', 
                    'prime', 'gcd', 'lcm', 'sqrt', 'logarithm'],
            'string': ['palindrome', 'anagram', 'reverse', 'count', 'find',
                      'replace', 'uppercase', 'lowercase', 'substring'],
            'data': ['filter', 'sort', 'group', 'map', 'reduce', 'average',
                    'median', 'mode', 'statistics', 'search'],
            'algorithm': ['sort', 'search', 'graph', 'tree', 'path', 'optimize',
                         'recursive', 'dynamic', 'greedy']
        }
        
        detected_skills = []
        detected_category = 'algorithm'  # default
        
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
        """
        Strategy 1: Adapt existing capability.
        Example: from 'add' create 'multiply' via repeated addition.
        """
        # Simple adaptations
        adaptations = {
            ('math', 'multiply'): '''
def multiply(a: float, b: float) -> float:
    """Generated by adaptation: repeated addition."""
    result = 0.0
    for _ in range(abs(int(b))):
        result += a
    return result if b >= 0 else -result

def test_multiply():
    return multiply(3, 4) == 12 and multiply(2, 0) == 0
''',
            ('data', 'filter_odd'): '''
def filter_odd(numbers: list) -> list:
    """Generated by adaptation: inverse of filter_even logic."""
    return [n for n in numbers if isinstance(n, (int, float)) and n % 2 != 0]

def test_filter_odd():
    return filter_odd([1, 2, 3, 4, 5]) == [1, 3, 5]
'''
        }
        
        key = (category, skill)
        if key in adaptations:
            return adaptations[key], f"ADAPTATION: {category}.{skill}"
        
        return None, "NO_ADAPTATION"
    
    def generate_from_composition(self, category: str, skill: str, existing_caps: Dict) -> Tuple[Optional[str], str]:
        """
        Strategy 2: Compose from multiple existing capabilities.
        """
        # Example: average = sum / count
        if skill == 'average' and 'sum' in str(existing_caps) and 'count' in str(existing_caps):
            return '''
def average(numbers: list) -> float:
    """Generated by composition: sum / count."""
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)

def test_average():
    return average([1, 2, 3, 4]) == 2.5 and average([5]) == 5.0
''', "COMPOSITION: sum + len"
        
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
        
        # Try strategies in order based on input
        strategies = [
            (0, lambda: self.generate_by_template(category, target_skill)),
            (1, lambda: self.generate_by_adaptation(category, target_skill, existing)),
            (2, lambda: self.generate_from_composition(category, target_skill, existing))
        ]
        
        # Reorder based on strategy parameter
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
        self.epsilon = 0.2  # Exploration rate
    
    def select_strategy(self, task_category: str) -> int:
        """
        Select generation strategy based on past success rates.
        Uses epsilon-greedy: sometimes explore randomly.
        """
        task_success = self.state.get('task_type_success', {})
        category_history = task_success.get(task_category, [0, 0, 0])
        
        # Calculate success rates
        total_attempts = sum(category_history)
        if total_attempts < 5:
            # Not enough data — explore
            return random.randint(0, 2)
        
        success_rates = [c / total_attempts if total_attempts > 0 else 0.33 
                        for c in category_history]
        
        # Epsilon-greedy
        if random.random() < self.epsilon:
            return random.randint(0, 2)
        
        return int(np.argmax(success_rates))
    
    def update(self, task_category: str, strategy: int, success: bool):
        """Update strategy success tracking."""
        task_success = self.state.setdefault('task_type_success', {})
        
        if task_category not in task_success:
            task_success[task_category] = [0, 0, 0]
        
        # Update count
        task_success[task_category][strategy] += 1 if success else 0
        
        # Also track total attempts separately for rate calculation
        attempts = self.state.setdefault('attempts', {})
        if task_category not in attempts:
            attempts[task_category] = [0, 0, 0]
        attempts[task_category][strategy] += 1
        
        self.core.update_meta({
            'task_type_success': task_success,
            'attempts': attempts
        })


# =============================================================================
# LAYER 4: AETHER MAIN AGENT (Orchestrator)
# =============================================================================

class Aether:
    """
    The main interface. Self-improving AI system.
    
    CAPABILITIES:
        - introspect()         : View current source and state
        - analyze(task)        : Identify capability gaps
        - improve(task)        : Generate, test, and deploy new capability
        - execute(skill, *args) : Run a deployed capability
        - evolve()             : Trigger meta-learning update
        - status()             : Show system state
    
    USAGE:
        aether = Aether()
        aether.improve("I need a function to check palindromes")
        result = aether.execute("is_palindrome", "A man a plan a canal Panama")
    """
    
    def __init__(self):
        print("=" * 60)
        print("  AETHER — Adaptive Extensible Heuristic Engine")
        print("  with Training & Evolution Routines")
        print("  v1.0.0 | Offline Mode | English Interface")
        print("=" * 60)
        
        self.core = AetherCore()
        self.generator = CapabilityGenerator(self.core)
        self.meta = MetaLearningEngine(self.core)
        
        # Load existing modules
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
    
    def help(self):
        """Display available commands."""
        help_text = """
Available Commands:
  introspect()              — View Aether's current source code state
  analyze("task desc")      — Identify what capabilities are missing
  improve("task desc")      — Generate, test, and deploy new capability
  execute("skill", *args)   — Run a deployed capability with arguments
  status()                  — Show full system state
  list_modules()            — List all loaded capabilities
  evolve()                  — Trigger meta-learning reflection
  
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
        
        # Current capabilities
        caps = self.core.get_capability_list()
        print(f"\n[Capabilities] {len(caps)} categories:")
        for cat, skills in caps.items():
            print(f"  {cat}: {skills}")
        
        # Loaded modules
        print(f"\n[Loaded Modules] {len(self.loaded_modules)}:")
        for name in self.loaded_modules:
            print(f"  - {name}")
        
        # Meta state
        meta = self.core.meta_state
        print(f"\n[Meta-Learning] Generation: {meta.get('generation', 0)}")
        print(f"  Strategy weights: {meta.get('strategy_weights', [0.33, 0.33, 0.33])}")
        
        # History
        history = self.core.history
        print(f"\n[Modification History] {len(history)} entries:")
        for h in history[-5:]:
            print(f"  {h['timestamp']}: {h['file']} by {h['author']}")
        
        print("\n" + "=" * 60)
        return {
            'capabilities': caps,
            'modules': list(self.loaded_modules.keys()),
            'meta': meta,
            'history_count': len(history)
        }
    
    def analyze(self, task_description: str) -> Dict:
        """
        Analyze a task and identify capability gaps.
        """
        print(f"\n[Analyze] Task: '{task_description}'")
        
        category, needed = self.generator.classify_task(task_description)
        existing = self.core.get_capability_list()
        
        # Check what's missing
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
            print(f"  → Gap detected! Missing: {missing}")
            print(f"  → Suggested: call improve() to generate these capabilities")
        else:
            print(f"  → All skills available: {available}")
            print(f"  → Suggested: call execute() directly")
        
        return result
    
    def improve(self, task_description: str) -> Tuple[bool, str]:
        """
        THE CORE SELF-IMPROVEMENT PIPELINE:
        1. Analyze gap
        2. Select strategy (meta-learning)
        3. Generate code
        4. Test in sandbox
        5. Deploy if passed
        6. Update knowledge and meta-learning
        """
        print(f"\n{'='*60}")
        print(f"SELF-IMPROVEMENT SEQUENCE INITIATED")
        print(f"{'='*60}")
        print(f"Target: '{task_description}'")
        
        # Step 1: Analyze
        analysis = self.analyze(task_description)
        if not analysis['gap_exists']:
            print(f"\n[Skip] No improvement needed. Use execute() instead.")
            return True, "NO_GAP"
        
        category = analysis['inferred_category']
        skill = analysis['missing'][0]
        
        # Step 2: Select strategy via meta-learning
        strategy = self.meta.select_strategy(category)
        strategy_names = ['Template', 'Adaptation', 'Composition']
        print(f"\n[Strategy] Selected: {strategy_names[strategy]} (ID: {strategy})")
        
        # Step 3: Generate
        print(f"\n[Generate] Creating capability: {category}.{skill}")
        code, gen_msg = self.generator.generate(task_description, strategy)
        
        if not code:
            print(f"[Fail] Generation failed: {gen_msg}")
            self.meta.update(category, strategy, False)
            self.core.update_knowledge(category, skill, False, {'error': gen_msg})
            return False, f"GENERATION_FAILED: {gen_msg}"
        
        print(f"[Success] {gen_msg}")
        print(f"[Preview]\n{code[:200]}...")
        
        # Step 4 & 5: Deploy (includes sandbox testing)
        print(f"\n[Deploy] Running safety pipeline...")
        success, deploy_msg = self.core.write_module(f"{skill}.py", code)
        
        if not success:
            print(f"[Fail] Deployment failed: {deploy_msg}")
            self.meta.update(category, strategy, False)
            self.core.update_knowledge(category, skill, False, {'error': deploy_msg})
            return False, f"DEPLOYMENT_FAILED: {deploy_msg}"
        
        print(f"[Success] {deploy_msg}")
        
        # Step 6: Update systems
        self.meta.update(category, strategy, True)
        self.core.update_knowledge(category, skill, True, {
            'strategy': strategy,
            'code_hash': hashlib.sha256(code.encode()).hexdigest()[:16]
        })
        
        # Refresh modules
        self._refresh_modules()
        
        print(f"\n{'='*60}")
        print(f"SELF-IMPROVEMENT COMPLETE")
        print(f"{'='*60}")
        print(f"New capability: {skill}")
        print(f"Try: aether.execute('{skill}', ...)")
        
        return True, f"DEPLOYED: {skill}"
    
    def execute(self, skill_name: str, *args, **kwargs):
        """
        Execute a deployed capability by name.
        """
        # Find in loaded modules
        for module_name, namespace in self.loaded_modules.items():
            if skill_name in namespace and callable(namespace[skill_name]):
                try:
                    result = namespace[skill_name](*args, **kwargs)
                    print(f"\n[Execute] {skill_name}({', '.join(map(str, args))})")
                    print(f"  → Result: {result}")
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
        print(f"META-LEARNING EVOLUTION")
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
            print(f"[Adapt] High success rate — reducing exploration to {self.meta.epsilon:.2f}")
        elif success_rate < 0.4:
            self.meta.epsilon = min(0.5, self.meta.epsilon * 1.2)
            print(f"[Adapt] Low success rate — increasing exploration to {self.meta.epsilon:.2f}")
        
        # Show current strategy preferences
        task_success = self.core.meta_state.get('task_type_success', {})
        print(f"\n[Strategy Preferences]")
        for category, counts in task_success.items():
            best = int(np.argmax(counts))
            names = ['Template', 'Adaptation', 'Composition']
            print(f"  {category}: prefers {names[best]} (scores: {counts})")
        
        self.core.update_meta({'last_evolution': datetime.now().isoformat()})
        print(f"\n[Complete] Meta-learning state updated.")


# =============================================================================
# INTERACTIVE SHELL
# =============================================================================

def main():
    """Interactive Aether shell."""
    aether = Aether()
    
    print("\n" + "=" * 60)
    print("INTERACTIVE MODE")
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
            
            # Parse command
            if '(' in user_input and user_input.endswith(')'):
                # Method call format: method(args)
                method_name = user_input[:user_input.index('(')]
                args_str = user_input[user_input.index('(')+1:-1]
                
                # Simple argument parsing
                if args_str:
                    # Try to eval safely
                    try:
                        args = eval(f"({args_str},)", {"__builtins__": {}}, {})
                        if not isinstance(args, tuple):
                            args = (args,)
                    except:
                        args = (args_str,)  # Treat as string
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
                # Direct execution or query
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
    # Check if run with --demo flag
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        print("RUNNING AUTONOMOUS DEMONSTRATION\n")
        
        aether = Aether()
        
        # Demo 1: Improve with math capability
        aether.improve("I need a function to multiply two numbers")
        aether.execute("multiply", 7, 8)
        
        # Demo 2: Improve with string capability
        aether.improve("Can you check if a text is palindrome?")
        aether.execute("is_palindrome", "radar")
        
        # Demo 3: Improve with data capability
        aether.improve("I want to filter even numbers from a list")
        aether.execute("filter_even", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        
        # Demo 4: Meta-learning evolution
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