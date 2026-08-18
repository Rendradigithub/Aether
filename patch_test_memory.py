import re
with open('tests/test_memory.py', 'r') as f:
    content = f.read()

def repl(m):
    inner = m.group(1)
    if 'self.archive' in inner or 'self.assert_memory_equal' in inner:
        return m.group(0)
    if inner.strip() == '':
        return m.group(0)
    return f"add_experience({inner}.get('state', None), 'generate', {inner}.get('reward', 0.5), {inner}.get('state', None), {inner})"

content = re.sub(r'add_experience\((.*?)\)', repl, content)

with open('tests/test_memory.py', 'w') as f:
    f.write(content)
print('patched test_memory.py')
