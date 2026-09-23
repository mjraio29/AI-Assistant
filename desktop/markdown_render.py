"""
Minimal markdown rendering for chat bubbles: **bold**, `inline code`, and
fenced ```code blocks```. Not a full markdown parser -- just the handful of
things models actually produce most often in chat replies. Renders into a
plain tkinter Text widget using tags, which keeps native text selection and
wrapping working normally (a CTkLabel can't do either of those).
"""
import re
import tkinter.font as tkfont

_FENCE_RE = re.compile(r"```(?:\w+\n)?(.*?)```", re.DOTALL)
_INLINE_RE = re.compile(r"\*\*(.+?)\*\*|`([^`\n]+?)`")


def render_markdown(text_widget, text: str, mono_bg: str) -> None:
    """Insert `text` into `text_widget` with bold/code tags applied.
    Call before setting the widget to a disabled/readonly state."""
    base_font = tkfont.Font(font=text_widget.cget("font"))
    bold_font = tkfont.Font(font=text_widget.cget("font"))
    bold_font.configure(weight="bold")
    mono_font = tkfont.Font(family="Consolas", size=base_font.actual("size"))

    text_widget.tag_configure("bold", font=bold_font)
    text_widget.tag_configure("code", font=mono_font, background=mono_bg)
    text_widget.tag_configure(
        "codeblock", font=mono_font, background=mono_bg,
        lmargin1=10, lmargin2=10, spacing1=4, spacing3=4,
    )

    pos = 0
    for fence_match in _FENCE_RE.finditer(text):
        _insert_inline(text_widget, text[pos:fence_match.start()])
        code = fence_match.group(1).strip("\n")
        text_widget.insert("end", code + "\n", ("codeblock",))
        pos = fence_match.end()
    _insert_inline(text_widget, text[pos:])


def _insert_inline(text_widget, segment: str) -> None:
    pos = 0
    for m in _INLINE_RE.finditer(segment):
        text_widget.insert("end", segment[pos:m.start()])
        if m.group(1) is not None:
            text_widget.insert("end", m.group(1), ("bold",))
        else:
            text_widget.insert("end", m.group(2), ("code",))
        pos = m.end()
    text_widget.insert("end", segment[pos:])
