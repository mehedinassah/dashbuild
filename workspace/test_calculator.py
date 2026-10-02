from calculator import calculate


def test_add():
    assert calculate(10, 5, "add") == 15

def test_subtract():
    assert calculate(10, 5, "subtract") == 5

def test_multiply():
    assert calculate(10, 5, "multiply") == 50

def test_divide():
    assert calculate(10, 5, "divide") == 2

def test_divide_by_zero():
    assert calculate(10, 0, "divide") == "Error: Division by zero"

def test_invalid_operation():
    assert calculate(10, 5, "modulus") == "Error: Invalid operation"