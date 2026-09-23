"""
FastAPI entrypoint. Run with:
    uvicorn app.main:app --reload
"""
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.groq_client import chat
from app.memory import clear_session

app = FastAPI(
    title="Robert",
    description="A custom Groq-powered assistant with memory, tools, and optional RAG.",
    version="0.1.0",
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, description="Omit to start a new session.")


class ChatResponse(BaseModel):
    session_id: str
    reply: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    try:
        reply = chat(session_id, req.message)
    except RuntimeError as e:
        # e.g. missing API key -- a config problem, not a client error
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(session_id=session_id, reply=reply)


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}
