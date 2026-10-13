import json

import httpx
import pytest

from app.services.extraction import ClaudeExtractor, ExtractionError, RuleBasedExtractor, parse_llm_json

CAPTION = """Creamy garlic tuscan pasta 🍝 serves 4
Ingredients:
- 2 cups penne
- 4 cloves garlic, minced
- 1/2 cup heavy cream
- 1½ tbsp olive oil
- 1 can sun-dried tomatoes
- a handful of spinach
- salt to taste

1. Boil the pasta until al dente.
2. Fry the garlic in olive oil.
3. Stir in cream, tomatoes and spinach.
#pasta #easyrecipes"""


def by_name(recipe):
    return {i.name.lower(): i for i in recipe.ingredients}


def test_caption_ingredients():
    r = RuleBasedExtractor().extract(CAPTION, "")
    ings = by_name(r)
    assert ings["penne"].quantity == "2" and ings["penne"].unit == "cups"
    assert ings["garlic, minced"].unit == "cloves"
    assert ings["heavy cream"].quantity == "1/2"
    assert ings["olive oil"].quantity == "1½"
    assert ings["sun-dried tomatoes"].unit == "can"
    assert "handful of spinach" in ings


def test_caption_title_servings_and_steps():
    r = RuleBasedExtractor().extract(CAPTION, "")
    assert r.title == "Creamy garlic tuscan pasta 🍝"
    assert r.servings == 4
    assert r.steps == ["Boil the pasta until al dente.", "Fry the garlic in olive oil.",
                       "Stir in cream, tomatoes and spinach."]


def test_numbered_steps_are_not_ingredients():
    r = RuleBasedExtractor().extract("1. Preheat the oven\n2 eggs", "")
    assert [i.name for i in r.ingredients] == ["eggs"]


def test_spoken_transcript():
    transcript = ("Okay so first add two cups of flour and a pinch of salt. Then whisk in "
                  "3 tablespoons of melted butter, then bake for 20 minutes.")
    r = RuleBasedExtractor().extract("", transcript)
    ings = {(i.quantity, i.unit.lower(), i.name) for i in r.ingredients}
    assert ("two", "cups", "flour") in ings
    assert ("a", "pinch", "salt") in ings
    assert ("3", "tablespoons", "melted butter") in ings
    assert not any("minute" in i.name for i in r.ingredients)
    assert any("bake" in s for s in r.steps)


def test_empty_input():
    r = RuleBasedExtractor().extract("", "")
    assert r.ingredients == [] and r.title == "Untitled recipe"


VALID = {"title": "Pasta", "servings": 2,
         "ingredients": [{"name": "penne", "quantity": "200", "unit": "g", "raw_text": "200g penne"},
                         {"name": "salt", "quantity": None, "unit": None}],
         "steps": ["Boil", " "]}


def test_parse_llm_json_handles_code_fences():
    r = parse_llm_json("Here you go:\n```json\n" + json.dumps(VALID) + "\n```")
    assert r.title == "Pasta" and r.servings == 2
    assert r.ingredients[1].quantity == "" and r.ingredients[1].unit == ""
    assert r.steps == ["Boil"]


@pytest.mark.parametrize("bad", ["no json here", "{not json}", json.dumps({"title": "x"}),
                                 json.dumps({**VALID, "ingredients": [{"name": ""}]})])
def test_parse_llm_json_rejects_bad_output(bad):
    with pytest.raises(ExtractionError):
        parse_llm_json(bad)


def test_claude_extractor_with_mock_http():
    seen = {}

    def handler(request: httpx.Request):
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(VALID)}]})

    ex = ClaudeExtractor("test-key", "test-model", httpx.Client(transport=httpx.MockTransport(handler)))
    r = ex.extract("my caption", "my transcript")
    assert r.title == "Pasta"
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["body"]["model"] == "test-model"
    assert "my caption" in seen["body"]["messages"][0]["content"]


def test_claude_extractor_http_error():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(529)))
    with pytest.raises(ExtractionError):
        ClaudeExtractor("k", "m", client).extract("c", "t")
