import math

def calculator_tool(num1: float, operation: str, num2: float | None = None) -> float:
    """
    Performs basic arithmetic operations and advanced mathematical functions (square root, power, logarithm, sine, cosine, tangent) on one or two numbers.

    Args:
        num1: The first number (or the only number for single-argument functions like sqrt, sin, cos, tan).
        num2: The second number (for two-argument functions like add, subtract, multiply, divide, power, or the base for logarithm). Optional for single-argument functions.
        operation: The arithmetic operation or mathematical function to perform (add, subtract, multiply, divide, sqrt, power, log, sin, cos, tan).

    Returns:
        The result of the operation.

    Raises:
        ValueError: If an unknown operation is provided, division by zero occurs, or insufficient arguments for an operation.
    """
    if operation == "add":
        if num2 is None:
            raise ValueError("Operation 'add' requires two numbers.")
        return num1 + num2
    elif operation == "subtract":
        if num2 is None:
            raise ValueError("Operation 'subtract' requires two numbers.")
        return num1 - num2
    elif operation == "multiply":
        if num2 is None:
            raise ValueError("Operation 'multiply' requires two numbers.")
        return num1 * num2
    elif operation == "divide":
        if num2 is None:
            raise ValueError("Operation 'divide' requires two numbers.")
        if num2 == 0:
            raise ValueError("Division by zero is not allowed.")
        return num1 / num2
    elif operation == "sqrt":
        if num1 < 0:
            raise ValueError("Square root of a negative number is not allowed.")
        return math.sqrt(num1)
    elif operation == "power":
        if num2 is None:
            raise ValueError("Operation 'power' requires two numbers (base and exponent).")
        return math.pow(num1, num2)
    elif operation == "log":
        if num1 <= 0:
            raise ValueError("Logarithm of a non-positive number is not allowed.")
        if num2 is None: # Natural logarithm if base not provided
            return math.log(num1)
        elif num2 <= 0 or num2 == 1:
            raise ValueError("Logarithm base must be positive and not equal to 1.")
        return math.log(num1, num2)
    elif operation == "sin":
        return math.sin(math.radians(num1)) # Assuming input in degrees
    elif operation == "cos":
        return math.cos(math.radians(num1)) # Assuming input in degrees
    elif operation == "tan":
        return math.tan(math.radians(num1)) # Assuming input in degrees
    else:
        raise ValueError(f"Unknown operation: {operation}. Supported operations are add, subtract, multiply, divide, sqrt, power, log, sin, cos, tan.")

if __name__ == "__main__":
    # Example usage for basic operations:
    print(f"10 + 5 = {calculator_tool(10, 5, 'add')}")
    print(f"10 - 5 = {calculator_tool(10, 5, 'subtract')}")
    print(f"10 * 5 = {calculator_tool(10, 5, 'multiply')}")
    print(f"10 / 5 = {calculator_tool(10, 5, 'divide')}")

    # Example usage for advanced operations:
    print(f"sqrt(25) = {calculator_tool(25, operation='sqrt')}")
    print(f"2^3 = {calculator_tool(2, 3, 'power')}")
    print(f"log(100) (natural) = {calculator_tool(100, operation='log')}")
    print(f"log(100, base=10) = {calculator_tool(100, 10, 'log')}")
    print(f"sin(30 degrees) = {calculator_tool(30, operation='sin')}")
    print(f"cos(60 degrees) = {calculator_tool(60, operation='cos')}")
    print(f"tan(45 degrees) = {calculator_tool(45, operation='tan')}")

    # Example error handling:
    try:
        calculator_tool(10, 0, 'divide')
    except ValueError as e:
        print(f"Error: {e}")
    try:
        calculator_tool(-9, operation='sqrt')
    except ValueError as e:
        print(f"Error: {e}")
    try:
        calculator_tool(10, operation='power')
    except ValueError as e:
        print(f"Error: {e}")
    try:
        calculator_tool(0, operation='log')
    except ValueError as e:
        print(f"Error: {e}")
    try:
        calculator_tool(10, 5, 'unknown')
    except ValueError as e:
        print(f"Error: {e}")
