import pytest
from calculator import calculate
def test_add():
    assert calculate(10, 5, 'add') == 15
def test_subtract():
    assert calculate(10, 5, 'subtract') == 5
def test_multiply():
    assert calculate(10, 5, 'multiply') == 50
def test_divide():
    assert calculate(10, 5, 'divide') == 2
def test_divide_by_zero():
    assert calculate(10, 0, 'divide') == 'Error: Division by zero'
def test_modulus():
    assert calculate(10, 3, 'modulus') == 1
def test_modulus_by_zero():
    assert calculate(10, 0, 'modulus') == 'Error: Modulus by zero'
def test_invalid_operation():
    assert calculate(10, 5, 'invalid') == 'Error: Invalid operation'


def test_power():
    assert calculate(2, 3, 'power') == 8
    assert calculate(-2, 3, 'power') == -8
    assert calculate(0, 3, 'power') == 0
