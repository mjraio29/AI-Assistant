from desktop.main import ChatApp

app = ChatApp()
app._add_bubble('Hello! Here is **bold text**, some `inline code`, and a code block:\n```python\ndef hi():\n    return 42\n```\nDoes this look right?', is_user=False)
app._add_bubble('Can you show me markdown formatting?', is_user=True)
app.update()
app.after(5000, app.destroy)
app.mainloop()
