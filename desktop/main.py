"""
Desktop chat client for Robert. Talks directly to app.groq_client --
no server required, though the FastAPI backend from app/main.py can still run
separately for other clients (web, mobile) against the same SQLite memory.

Run from the project root:
    python -m desktop.main
"""
import threading
from pathlib import Path
from tkinter import messagebox, filedialog
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk

from app.config import require_api_key, settings
from desktop.markdown_render import render_markdown
from desktop.session_store import create_session, delete_session, list_sessions, touch_session

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

APP_NAME = "Robert"
ICON_PATH = Path(__file__).parent / "assets" / "icon.png"
SIDEBAR_WIDTH = 220
BUBBLE_WRAP = 480

try:
    from desktop.tray import TrayIcon

    TRAY_AVAILABLE = True
except Exception:
    # pystray can fail at import time (not just ImportError) on systems
    # missing a tray backend (e.g. no GTK on some Linux setups). Robert
    # should still run as a normal window in that case, just without tray.
    TRAY_AVAILABLE = False


class ChatBubble(ctk.CTkFrame):
    """One message bubble. Right-aligned + accent color for the user,
    left-aligned + neutral for the assistant. Renders bold/inline-code/code
    blocks and includes a small copy button."""

    def __init__(self, parent, text: str, is_user: bool):
        super().__init__(parent, fg_color="transparent")
        bubble_bg = "#2563eb" if is_user else "#26262c"
        text_color = "white" if is_user else "#e5e5e5"
        anchor_side = "e" if is_user else "w"

        column = ctk.CTkFrame(self, fg_color="transparent")
        column.pack(anchor=anchor_side, padx=10, pady=4)

        default_font = tkfont.nametofont("TkDefaultFont")
        family = default_font.actual("family")

        text_widget = tk.Text(
            column,
            wrap="word",
            width=58,
            borderwidth=0,
            highlightthickness=0,
            background=bubble_bg,
            foreground=text_color,
            insertbackground=text_color,
            padx=14,
            pady=10,
            font=(family, 13),
            cursor="arrow",
        )
        text_widget.pack(anchor=anchor_side)

        render_markdown(text_widget, text, mono_bg="#1a1a1f" if not is_user else "#1d4ed8")
        text_widget.configure(height=1, state="disabled")
        self.text_widget = text_widget

        copy_btn = ctk.CTkButton(
            column, text="Copy", width=50, height=20, font=("", 10),
            fg_color="transparent", text_color="gray60", hover_color=("gray80", "gray25"),
            command=lambda: self._copy_text(text),
        )
        copy_btn.pack(anchor=anchor_side, pady=(2, 0))

    def _copy_text(self, text: str):
        top = self.winfo_toplevel()
        top.clipboard_clear()
        top.clipboard_append(text)

    def finalize_height(self):
        """Must be called after this widget is actually packed into the
        window tree -- display-line wrapping can't be measured accurately
        before that, and calling it too early silently produces garbage
        heights."""
        self.text_widget.update_idletasks()
        boundaries = self.text_widget.count("1.0", "end-1c", "displaylines")
        # count() returns the number of line-wrap boundaries crossed, which
        # is (visual line count - 1); it returns None instead of (0,) when
        # the text fits on a single display line.
        lines = (boundaries[0] if boundaries else 0) + 1
        self.text_widget.configure(state="normal")
        self.text_widget.configure(height=max(1, lines))
        self.text_widget.configure(state="disabled")


class ChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x680")
        self.minsize(720, 480)
        self._set_window_icon()

        self.current_session_id: str | None = None
        self.is_sending = False
        self.tray: "TrayIcon | None" = None

        self._check_api_key()
        self._build_layout()
        self._refresh_sidebar()
        self._start_new_chat(select_existing_if_none=True)
        self._start_tray()
        self.protocol("WM_DELETE_WINDOW", self._on_close_button)

    def _set_window_icon(self):
        try:
            icon_image = tk.PhotoImage(file=str(ICON_PATH))
            self.iconphoto(True, icon_image)
            self._icon_image_ref = icon_image  # keep a reference, Tk drops unreferenced images
        except Exception:
            pass  # icon is cosmetic -- never block startup over it

    def _start_tray(self):
        if not TRAY_AVAILABLE:
            return
        try:
            self.tray = TrayIcon(self)
            self.tray.start()
        except Exception:
            self.tray = None  # tray is a nice-to-have; never block the app over it

    def _on_close_button(self):
        if TRAY_AVAILABLE and self.tray:
            self.withdraw()  # hide to tray instead of quitting
        else:
            self.destroy()

    # --- setup -------------------------------------------------------

    def _check_api_key(self):
        try:
            require_api_key()
        except RuntimeError:
            messagebox.showwarning(
                "API key missing",
                "GROQ_API_KEY isn't set.\n\n"
                "Create a .env file in the project root (copy .env.example), "
                "add a free key from console.groq.com/keys, then restart the app.",
            )

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        sidebar = ctk.CTkFrame(self, width=SIDEBAR_WIDTH, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nswe")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(4, weight=1)

        new_chat_btn = ctk.CTkButton(sidebar, text="+ New chat", command=self._start_new_chat)
        new_chat_btn.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="we")

        memory_btn = ctk.CTkButton(
            sidebar, text="\U0001F9E0 Memory", command=self._open_memory_window,
            fg_color="transparent", border_width=1, border_color="gray40",
        )
        memory_btn.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="we")

        audit_btn = ctk.CTkButton(
            sidebar, text="\U0001F6E1 Audit log", command=self._open_audit_log_window,
            fg_color="transparent", border_width=1, border_color="gray40",
        )
        audit_btn.grid(row=2, column=0, padx=12, pady=(0, 6), sticky="we")

        export_btn = ctk.CTkButton(
            sidebar, text="\u2913 Export chat", command=self._export_chat,
            fg_color="transparent", border_width=1, border_color="gray40",
        )
        export_btn.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="we")

        self.session_list_frame = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        self.session_list_frame.grid(row=4, column=0, sticky="nswe", padx=6)

        model_label = ctk.CTkLabel(
            sidebar, text=f"Model: {settings.model}", text_color="gray60", font=("", 11)
        )
        model_label.grid(row=5, column=0, padx=12, pady=(6, 12), sticky="w")

        # --- Chat area ---
        chat_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        chat_container.grid(row=0, column=1, sticky="nswe")
        chat_container.grid_columnconfigure(0, weight=1)
        chat_container.grid_rowconfigure(0, weight=1)

        self.messages_frame = ctk.CTkScrollableFrame(chat_container, fg_color="transparent")
        self.messages_frame.grid(row=0, column=0, sticky="nswe", padx=8, pady=(12, 0))
        self.messages_frame.grid_columnconfigure(0, weight=1)

        input_row = ctk.CTkFrame(chat_container, fg_color="transparent")
        input_row.grid(row=1, column=0, sticky="we", padx=12, pady=12)
        input_row.grid_columnconfigure(0, weight=1)

        self.input_box = ctk.CTkTextbox(input_row, height=60, wrap="word")
        self.input_box.grid(row=0, column=0, sticky="we", padx=(0, 8))
        self.input_box.bind("<Return>", self._on_enter_key)
        self.input_box.bind("<Shift-Return>", lambda e: None)  # allow newline

        self.send_button = ctk.CTkButton(input_row, text="Send", width=80, command=self._send_message)
        self.send_button.grid(row=0, column=1, sticky="s")

        self.status_label = ctk.CTkLabel(chat_container, text="", text_color="gray60", font=("", 11))
        self.status_label.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 8))

    # --- sidebar ------------------------------------------------------

    def _refresh_sidebar(self):
        for widget in self.session_list_frame.winfo_children():
            widget.destroy()

        for session in list_sessions():
            row = ctk.CTkFrame(self.session_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            is_active = session["session_id"] == self.current_session_id
            btn = ctk.CTkButton(
                row,
                text=session["title"][:28],
                anchor="w",
                fg_color=("gray80", "gray25") if is_active else "transparent",
                command=lambda sid=session["session_id"]: self._switch_session(sid),
            )
            btn.pack(side="left", fill="x", expand=True)

            del_btn = ctk.CTkButton(
                row, text="x", width=28, fg_color="transparent", text_color="gray60",
                command=lambda sid=session["session_id"]: self._delete_session(sid),
            )
            del_btn.pack(side="right")

    def _start_new_chat(self, select_existing_if_none: bool = False):
        existing = list_sessions()
        if select_existing_if_none and existing:
            self._switch_session(existing[0]["session_id"])
            return
        session_id = create_session()
        self._switch_session(session_id)
        self._refresh_sidebar()

    def _switch_session(self, session_id: str):
        self.current_session_id = session_id
        self._refresh_sidebar()
        self._render_history()

    def _delete_session(self, session_id: str):
        delete_session(session_id)
        if session_id == self.current_session_id:
            self.current_session_id = None
            self._start_new_chat(select_existing_if_none=True)
        else:
            self._refresh_sidebar()

    # --- chat rendering -------------------------------------------------

    def _render_history(self):
        for widget in self.messages_frame.winfo_children():
            widget.destroy()

        from app.memory import get_history  # local import keeps startup light

        for msg in get_history(self.current_session_id, limit=200):
            text = self._extract_text(msg["content"])
            if text:
                self._add_bubble(text, is_user=msg["role"] == "user")

    @staticmethod
    def _extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            return "\n".join(p for p in parts if p)
        return ""

    def _add_bubble(self, text: str, is_user: bool):
        bubble = ChatBubble(self.messages_frame, text, is_user)
        bubble.pack(fill="x")
        self.after(10, bubble.finalize_height)
        self.after(50, lambda: self.messages_frame._parent_canvas.yview_moveto(1.0))

    # --- sending ----------------------------------------------------

    def _on_enter_key(self, event):
        # Plain Enter sends; Shift+Enter (bound separately) inserts a newline.
        self._send_message()
        return "break"

    def _send_message(self):
        if self.is_sending:
            return
        text = self.input_box.get("1.0", "end").strip()
        if not text:
            return

        title = self._auto_title_if_new(text)
        touch_session(self.current_session_id, title=title)

        self.input_box.delete("1.0", "end")
        self._add_bubble(text, is_user=True)
        self._set_sending(True)

        thread = threading.Thread(target=self._call_assistant, args=(text,), daemon=True)
        thread.start()

    def _auto_title_if_new(self, text: str) -> str | None:
        """If this session has no prior history, rename it based on the
        first message instead of leaving it as 'New chat'."""
        from app.memory import get_history

        history = get_history(self.current_session_id, limit=1)
        if history:
            return None
        return text[:40] + ("..." if len(text) > 40 else "")

    def _call_assistant(self, user_text: str):
        from app.groq_client import chat as run_chat

        try:
            reply = run_chat(self.current_session_id, user_text)
            error = None
        except Exception as e:  # surfaced in UI, not a crash
            reply = None
            error = str(e)

        self.after(0, lambda: self._on_assistant_reply(reply, error))

    def _on_assistant_reply(self, reply: str | None, error: str | None):
        self._set_sending(False)
        if error:
            self.status_label.configure(text=f"Error: {error}", text_color="#dc2626")
            return
        self.status_label.configure(text="")
        self._add_bubble(reply, is_user=False)
        self._refresh_sidebar()

    def _set_sending(self, sending: bool):
        self.is_sending = sending
        self.send_button.configure(state="disabled" if sending else "normal", text="Sending..." if sending else "Send")

    def destroy(self):
        if self.tray:
            self.tray.stop()
        super().destroy()

    # --- long-term memory viewer ---------------------------------------

    def _open_memory_window(self):
        from app.long_term_memory import clear_facts, delete_fact, get_facts

        window = ctk.CTkToplevel(self)
        window.title("Robert's memory")
        window.geometry("480x520")
        window.transient(self)

        header = ctk.CTkLabel(
            window,
            text="Facts Robert remembers across every chat",
            font=("", 14, "bold"),
        )
        header.pack(padx=16, pady=(16, 8), anchor="w")

        list_frame = ctk.CTkScrollableFrame(window, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        def render_facts():
            for widget in list_frame.winfo_children():
                widget.destroy()
            facts = get_facts()
            if not facts:
                empty = ctk.CTkLabel(
                    list_frame, text="Nothing saved yet -- Robert will remember\nthings you tell him worth keeping.",
                    text_color="gray60", justify="left",
                )
                empty.pack(anchor="w", padx=8, pady=8)
                return
            for fact in facts:
                row = ctk.CTkFrame(list_frame, fg_color="transparent")
                row.pack(fill="x", pady=3)
                label = ctk.CTkLabel(row, text=fact["fact"], wraplength=360, justify="left", anchor="w")
                label.pack(side="left", fill="x", expand=True, padx=(4, 8))
                del_btn = ctk.CTkButton(
                    row, text="x", width=28, fg_color="transparent", text_color="gray60",
                    command=lambda fid=fact["id"]: (delete_fact(fid), render_facts()),
                )
                del_btn.pack(side="right")

        render_facts()

        button_row = ctk.CTkFrame(window, fg_color="transparent")
        button_row.pack(fill="x", padx=12, pady=(0, 16))

        clear_btn = ctk.CTkButton(
            button_row, text="Clear all", fg_color="#7F1D1D", hover_color="#991B1B",
            command=lambda: (clear_facts(), render_facts()),
        )
        clear_btn.pack(side="left")

        close_btn = ctk.CTkButton(button_row, text="Close", command=window.destroy)
        close_btn.pack(side="right")

    # --- audit log viewer -----------------------------------------------

    def _open_audit_log_window(self):
        from app.audit_log import clear_log, get_recent_calls
        import datetime

        window = ctk.CTkToplevel(self)
        window.title("Robert's tool-call audit log")
        window.geometry("560x560")
        window.transient(self)

        header = ctk.CTkLabel(
            window,
            text="Every tool call Robert has made",
            font=("", 14, "bold"),
        )
        header.pack(padx=16, pady=(16, 4), anchor="w")

        subheader = ctk.CTkLabel(
            window,
            text="A security-relevant record: what was called, with what arguments, and what came back.",
            text_color="gray60", justify="left", wraplength=520,
        )
        subheader.pack(padx=16, pady=(0, 8), anchor="w")

        list_frame = ctk.CTkScrollableFrame(window, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        def render_log():
            for widget in list_frame.winfo_children():
                widget.destroy()
            calls = get_recent_calls()
            if not calls:
                empty = ctk.CTkLabel(list_frame, text="No tool calls yet.", text_color="gray60")
                empty.pack(anchor="w", padx=8, pady=8)
                return
            for call in calls:
                entry = ctk.CTkFrame(list_frame, fg_color="#1a1a1f", corner_radius=8)
                entry.pack(fill="x", pady=4, padx=2)

                when = datetime.datetime.fromtimestamp(call["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
                title = ctk.CTkLabel(
                    entry, text=f"{call['tool_name']}  ·  {when}",
                    font=("", 12, "bold"), anchor="w",
                )
                title.pack(fill="x", padx=10, pady=(8, 0))

                args_label = ctk.CTkLabel(
                    entry, text=f"args: {call['arguments']}", text_color="gray70",
                    anchor="w", justify="left", wraplength=490, font=("Consolas", 10),
                )
                args_label.pack(fill="x", padx=10, pady=(2, 0))

                result_str = str(call["result"])
                if len(result_str) > 300:
                    result_str = result_str[:300] + "..."
                result_label = ctk.CTkLabel(
                    entry, text=f"result: {result_str}", text_color="gray60",
                    anchor="w", justify="left", wraplength=490, font=("Consolas", 10),
                )
                result_label.pack(fill="x", padx=10, pady=(2, 8))

        render_log()

        button_row = ctk.CTkFrame(window, fg_color="transparent")
        button_row.pack(fill="x", padx=12, pady=(0, 16))

        clear_btn = ctk.CTkButton(
            button_row, text="Clear log", fg_color="#7F1D1D", hover_color="#991B1B",
            command=lambda: (clear_log(), render_log()),
        )
        clear_btn.pack(side="left")

        close_btn = ctk.CTkButton(button_row, text="Close", command=window.destroy)
        close_btn.pack(side="right")

    # --- export conversation ---------------------------------------------

    def _export_chat(self):
        from app.memory import get_history

        if not self.current_session_id:
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All files", "*.*")],
            initialfile="robert-chat.md",
            title="Export conversation",
        )
        if not path:
            return

        lines = [f"# Conversation with Robert\n"]
        for msg in get_history(self.current_session_id, limit=1000):
            text = self._extract_text(msg["content"])
            if not text:
                continue
            speaker = "You" if msg["role"] == "user" else "Robert"
            lines.append(f"**{speaker}:**\n\n{text}\n")

        try:
            Path(path).write_text("\n".join(lines))
            self.status_label.configure(text=f"Exported to {path}", text_color="gray60")
        except OSError as e:
            self.status_label.configure(text=f"Export failed: {e}", text_color="#dc2626")


def main():
    app = ChatApp()
    app.mainloop()


if __name__ == "__main__":
    main()
