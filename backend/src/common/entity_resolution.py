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
