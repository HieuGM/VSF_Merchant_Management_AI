"""Deterministic reference, scope, and number validation for agent claims."""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from models.merchant_orchestration import (
    EvidenceClaim,
    EvidenceValidationResult,
    MerchantExecutionContext,
    RejectedClaim,
)
from repositories.evidence_repository import EvidenceRepository
from services.merchant_data_policy import PUBLIC_DIMENSIONS


class EvidenceValidationService:
    def __init__(self, db: Session) -> None:
        self._repository = EvidenceRepository(db)

    @staticmethod
    def _policy_rejection(
        evidence: dict[str, Any],
        context: MerchantExecutionContext,
    ) -> str | None:
        merchant_id = evidence.get("merchant_id")
        if merchant_id in (None, context.owner_merchant_id):
            return None
        evidence_type = evidence.get("type")
        if evidence_type in {
            "operational_metric",
            "complaint",
            "delivery_feedback",
        }:
            return "competitor_private"
        if evidence_type in {"profile", "dimension_evidence"}:
            if evidence.get("dimension") not in PUBLIC_DIMENSIONS:
                return "competitor_private"
        return None

    def validate_claims(
        self,
        claims: list[EvidenceClaim],
        context: MerchantExecutionContext,
        aggregate_snapshots: dict[str, dict[str, Any]],
    ) -> EvidenceValidationResult:
        valid: list[EvidenceClaim] = []
        rejected: list[RejectedClaim] = []
        all_resolved: dict[str, dict[str, Any]] = {}

        for claim in claims:
            claim_resolved: dict[str, dict[str, Any]] = {}
            rejection_reason: str | None = None
            rejection_ref: str | None = None
            for ref in claim.evidence_refs:
                evidence = self._repository.resolve_reference(
                    ref,
                    aggregate_snapshots,
                )
                if evidence is None:
                    rejection_reason = "missing_evidence"
                    rejection_ref = ref
                    break
                policy_reason = self._policy_rejection(evidence, context)
                if policy_reason:
                    rejection_reason = policy_reason
                    rejection_ref = ref
                    break
                claim_resolved[ref] = evidence

            if rejection_reason is None:
                for cited in claim.numbers:
                    evidence = claim_resolved.get(cited.evidence_ref)
                    source_value = evidence.get("value") if evidence else None
                    if (
                        isinstance(source_value, bool)
                        or not isinstance(source_value, (int, float))
                        or not math.isclose(
                            float(cited.value),
                            float(source_value),
                            rel_tol=1e-6,
                            abs_tol=1e-6,
                        )
                    ):
                        rejection_reason = "number_mismatch"
                        rejection_ref = cited.evidence_ref
                        break

            if rejection_reason:
                rejected.append(
                    RejectedClaim(
                        claim=claim,
                        reason=rejection_reason,
                        evidence_ref=rejection_ref,
                    )
                )
                continue

            valid.append(claim)
            all_resolved.update(claim_resolved)

        return EvidenceValidationResult(
            status="ok" if valid else "insufficient_data",
            valid_claims=valid,
            rejected=rejected,
            resolved_evidence=all_resolved,
        )
