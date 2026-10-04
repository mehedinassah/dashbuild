def calculate(a, b, operation):
    if operation == 'add':
        return a + b
    elif operation == 'subtract':
        return a - b
    elif operation == 'multiply':
        return a * b
    elif operation == 'divide':
        if b == 0:
            return 'Error: Division by zero'
        return a / b
    elif operation == 'modulus':
        if b == 0:
            return 'Error: Modulus by zero'
        return a % b
    else:
        return 'Error: Invalid operation'