from fastapi import APIRouter, Depends, HTTPException

from config import DEMO_MODE
from database import get_db, now
from deps import current_user
from services import portfolio as pf

router = APIRouter(prefix="/api/parental-controls", tags=["parental"])

# no real parent accounts yet
# approve and deny are just the demo override (DEMO_MODE only), saved with demo_override = 1


def history(db, uid):
    rows = db.execute(
        "SELECT * FROM permissions WHERE user_id = ? ORDER BY id DESC LIMIT 20", (uid,)
    ).fetchall()
    return [
        {"id": r["id"], "status": r["status"], "requested_at": r["requested_at"],
         "decided_at": r["decided_at"], "demo_override": bool(r["demo_override"]), "note": r["note"]}
        for r in rows
    ]


@router.get("/status")
def status(user=Depends(current_user), db=Depends(get_db)):
    return {
        "status": pf.permission_status(db, user["id"]),
        "age_band": user["age_band"],
        "demo_mode": DEMO_MODE,
        "history": history(db, user["id"]),
    }


@router.post("/request")
def request_permission(user=Depends(current_user), db=Depends(get_db)):
    current = pf.permission_status(db, user["id"])
    if current in ("approved", "pending"):
        raise HTTPException(400, "You already have a %s request." % current)
    db.execute(
        "INSERT INTO permissions (user_id, status, requested_at, demo_override, note) "
        "VALUES (?, 'pending', ?, 0, 'Waiting for a parent')",
        (user["id"], now()),
    )
    db.commit()
    return {"ok": True}


def decide(db, user, new_status):
    if not DEMO_MODE:
        raise HTTPException(403, "Only a parent can do this. The demo override is turned off.")
    if pf.permission_status(db, user["id"]) != "pending":
        raise HTTPException(400, "There is no pending request.")
    db.execute(
        "UPDATE permissions SET status = ?, decided_at = ?, demo_override = 1, note = ? "
        "WHERE id = (SELECT MAX(id) FROM permissions WHERE user_id = ?)",
        (new_status, now(), "DEMO PARENT OVERRIDE. Not real parental consent.", user["id"]),
    )
    db.commit()


@router.post("/approve")
def approve(user=Depends(current_user), db=Depends(get_db)):
    decide(db, user, "approved")
    return {"ok": True}


@router.post("/deny")
def deny(user=Depends(current_user), db=Depends(get_db)):
    decide(db, user, "denied")
    return {"ok": True}
