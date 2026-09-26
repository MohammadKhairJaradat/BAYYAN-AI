from app.advisor.llm import _parse_json_safely


def test_parse_json_safely_accepts_fenced_json_with_trailing_commas():
    raw = """```json
{
  "steps": [
    {"priority": 1, "action": "Upload salary slip",},
  ],
  "narrative": "Ready",
}
```"""

    data = _parse_json_safely(raw)

    assert data["steps"][0]["action"] == "Upload salary slip"
    assert data["narrative"] == "Ready"


def test_parse_json_safely_extracts_json_object_from_prose():
    raw = 'Here is the JSON: {"flags": [], "narrative": "No issues"}'

    data = _parse_json_safely(raw)

    assert data == {"flags": [], "narrative": "No issues"}


def test_parse_json_safely_rejects_non_object_json():
    data = _parse_json_safely('[{"priority": 1}]')

    assert data["error"] == "parse_failed"
