from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import QualityDebt
from app.schemas.quality_debt import QualityDebtOut, QualityDebtUpdate

router = APIRouter(prefix="/projects/{project_id}/quality-debts", tags=["quality-debts"])


@router.get("/", response_model=List[QualityDebtOut])
def list_quality_debts(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(QualityDebt).filter(QualityDebt.project_id == project_id)
    if status:
        query = query.filter(QualityDebt.status == status)
    return query.order_by(QualityDebt.source_chapter_number.asc(), QualityDebt.created_at.asc()).all()


@router.patch("/{debt_id}", response_model=QualityDebtOut)
def update_quality_debt(
    project_id: str,
    debt_id: str,
    payload: QualityDebtUpdate,
    db: Session = Depends(get_db),
):
    debt = db.query(QualityDebt).filter(
        QualityDebt.project_id == project_id,
        QualityDebt.id == debt_id,
    ).first()
    if not debt:
        raise HTTPException(404, "Quality debt not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(debt, field, value)
    db.commit()
    db.refresh(debt)
    return debt
