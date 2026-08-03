def is_anagram(a: str, b: str) -> bool:
    """Auto-generated: anagram detection."""
    def normalize(s):
        return sorted(''.join(c.lower() for c in s if c.isalnum()))
    return normalize(a) == normalize(b)

def test_anagram():
    return (is_anagram('listen', 'silent') and 
            is_anagram('Dormitory', 'Dirty room') and 
            not is_anagram('hello', 'world'))
