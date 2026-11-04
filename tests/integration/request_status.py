"""Audit helper (D-053): every htmx write trigger is, or sits inside, an element holding a
`[data-request-status]` slot."""

from __future__ import annotations

from html.parser import HTMLParser

WRITE_ATTRIBUTES = ("hx-post", "hx-patch", "hx-put", "hx-delete")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class _Element:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.has_slot = False


class SlotAudit(HTMLParser):
    """Collects each write trigger with its ancestors, and which elements contain a slot."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[_Element] = []
        self.triggers: list[tuple[str, list[_Element]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = {name for name, _ in attrs}
        element = _Element(tag)
        chain = [*self.stack, element]
        if "data-request-status" in names:
            for ancestor in self.stack:
                ancestor.has_slot = True
        for name, value in attrs:
            if name in WRITE_ATTRIBUTES:
                self.triggers.append((f"<{tag} {name}={value}>", chain))
        if tag not in VOID:
            self.stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return


def triggers_without_slot(html: str) -> list[str]:
    """Write triggers of `html` with no slot in themselves or an ancestor."""
    audit = SlotAudit()
    audit.feed(html)
    audit.close()
    return [label for label, chain in audit.triggers if not any(element.has_slot for element in chain)]


def write_triggers(html: str) -> int:
    """Number of htmx write triggers in `html`."""
    audit = SlotAudit()
    audit.feed(html)
    audit.close()
    return len(audit.triggers)
