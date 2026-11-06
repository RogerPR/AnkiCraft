"""Apply operations recorded in WoW (SavedVariables) to the Anki collection."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from anki.scheduler_pb2 import CardAnswer

from . import fsutil, luaser
from .render import plain_to_html

ACK_CONFIG_KEY = "ankicraft_acks"
SV_VARIABLE = "AnkiCraftDB"
MAX_ANSWER_MS = 60_000
_RATINGS = {
    1: CardAnswer.AGAIN,
    2: CardAnswer.HARD,
    3: CardAnswer.GOOD,
    4: CardAnswer.EASY,
}


@dataclass
class SyncResult:
    install_id: str = ""
    answered: int = 0
    added: int = 0
    changed: int = 0
    conflicts: int = 0
    errors: list[str] = field(default_factory=list)
    last_seq: int = 0

    @property
    def total(self) -> int:
        return self.answered + self.added + self.changed + self.conflicts + len(self.errors)

    def summary(self) -> str:
        parts = [f"{self.answered} reviews", f"{self.added} new notes", f"{self.changed} card changes"]
        if self.conflicts:
            parts.append(f"{self.conflicts} skipped (reviewed elsewhere)")
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts)


def get_acks(col) -> dict[str, int]:
    acks = col.get_config(ACK_CONFIG_KEY, {}) or {}
    return {str(k): int(v) for k, v in acks.items()}


def set_ack(col, install_id: str, seq: int) -> None:
    acks = get_acks(col)
    acks[install_id] = seq
    col.set_config(ACK_CONFIG_KEY, acks)


def read_savedvariables(path: str) -> dict[str, Any] | None:
    data = fsutil.read_bytes(path)
    if not data.strip():
        return None
    parsed = luaser.parse_assignments(data)
    db = parsed.get(SV_VARIABLE)
    return db if isinstance(db, dict) else None


def pending_ops(db: dict[str, Any]) -> list[dict[str, Any]]:
    ops = [op for op in luaser.as_list(db.get("pending")) if isinstance(op, dict)]
    ops = [op for op in ops if isinstance(op.get("seq"), int)]
    ops.sort(key=lambda o: o["seq"])
    return ops


def _cid(op: dict) -> int:
    return int(str(op.get("cid")))


def _answered_at_ms(op: dict, now_s: float) -> int:
    at = op.get("at")
    if not isinstance(at, (int, float)) or at <= 0:
        return int(now_s * 1000)
    # clamp clock skew/garbage: no future answers, nothing older than 60 days
    at = min(float(at), now_s)
    at = max(at, now_s - 60 * 86400)
    # sub-second offset keeps revlog ids unique for answers in the same second
    return int(at * 1000) + int(op.get("seq", 0)) % 1000


def apply_answer(col, op: dict, res: SyncResult, now_s: float) -> None:
    rating = _RATINGS.get(int(op.get("ease", 0)))
    if rating is None:
        res.errors.append(f"seq {op.get('seq')}: invalid ease {op.get('ease')!r}")
        return
    card = col.get_card(_cid(op))
    expected = op.get("reps")
    if (isinstance(expected, int) and card.reps != expected) or card.queue < 0:
        res.conflicts += 1
        return
    states = col._backend.get_scheduling_states(card.id)
    card.start_timer()
    answer = col.sched.build_answer(card=card, states=states, rating=rating)
    answer.answered_at_millis = _answered_at_ms(op, now_s)
    ms = op.get("ms")
    answer.milliseconds_taken = max(0, min(int(ms), MAX_ANSWER_MS)) if isinstance(ms, (int, float)) else 0
    col.sched.answer_card(answer)
    res.answered += 1


def apply_add(col, op: dict, res: SyncResult) -> None:
    model = col.models.by_name(str(op.get("notetype", "Basic")))
    if not model:
        res.errors.append(f"seq {op.get('seq')}: note type {op.get('notetype')!r} not found")
        return
    did = op.get("deck")
    try:
        did = int(str(did))
    except (TypeError, ValueError):
        did = None
    if not did or not col.decks.get(did, default=False):
        did = col.decks.get_current_id()
    note = col.new_note(model)
    fields = op.get("fields")
    if isinstance(fields, list):
        names = [f["name"] for f in model["flds"]]
        fields = {names[i]: v for i, v in enumerate(fields) if i < len(names)}
    if not isinstance(fields, dict):
        fields = {}
    for name, value in fields.items():
        if name in note and isinstance(value, str):
            note[name] = plain_to_html(value)
    tags = op.get("tags")
    if isinstance(tags, str) and tags.strip():
        note.tags = col.tags.split(tags)
    note.add_tag("AnkiCraft")
    if not note.fields[0].strip():
        res.errors.append(f"seq {op.get('seq')}: first field is empty, note not added")
        return
    col.add_note(note, did)
    res.added += 1


def apply_card_change(col, op: dict, res: SyncResult) -> None:
    t = op.get("t")
    cid = _cid(op)
    card = col.get_card(cid)
    if t == "suspend":
        col.sched.suspend_cards([cid])
    elif t == "bury":
        col.sched.bury_cards([cid])
    elif t == "flag":
        flag = int(op.get("flag", 0))
        if not 0 <= flag <= 7:
            raise ValueError(f"bad flag {flag}")
        col.set_user_flag_for_cards(flag, [cid])
    elif t == "mark":
        note = card.note()
        if op.get("on"):
            note.add_tag("marked")
        else:
            note.remove_tag("marked")
        col.update_note(note)
    else:
        res.errors.append(f"seq {op.get('seq')}: unknown op {t!r}")
        return
    res.changed += 1


def apply_ops(col, install_id: str, ops: list[dict[str, Any]], now_s: float | None = None) -> SyncResult:
    """Apply ops newer than the stored ack for install_id. Idempotent."""
    now_s = time.time() if now_s is None else now_s
    acks = get_acks(col)
    last = acks.get(install_id, 0)
    res = SyncResult(install_id=install_id, last_seq=last)
    for op in ops:
        seq = op["seq"]
        if seq <= last:
            continue
        try:
            t = op.get("t")
            if t == "answer":
                apply_answer(col, op, res, now_s)
            elif t == "add":
                apply_add(col, op, res)
            else:
                apply_card_change(col, op, res)
        except Exception as e:  # one bad op must not block the queue
            msg = str(e) or type(e).__name__
            if "not found" in msg.lower() or type(e).__name__ == "NotFoundError":
                res.conflicts += 1
            else:
                res.errors.append(f"seq {seq}: {msg}")
        res.last_seq = max(res.last_seq, seq)
    if res.last_seq != last:
        set_ack(col, install_id, res.last_seq)
    return res


def sync_savedvariables(col, path: str, now_s: float | None = None) -> SyncResult | None:
    db = read_savedvariables(path)
    if not db:
        return None
    install_id = db.get("installId")
    if not isinstance(install_id, str) or not install_id:
        return None
    return apply_ops(col, install_id, pending_ops(db), now_s)
