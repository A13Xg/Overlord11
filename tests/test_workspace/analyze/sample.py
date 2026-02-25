import os
import json
from pathlib import Path

def simple_function(x):
    """A simple function."""
    return x + 1

def complex_function(data, threshold=0.5):
    results = []
    for item in data:
        if item > threshold:
            if item > threshold * 2:
                results.append(item * 2)
            else:
                results.append(item)
        elif item == 0:
            results.append(None)
        else:
            for sub in range(int(item)):
                if sub % 2 == 0:
                    results.append(sub)
    return results

class DataProcessor:
    def __init__(self, name):
        self.name = name
        self.data = []

    def process(self, items):
        """Process a list of items."""
        for item in items:
            if isinstance(item, dict):
                self.data.append(item)
        return self.data

# TODO: add error handling
# FIXME: this is a placeholder
