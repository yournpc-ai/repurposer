"""Notifications router — the bell panel's data source.

The dropdown polls ``GET /notifications`` and marks everything read on open;
there is deliberately no per-item read endpoint and no pagination (the panel
shows the most recent N).
"""

from fastapi import APIRouter, Depends, Query, status

from app.dependencies import DBDep, get_current_user_required
from app.models.schemas import NotificationListResponse
from app.models.tables import User
from app.services import notifications as svc

router = APIRouter()


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    db: DBDep,
    user: User = Depends(get_current_user_required),
    limit: int = Query(default=30, le=100),
) -> NotificationListResponse:
    items, unread = await svc.list_notifications(db, user.id, limit=limit)
    return NotificationListResponse(items=items, unread_count=unread)


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(
    db: DBDep,
    user: User = Depends(get_current_user_required),
) -> None:
    await svc.mark_all_read(db, user.id)
    await db.commit()
