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
