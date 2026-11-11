"""Test doubles and builders shared by the test modules."""
from google.genai import errors, types


def reply(text: str, finish: str = "STOP") -> types.GenerateContentResponse:
    """A real SDK response object containing one text candidate."""
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text=text)]),
                finish_reason=getattr(types.FinishReason, finish),
            )
        ]
    )


def blocked_prompt(reason: str = "SAFETY") -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        prompt_feedback=types.GenerateContentResponsePromptFeedback(block_reason=getattr(types.BlockedReason, reason))
    )


def api_error(code: int, status: str = "ERROR", message: str = "boom") -> errors.APIError:
    body = {"error": {"code": code, "message": message, "status": status}}
    return (errors.ServerError if code >= 500 else errors.ClientError)(code, body)


class FakeGemini:
    """Stands in for ``genai.Client``. Each call consumes the next scripted outcome.

    An outcome is a response object, an exception (raised), a string (wrapped as a reply) or a
    callable taking the call kwargs. The last outcome repeats if the script runs out.
    """

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes) or [reply("ok")]
        self.calls: list[dict] = []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]
        if callable(outcome) and not isinstance(outcome, type):
            outcome = outcome(**kwargs)
        if isinstance(outcome, BaseException):
            raise outcome
        return reply(outcome) if isinstance(outcome, str) else outcome

    @property
    def prompt(self) -> str:
        return self.calls[-1]["contents"]


def make_pdf_bytes(pages: list[list[str]]) -> bytes:
    """Build a small text PDF; each inner list holds the lines of one page."""
    import io

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for lines in pages:
        for i, line in enumerate(lines):
            pdf.drawString(72, 750 - 18 * i, line)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()