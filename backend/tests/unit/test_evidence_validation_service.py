from __future__ import annotations

from models.merchant_orchestration import (
    CitedNumber,
    EvidenceClaim,
    MerchantExecutionContext,
)
from services.evidence_validation_service import EvidenceValidationService


OWNER_CONTEXT = MerchantExecutionContext(
    trace_id="tr-evidence",
    session_id="sess-evidence",
    owner_merchant_id="m_evidence_owner",
)


def test_invalid_number_drops_claim(db_session):
    from database.models import Merchant
    from relational_test_fixtures import seed_relational_profile

    db_session.add(
        Merchant(
            merchant_id=OWNER_CONTEXT.owner_merchant_id,
            name="Owner Evidence",
            cuisine="Món Việt",
            city="Hà Nội",
            city_slug="ha_noi",
        )
    )
    seed_relational_profile(
        db_session,
        OWNER_CONTEXT.owner_merchant_id,
        scores={},
        prep_minutes=18.0,
    )
    db_session.commit()
    claim = EvidenceClaim(
        claim="Thời gian chuẩn bị là 99 phút",
        evidence_refs=[
            f"metric:{OWNER_CONTEXT.owner_merchant_id}:avg_prep_time_min"
        ],
        numbers=[
            CitedNumber(
                value=99,
                evidence_ref=(
                    f"metric:{OWNER_CONTEXT.owner_merchant_id}:avg_prep_time_min"
                ),
                field="avg_prep_time_min",
            )
        ],
    )

    result = EvidenceValidationService(db_session).validate_claims(
        [claim],
        context=OWNER_CONTEXT,
        aggregate_snapshots={},
    )

    assert result.valid_claims == []
    assert result.status == "insufficient_data"
    assert result.rejected[0].reason == "number_mismatch"


def test_competitor_metric_reference_is_policy_blocked(db_session):
    from database.models import Merchant
    from relational_test_fixtures import seed_relational_profile

    competitor_id = "m_evidence_competitor"
    db_session.add(
        Merchant(
            merchant_id=competitor_id,
            name="Competitor Evidence",
            cuisine="Món Việt",
            city="Hà Nội",
            city_slug="ha_noi",
        )
    )
    seed_relational_profile(db_session, competitor_id, scores={})
    db_session.commit()
    claim = EvidenceClaim(
        claim="Đối thủ có cancel rate cao",
        evidence_refs=[f"metric:{competitor_id}:cancel_rate"],
    )

    result = EvidenceValidationService(db_session).validate_claims(
        [claim],
        context=OWNER_CONTEXT,
        aggregate_snapshots={},
    )

    assert result.valid_claims == []
    assert result.rejected[0].reason == "competitor_private"


def test_valid_owner_profile_and_aggregate_claim_survives(db_session):
    from database.models import Merchant
    from relational_test_fixtures import seed_relational_profile

    db_session.add(
        Merchant(
            merchant_id=OWNER_CONTEXT.owner_merchant_id,
            name="Owner Aggregate",
            cuisine="Món Việt",
            city="Hà Nội",
            city_slug="ha_noi",
        )
    )
    seed_relational_profile(
        db_session,
        OWNER_CONTEXT.owner_merchant_id,
        scores={"food_quality": 0.6},
    )
    db_session.commit()
    claim = EvidenceClaim(
        claim="Food quality của owner thấp hơn cohort",
        evidence_refs=[
            f"profile:{OWNER_CONTEXT.owner_merchant_id}:food_quality",
            "aggregate:cohort:dimensions.food_quality.mean",
        ],
        numbers=[
            CitedNumber(
                value=0.6,
                evidence_ref=(
                    f"profile:{OWNER_CONTEXT.owner_merchant_id}:food_quality"
                ),
                field="food_quality",
            ),
            CitedNumber(
                value=0.8,
                evidence_ref="aggregate:cohort:dimensions.food_quality.mean",
                field="dimensions.food_quality.mean",
            ),
        ],
    )

    result = EvidenceValidationService(db_session).validate_claims(
        [claim],
        context=OWNER_CONTEXT,
        aggregate_snapshots={
            "cohort": {
                "aggregates": {
                    "dimensions": {"food_quality": {"mean": 0.8}}
                }
            }
        },
    )

    assert result.status == "ok"
    assert result.valid_claims == [claim]
