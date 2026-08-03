def fibonacci(n: int) -> int:
    """Auto-generated: fibonacci sequence."""
    if n < 0:
        raise ValueError('Fibonacci undefined for negative numbers')
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

def test_fibonacci():
    return fibonacci(0) == 0 and fibonacci(1) == 1 and fibonacci(10) == 55
