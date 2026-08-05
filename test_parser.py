import json
from app.services.groq_vision import GroqVisionService

def test_think_parser():
    svc = GroqVisionService()
    
    # 1. Standard think block
    test_str1 = """<think>
This is reasoning...
</think>
```json
{
  "schema_version": "1.0",
  "remarks": "Test 1"
}
```"""

    # 2. Unclosed think block!
    test_str2 = """<think>
I forgot to close the tag...
But here is the json:
{
  "schema_version": "1.0",
  "remarks": "Test 2"
}
"""

    print("--- TEST 1 (Standard) ---")
    clean1 = svc._clean_json_markdown(test_str1)
    print("Extracted:")
    print(clean1)
    try:
        data1 = json.loads(clean1)
        print("JSON parsed:", data1["remarks"])
        print("Test 1 PASS")
    except Exception as e:
        print("Test 1 FAIL:", e)

    print("\n--- TEST 2 (Unclosed) ---")
    clean2 = svc._clean_json_markdown(test_str2)
    print("Extracted:")
    print(clean2)
    try:
        data2 = json.loads(clean2)
        print("JSON parsed:", data2["remarks"])
        print("Test 2 PASS")
    except Exception as e:
        print("Test 2 FAIL:", e)

if __name__ == "__main__":
    test_think_parser()
