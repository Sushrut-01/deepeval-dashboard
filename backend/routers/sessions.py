from fastapi import APIRouter, HTTPException
from backend.services.session_builder import get_all_sessions, get_session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("")
def list_sessions():
    return get_all_sessions()


@router.get("/{session_id}")
def get_session_detail(session_id: str):
    s = get_session(session_id)
    if not s:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return s
