def factorial(n: int) -> int:
    """Auto-generated: factorial computation."""
    if n < 0:
        raise ValueError('Factorial undefined for negative numbers')
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

def test_factorial():
    return factorial(0) == 1 and factorial(5) == 120 and factorial(1) == 1
