"""Channel-agnostic outgoing messages that mirror WhatsApp Cloud API
interactive types, with WhatsApp's limits enforced at construction.

Anything that renders in the web simulator is therefore valid on WhatsApp.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# WhatsApp Cloud API limits
MAX_BODY = 1024
MAX_HEADER = 60
MAX_FOOTER = 60
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_LIST_ROWS = 10
MAX_LIST_SECTIONS = 10
MAX_LIST_BUTTON = 20
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72
MAX_SECTION_TITLE = 24
MAX_ID = 200
MAX_TEXT = 4096


class LimitError(ValueError):
    pass


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise LimitError(msg)


def fit(text: str, limit: int) -> str:
    """Shorten text to a WhatsApp limit, adding an ellipsis.

    Collapses runs of spaces but keeps line breaks (message bodies are
    multi-line: carts, summaries)."""
    text = "\n".join(" ".join(line.split()) for line in text.strip().split("\n"))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@dataclass
class Text:
    body: str
    type: str = field(default="text", init=False)

    def __post_init__(self):
        _check(0 < len(self.body) <= MAX_TEXT, "text body length")


@dataclass
class Button:
    id: str
    title: str

    def __post_init__(self):
        _check(0 < len(self.title) <= MAX_BUTTON_TITLE, f"button title too long: {self.title!r}")
        _check(0 < len(self.id) <= MAX_ID, "button id length")


@dataclass
class Buttons:
    body: str
    buttons: list[Button]
    header: str | None = None
    footer: str | None = None
    type: str = field(default="buttons", init=False)

    def __post_init__(self):
        _check(0 < len(self.body) <= MAX_BODY, "buttons body length")
        _check(1 <= len(self.buttons) <= MAX_BUTTONS, "1..3 buttons")
        _check(len({b.id for b in self.buttons}) == len(self.buttons), "duplicate button ids")
        _check(len({b.title for b in self.buttons}) == len(self.buttons), "duplicate button titles")
        _check(self.header is None or len(self.header) <= MAX_HEADER, "header length")
        _check(self.footer is None or len(self.footer) <= MAX_FOOTER, "footer length")


@dataclass
class Row:
    id: str
    title: str
    description: str | None = None

    def __post_init__(self):
        _check(0 < len(self.title) <= MAX_ROW_TITLE, f"row title too long: {self.title!r}")
        _check(self.description is None or len(self.description) <= MAX_ROW_DESCRIPTION, "row description length")
        _check(0 < len(self.id) <= MAX_ID, "row id length")


@dataclass
class Section:
    title: str
    rows: list[Row]

    def __post_init__(self):
        _check(0 < len(self.title) <= MAX_SECTION_TITLE, f"section title too long: {self.title!r}")
        _check(len(self.rows) >= 1, "section needs rows")


@dataclass
class List:
    body: str
    button: str
    sections: list[Section]
    header: str | None = None
    footer: str | None = None
    type: str = field(default="list", init=False)

    def __post_init__(self):
        _check(0 < len(self.body) <= MAX_BODY, "list body length")
        _check(0 < len(self.button) <= MAX_LIST_BUTTON, "list button length")
        _check(1 <= len(self.sections) <= MAX_LIST_SECTIONS, "list sections count")
        rows = [r for s in self.sections for r in s.rows]
        _check(1 <= len(rows) <= MAX_LIST_ROWS, f"list rows must be 1..10 (got {len(rows)})")
        _check(len({r.id for r in rows}) == len(rows), "duplicate row ids")
        _check(self.header is None or len(self.header) <= MAX_HEADER, "header length")
        _check(self.footer is None or len(self.footer) <= MAX_FOOTER, "footer length")


@dataclass
class LocationRequest:
    """WhatsApp interactive `location_request_message`: a body plus a
    "Send location" button that shares the customer's pin."""

    body: str
    type: str = field(default="location_request", init=False)

    def __post_init__(self):
        _check(0 < len(self.body) <= MAX_BODY, "location request body length")


Outgoing = Text | Buttons | List | LocationRequest


def valid_coords(lat: float | None, lng: float | None) -> bool:
    try:
        return lat is not None and lng is not None and -90 <= float(lat) <= 90 and -180 <= float(lng) <= 180
    except (TypeError, ValueError):
        return False


def to_payload(msg: Outgoing) -> dict:
    return asdict(msg)


def validate_payload(payload: dict) -> Outgoing:
    """Rebuild (and therefore re-validate) a stored outgoing payload."""
    kind = payload["type"]
    if kind == "text":
        return Text(body=payload["body"])
    if kind == "buttons":
        return Buttons(
            body=payload["body"],
            buttons=[Button(**b) for b in payload["buttons"]],
            header=payload.get("header"),
            footer=payload.get("footer"),
        )
    if kind == "list":
        return List(
            body=payload["body"],
            button=payload["button"],
            sections=[Section(title=s["title"], rows=[Row(**r) for r in s["rows"]]) for s in payload["sections"]],
            header=payload.get("header"),
            footer=payload.get("footer"),
        )
    if kind == "location_request":
        return LocationRequest(body=payload["body"])
    raise LimitError(f"unknown message type {kind}")


@dataclass
class Inbound:
    """Normalized inbound message (same shape for web and WhatsApp)."""

    kind: str  # text | button | list | location
    text: str = ""
    id: str | None = None  # reply id for button/list
    lat: float | None = None  # location messages
    lng: float | None = None

    def to_payload(self) -> dict:
        if self.kind == "text":
            return {"type": "text", "text": self.text}
        if self.kind == "location":
            return {"type": "location", "latitude": self.lat, "longitude": self.lng}
        return {"type": f"{self.kind}_reply", "id": self.id, "title": self.text}
