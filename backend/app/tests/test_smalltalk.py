"""Greetings get an introduction; real questions still go to the document search."""
import pytest

from backend.app.services import smalltalk


@pytest.mark.parametrize("text", [
    "hi", "Hi!", "hai", "Hello", "hey there", "good morning", "Hello ForgeMind AI", "hii", "namaste",
])
def test_greetings_get_the_introduction(text):
    assert smalltalk.reply(text) == smalltalk.INTRO


@pytest.mark.parametrize("text, expected", [
    ("how are you?", smalltalk.FINE),
    ("who are you", smalltalk.ABOUT),
    ("what can you do", smalltalk.ABOUT),
    ("thanks", smalltalk.WELCOME),
    ("Thank you!", smalltalk.WELCOME),
    ("bye", smalltalk.BYE),
])
def test_other_small_talk(text, expected):
    assert smalltalk.reply(text) == expected


@pytest.mark.parametrize("text", [
    "hi pressure alarm on the compressor", "how do I replace the oil filter", "hello what causes low oil pressure",
    "help me fix the pump leak on line 2", "", "   ", "?!",
])
def test_real_questions_are_not_small_talk(text):
    assert smalltalk.reply(text) is None


def test_ask_endpoint_answers_a_greeting_without_sources(client):
    r = client.post("/api/ask", json={"question": "hi"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == smalltalk.INTRO and body["sources"] == [] and body["generated_by"] == "assistant"


def test_ask_endpoint_still_searches_for_real_questions(client):
    r = client.post("/api/ask", json={"question": "How do I replace the oil separator?"})
    assert r.status_code == 200 and r.json()["generated_by"] != "assistant"