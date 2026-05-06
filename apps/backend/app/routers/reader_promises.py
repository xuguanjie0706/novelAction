from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.database import get_db
from app.models import ReaderPromise, Project
from app.schemas import ReaderPromiseCreate, ReaderPromiseUpdate, ReaderPromiseOut

router = APIRouter(prefix="/projects/{project_id}/reader_promises", tags=["reader_promises"])


@router.get("/", response_model=List[ReaderPromiseOut])
def list_reader_promises(project_id: str, db: Session = Depends(get_db), status: Optional[str] = None):
    q = db.query(ReaderPromise).filter(ReaderPromise.project_id == project_id)
    if status:
        q = q.filter(ReaderPromise.status == status)
    return q.order_by(ReaderPromise.created_at.desc()).all()


@router.get("/{promise_id}", response_model=ReaderPromiseOut)
def get_reader_promise(project_id: str, promise_id: str, db: Session = Depends(get_db)):
    rp = db.query(ReaderPromise).filter(ReaderPromise.id == promise_id, ReaderPromise.project_id == project_id).first()
    if not rp:
        raise HTTPException(404, "ReaderPromise not found")
    return rp


@router.post("/", response_model=ReaderPromiseOut)
def create_reader_promise(project_id: str, payload: ReaderPromiseCreate, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")
    rp = ReaderPromise(
        project_id=project_id,
        **payload.dict(exclude_unset=True)
    )
    db.add(rp)
    db.commit()
    db.refresh(rp)
    return rp


@router.patch("/{promise_id}", response_model=ReaderPromiseOut)
def update_reader_promise(project_id: str, promise_id: str, payload: ReaderPromiseUpdate, db: Session = Depends(get_db)):
    rp = db.query(ReaderPromise).filter(ReaderPromise.id == promise_id, ReaderPromise.project_id == project_id).first()
    if not rp:
        raise HTTPException(404, "ReaderPromise not found")
    for k, v in payload.dict(exclude_unset=True).items():
        setattr(rp, k, v)
    db.commit()
    db.refresh(rp)
    return rp


@router.delete("/{promise_id}")
def delete_reader_promise(project_id: str, promise_id: str, db: Session = Depends(get_db)):
    rp = db.query(ReaderPromise).filter(ReaderPromise.id == promise_id, ReaderPromise.project_id == project_id).first()
    if not rp:
        raise HTTPException(404, "ReaderPromise not found")
    db.delete(rp)
    db.commit()
    return {"ok": True}
