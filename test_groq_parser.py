import re
import json

def _extract_json_dict(text: str) -> dict:
    """Extracts the largest valid JSON object from the text."""
    start_idx = text.find('{')
    if start_idx == -1:
        return {}
        
    best_dict = {}
    
    for i in range(len(text)):
        if text[i] == '{':
            nesting = 0
            in_string = False
            escape = False
            
            for j in range(i, len(text)):
                char = text[j]
                
                if escape:
                    escape = False
                    continue
                if char == '\\':
                    escape = True
                    continue
                
                if char == '"':
                    in_string = not in_string
                    continue
                    
                if not in_string:
                    if char == '{':
                        nesting += 1
                    elif char == '}':
                        nesting -= 1
                        if nesting == 0:
                            candidate = text[i:j+1]
                            try:
                                parsed = json.loads(candidate)
                                if isinstance(parsed, dict):
                                    if "schema_version" in parsed and "is_valid_anganwadi_scene" in parsed:
                                        return parsed  # Found it!
                                    best_dict = parsed
                            except json.JSONDecodeError:
                                pass
                            break
    return best_dict

# Test cases
tests = [
    """<think>reasoning</think>\n{"schema_version":"1.0", "is_valid_anganwadi_scene": true}""",
    """<think>unclosed reasoning...\n{"schema_version":"1.0", "is_valid_anganwadi_scene": true}""",
    """```json\n{"schema_version":"1.0", "is_valid_anganwadi_scene": true}\n```""",
    """{"schema_version":"1.0", "is_valid_anganwadi_scene": true}""",
    """{"nested": {"schema_version":"1.0", "is_valid_anganwadi_scene": true}}""",
    """{"schema_version":"1.0", "is_valid_anganwadi_scene": true, "remarks":"स्थिति {संदिग्ध} है"}""",
    """malformed no json""",
]

for idx, t in enumerate(tests):
    print(f"Test {chr(65+idx)}:", _extract_json_dict(t))
