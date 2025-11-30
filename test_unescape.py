#!/usr/bin/env python3
"""Debug script to check newline unescaping"""

import json

test_json = '''[{
  "file_path": "calc.py",
  "new_code": "def calculate_average(numbers):\\n    if not numbers:\\n        return 0.0\\n    return sum(numbers) / len(numbers)",
  "issue": "Fixed division by zero"
}]'''

print("Original JSON:")
print(test_json[:200])

fixes = json.loads(test_json)
print(f"\nParsed {len(fixes)} fixes")

# Unescape
decoded_fixes = []
for fix in fixes:
    decoded_fix = {}
    for key, value in fix.items():
        if isinstance(value, str):
            # Unescape the JSON string value
            decoded_value = value.encode('utf-8').decode('unicode-escape')
            decoded_fix[key] = decoded_value
        else:
            decoded_fix[key] = value
    decoded_fixes.append(decoded_fix)

print(f"\nUnescaped code:\n{decoded_fixes[0]['new_code']}")
