from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .dod import fetch_dod_darpa_opportunities
from .models import Opportunity
from .nih import fetch_nih_guide_opportunities
from .nsf import fetch_nsf_seedfund_opportunities
from .rss import fetch_rss_opportunities
from .sam import fetch_sam_opportunities
from .sbir import fetch_solicitations, iter_opportunities


@dataclass(slots=True)
class SourceReport:
    name: str
    count: int


def collect_opportunities(
    config: AppConfig,
) -> tuple[list[Opportunity], list[SourceReport], list[str]]:
    opportunities: list[Opportunity] = []
    reports: list[SourceReport] = []
    errors: list[str] = []

    sbir_failed = False
    try:
        solicitations = fetch_solicitations(config)
        sbir_opps = [opp for record in solicitations for opp in iter_opportunities(record)]
        opportunities.extend(sbir_opps)
        reports.append(SourceReport(name="sbir", count=len(sbir_opps)))
    except Exception as exc:  # pragma: no cover - network errors
        sbir_failed = True
        errors.append(f"SBIR.gov: {exc}")

    dod_failed = False
    if config.dod.enabled and (sbir_failed or not config.dod.fallback_only):
        try:
            dod_opps = fetch_dod_darpa_opportunities(config)
            opportunities.extend(dod_opps)
            reports.append(SourceReport(name="dod_darpa", count=len(dod_opps)))
        except Exception as exc:  # pragma: no cover - network errors
            dod_failed = True
            errors.append(f"DARPA topics: {exc}")

    nsf_failed = False
    if config.nsf.enabled and (sbir_failed or not config.nsf.fallback_only):
        try:
            nsf_opps = fetch_nsf_seedfund_opportunities(config)
            opportunities.extend(nsf_opps)
            reports.append(SourceReport(name="nsf_seedfund", count=len(nsf_opps)))
        except Exception as exc:  # pragma: no cover - network errors
            nsf_failed = True
            errors.append(f"NSF solicitations: {exc}")

    nih_failed = False
    if config.nih.enabled and (sbir_failed or not config.nih.fallback_only):
        try:
            nih_opps = fetch_nih_guide_opportunities(config)
            opportunities.extend(nih_opps)
            reports.append(SourceReport(name="nih_guide", count=len(nih_opps)))
        except Exception as exc:  # pragma: no cover - network errors
            nih_failed = True
            errors.append(f"NIH Guide: {exc}")

    rss_failed = False
    if config.rss.enabled and (sbir_failed or not config.rss.fallback_only):
        try:
            rss_opps = fetch_rss_opportunities(config)
            opportunities.extend(rss_opps)
            reports.append(SourceReport(name="grants_rss", count=len(rss_opps)))
        except Exception as exc:  # pragma: no cover - network errors
            rss_failed = True
            errors.append(f"Grants.gov RSS: {exc}")

    if config.sam.enabled and (
        sbir_failed
        or rss_failed
        or dod_failed
        or nsf_failed
        or nih_failed
        or not config.sam.fallback_only
    ):
        try:
            sam_opps = fetch_sam_opportunities(config)
            opportunities.extend(sam_opps)
            reports.append(SourceReport(name="sam", count=len(sam_opps)))
        except Exception as exc:  # pragma: no cover - network errors
            errors.append(f"SAM.gov: {exc}")

    if not opportunities and errors and config.fail_on_no_results:
        raise RuntimeError("All sources failed: " + "; ".join(errors))

    return opportunities, reports, errors
