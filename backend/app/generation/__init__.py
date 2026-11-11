"""Writes the answer.

* ``gemini_client`` - builds the grounded prompt, calls Gemini with retries, checks the [n] citations,
  adds the safety note, and falls back to extracts from the manuals if the model is unavailable.
"""