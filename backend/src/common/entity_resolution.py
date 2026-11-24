"""
Certificate-anchored entity resolution (TrustScore v5.0 §8).

Every scraped source — NTSB, FAA enforcement, DOT OACP — files records against
a *name*, not a certificate. So a lookup by the operator's current marketing
name finds only what was filed under that name. An operator that rebrands
therefore sheds its entire history and scores as though it had none, which is
the failure §8 exists to defeat:

    "the extraction pipeline injects this complete name and address array. An
     event matching any historical identity associated with that certificate
     must be attributed to the active certificate designator."

The designator is the stable key; the names are what change. This module turns
one operator reference into every name its certificate has operated under, so a
lookup can match any of them.

`gtj.certificate_dbas` is populated by scripts/ingest_part135.py from the FAA
Part 135 roster, monthly. Names are never deleted — a name that drops off the
roster is precisely the one an old filing will carry.

Degrades to the supplied name alone if the table is empty or unreachable, so a
missing DBA array narrows results rather than breaking a scoring run.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def resolve_operator_names(
    operator_name: str,
    certificate_designator: Optional[str] = None,
    db_session_factory: Any = None,
) -> List[str]:
    """
    Every normalized name a certificate has been known by.

    Resolution runs in two directions so a caller needs only one of them:

      1. If a designator is supplied, return all names recorded against it.
      2. Otherwise look the designator up *from* the name first — which is what
         makes a lookup work when the caller only knows the current trade name.

    The supplied name is always included, even when the certificate is unknown,
    so this can never return fewer results than a plain name match would.

    Args:
        operator_name: Operator name as the caller knows it.
        certificate_designator: 4-char FAA ID, when already known.
        db_session_factory: Callable returning a session; defaults to
            SessionLocal. Injectable so tests never touch a live database.

    Returns:
        Distinct normalized names, the supplied one first. Never empty unless
        the input normalizes to nothing.
    """
    from src.trustscore.adapter_v5 import normalize_operator_name

    primary = normalize_operator_name(operator_name)
    names: List[str] = [primary] if primary else []

    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal
            db_session_factory = SessionLocal

        from sqlalchemy import text

        session = db_session_factory()
        designator = (certificate_designator or "").strip().upper()

        # Reverse lookup: the caller knows a name but not the certificate.
        # Without this, an operator referred to by a historical name would
        # resolve to nothing but itself.
        if not designator and primary:
            row = session.execute(
                text("""
                    SELECT certificate_designator
                    FROM gtj.certificate_dbas
                    WHERE operator_name_normalized = :name
                    LIMIT 1
                """),
                {"name": primary},
            ).first()
            if row:
                designator = row[0]

        if designator:
            rows = session.execute(
                text("""
                    SELECT operator_name_normalized
                    FROM gtj.certificate_dbas
                    WHERE certificate_designator = :designator
                """),
                {"designator": designator},
            )
            for row in rows:
                if row[0] and row[0] not in names:
                    names.append(row[0])
    except Exception as exc:  # pragma: no cover - defensive
        # A missing table or an unreachable database must narrow the search,
        # never fail the score.
        logger.warning("Entity resolution failed for %s: %s", operator_name, exc)
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass

    return names


def resolve_certificate(
    operator_name: str,
    db_session_factory: Any = None,
) -> Optional[str]:
    """
    The certificate designator an operator name belongs to, if recorded.

    Returns None when the name is not in the DBA array — which is the signal
    that a result set is name-anchored rather than certificate-anchored, and
    should be reported as such rather than treated as complete.
    """
    from src.trustscore.adapter_v5 import normalize_operator_name

    primary = normalize_operator_name(operator_name)
    if not primary:
        return None

    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal
            db_session_factory = SessionLocal

        from sqlalchemy import text

        session = db_session_factory()
        row = session.execute(
            text("""
                SELECT certificate_designator
                FROM gtj.certificate_dbas
                WHERE operator_name_normalized = :name
                LIMIT 1
            """),
            {"name": primary},
        ).first()
        return row[0] if row else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Certificate lookup failed for %s: %s", operator_name, exc)
        return None
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def resolve_trade_names(
    operator_name: str,
    certificate_designator: Optional[str] = None,
    db_session_factory: Any = None,
) -> List[dict]:
    """
    Every name a certificate has traded under, in DISPLAY form, for reporting.

    Distinct from `resolve_operator_names`, which returns normalized strings
    ("jet excellence") suitable for matching a database column and unsuitable
    for printing. This returns the names as recorded, plus the metadata a
    reader needs to interpret them.

    WHY A BROKER NEEDS THIS. A charter is sold under a trade name, while the
    safety and enforcement record attaches to the certificate. Those can differ:
    certificate 3KSC is held by Asher Air LLC and also trades as Blue Spruce
    Air. A broker quoted by one has no way to know the other is the same
    operator — and that is precisely the arrangement §8 exists to defeat. 44 of
    1,870 certificates currently carry more than one name.

    Each entry carries:
        name        as recorded, for display
        is_current  whether the roster still lists it
        first_seen  earliest date observed on the roster
        last_seen   most recent date observed

    `is_current` matters: a name no longer on the roster is a FORMER identity,
    which reads very differently from a concurrent dba and must not be
    presented as one.

    Args:
        operator_name: Operator name as the caller knows it.
        certificate_designator: 4-char FAA ID, when already known.
        db_session_factory: Callable returning a session; defaults to
            SessionLocal.

    Returns:
        Dicts ordered current-first then alphabetically. Empty when the
        certificate is unknown — which is not the same as "no other names",
        and callers should report it as unresolved rather than as a single
        identity. Never raises.
    """
    from src.trustscore.adapter_v5 import normalize_operator_name

    primary = normalize_operator_name(operator_name)
    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal
            db_session_factory = SessionLocal

        from sqlalchemy import text

        session = db_session_factory()
        designator = (certificate_designator or "").strip().upper()

        # Same reverse lookup as resolve_operator_names: the caller may know
        # only a trade name, possibly a historical one.
        if not designator and primary:
            row = session.execute(
                text("""
                    SELECT certificate_designator
                    FROM gtj.certificate_dbas
                    WHERE operator_name_normalized = :name
                    LIMIT 1
                """),
                {"name": primary},
            ).first()
            if row:
                designator = row[0]

        if not designator:
            return []

        rows = session.execute(
            text("""
                SELECT operator_name, is_current, first_seen, last_seen
                FROM gtj.certificate_dbas
                WHERE certificate_designator = :designator
                ORDER BY is_current DESC NULLS LAST, operator_name
            """),
            {"designator": designator},
        ).mappings().all()

        return [
            {
                "name": row["operator_name"],
                "is_current": bool(row["is_current"]),
                "first_seen": str(row["first_seen"]) if row["first_seen"] else None,
                "last_seen": str(row["last_seen"]) if row["last_seen"] else None,
            }
            for row in rows
            if row["operator_name"]
        ]
    except Exception as exc:  # pragma: no cover - defensive
        # Consistent with the rest of this module: a reporting detail must
        # never fail a score.
        logger.warning("Trade-name lookup failed for %s: %s", operator_name, exc)
        return []
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def resolve_certificate_age_years(
    operator_name: str,
    certificate_designator: str = "",
    db_session_factory=None,
) -> "tuple[float, bool] | tuple[None, bool]":
    """
    Years since the certificate was ISSUED, from the FAA 14 CFR Search export.

    Returns (years, is_estimated). `is_estimated` is always False here: this is
    an observed issuance date, which is exactly what §3 asks for and what we
    have never had before.

    WHY THIS MATTERS MORE THAN IT LOOKS. The scoring path previously fell back
    to a HARDCODED 10.0 years whenever `gtj.operators.business_started_date`
    was missing — 838 of 1,767 certificated operators. Agecert drives Cs, and
    Cs multiplies the entire composite, so every one of those scores rested on
    an invented input. Worse, business_started_date is when the COMPANY began,
    not when the FAA issued the certificate; §3 wants the latter.

    Returns (None, False) when no date is held, so the caller can tell
    "unknown" apart from a real zero and keep its own fallback rather than
    silently scoring a brand-new certificate as mature.

    Args:
        operator_name: Operator name, trade name or legal.
        certificate_designator: 4-char FAA ID, preferred when known.
        db_session_factory: Callable returning a session; defaults to
            SessionLocal.
    """
    from datetime import date

    from src.trustscore.adapter_v5 import normalize_operator_name

    designator = (certificate_designator or "").strip().upper()
    normalized = normalize_operator_name(operator_name or "")
    if not designator and not normalized:
        return None, False

    session = None
    try:
        if db_session_factory is None:
            from src.common.config import SessionLocal

            db_session_factory = SessionLocal

        from sqlalchemy import text

        session = db_session_factory()
        if designator:
            row = session.execute(
                text("""
                    SELECT certificate_issued_date
                    FROM gtj.certificate_dbas
                    WHERE certificate_designator = :d
                      AND certificate_issued_date IS NOT NULL
                    LIMIT 1
                """),
                {"d": designator},
            ).first()
        else:
            row = session.execute(
                text("""
                    SELECT certificate_issued_date
                    FROM gtj.certificate_dbas
                    WHERE operator_name_normalized = :n
                      AND certificate_issued_date IS NOT NULL
                    LIMIT 1
                """),
                {"n": normalized},
            ).first()

        if not row or not row[0]:
            return None, False

        issued = row[0]
        years = (date.today() - issued).days / 365.25
        # A future date would give a negative age and a nonsensical Cs. The
        # importer already rejects those, so this is belt-and-braces.
        if years < 0:
            return None, False
        return round(years, 1), False
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Certificate age lookup failed: %s", exc)
        return None, False
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
