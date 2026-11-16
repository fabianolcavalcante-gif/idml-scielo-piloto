from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from idml_foundation.ai.contracts import ALLOWED_TOOLS
from idml_foundation.ai.outputs import AgentDomain
from idml_foundation.ai.pricing import load_pricing_catalog
from idml_foundation.ai.registry import load_registry
from idml_foundation.dependencies import Database, require_permission
from idml_foundation.models import AgentProposal, AgentRun
from idml_foundation.rbac import Permission, TenantContext
from idml_foundation.schemas import AgentCapabilitiesRead, AgentProposalRead, AgentRunRead
from idml_foundation.settings import get_settings

router = APIRouter(prefix="/v1/ai", tags=["assistive-ai"])


@router.get("/capabilities", response_model=AgentCapabilitiesRead)
def capabilities(
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> AgentCapabilitiesRead:
    del context
    settings = get_settings()
    pricing = load_pricing_catalog()
    model_keys = {profile.model_alias for profile in load_registry().values()}
    if len(model_keys) != 1:
        raise RuntimeError("agent domains must share one preflight model")
    model_key = model_keys.pop()
    provider, model = model_key.split("/", 1)
    preflight = pricing.resolve(
        provider=provider,
        model=model,
        input_tokens=settings.ai_max_input_tokens,
        output_tokens=settings.ai_max_output_tokens,
        cached_input_tokens=0,
        provider_cost_microusd=None,
    )
    return AgentCapabilitiesRead(
        enabled=settings.feature_openclaw,
        swarm_enabled=settings.feature_ai_swarm,
        domains=[domain.value for domain in AgentDomain],
        tools=sorted(ALLOWED_TOOLS),
        max_cost_microusd=settings.ai_max_cost_microusd,
        max_concurrency=settings.ai_max_concurrency,
        cost_policy=pricing.source_policy,
        pricing_version=pricing.version,
        priced_models=list(pricing.priced_models),
        default_model_key=model_key,
        preflight_max_cost_microusd=preflight.microusd,
    )


@router.get("/runs", response_model=list[AgentRunRead])
def list_runs(
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
    review_item_id: Annotated[str | None, Query()] = None,
) -> list[AgentRun]:
    statement = select(AgentRun).where(AgentRun.organization_id == context.organization_id)
    if review_item_id is not None:
        statement = statement.where(AgentRun.review_item_id == review_item_id)
    return list(db.scalars(statement.order_by(AgentRun.created_at.desc()).limit(200)))


@router.get("/proposals/{proposal_id}", response_model=AgentProposalRead)
def get_proposal(
    proposal_id: str,
    db: Database,
    context: Annotated[TenantContext, require_permission(Permission.RESOURCE_READ)],
) -> AgentProposal:
    proposal = db.scalar(
        select(AgentProposal).where(
            AgentProposal.id == proposal_id,
            AgentProposal.organization_id == context.organization_id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
    return proposal
