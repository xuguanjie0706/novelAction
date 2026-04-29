from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.llm_call_log import clear_llm_calls, list_llm_calls

router = APIRouter(prefix="/admin/llm-calls", tags=["admin-llm-calls"])


@router.get("/")
def list_calls(limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)):
    return list_llm_calls(limit=limit, db=db)


@router.delete("/")
def clear_calls(db: Session = Depends(get_db)):
    deleted = clear_llm_calls(db=db)
    return {"deleted": deleted}
