"""Bugs 4 and 5: an empty VLM answer, or one stuck in a repetition loop, must not be
reported as a successful conversion.

This is the behaviour test the fork's sync automation runs against each upstream
release *without* our code, to tell whether upstream fixed it. It must only use the
public pipeline API: importing our helper module would make it fail on upstream for
the wrong reason.

Measured on granite-docling over a 280-word page: 13564 characters, 2380 words, 7 of
them distinct — reported as SUCCESS with zero errors.
"""

from unittest.mock import MagicMock

import pytest

from docling.datamodel.base_models import (
    ConversionStatus,
    Page,
    PagePredictions,
    VlmPrediction,
    VlmStopReason,
)
from docling.datamodel.document import ConversionResult
from docling.pipeline.vlm_pipeline import VlmPipeline

HEALTHY = "# Title\n\n" + " ".join(f"word{i} with varied content" for i in range(60))
LOOP = "la industria de la industria de " * 200


def _page(page_no: int, text: str, stop_reason=VlmStopReason.END_OF_SEQUENCE) -> Page:
    page = Page(page_no=page_no)
    page.predictions = PagePredictions(
        vlm_response=VlmPrediction(text=text, stop_reason=stop_reason)
    )
    backend = MagicMock()
    backend.is_valid.return_value = True
    page._backend = backend
    return page


def _conv_res(pages: list[Page]) -> ConversionResult:
    conv_res = MagicMock(spec=ConversionResult)
    conv_res.pages = pages
    conv_res.errors = []
    conv_res.status = ConversionStatus.STARTED
    conv_res.input = MagicMock()
    conv_res.input._backend = None
    return conv_res


@pytest.fixture
def pipeline() -> VlmPipeline:
    return VlmPipeline.__new__(VlmPipeline)


def test_empty_answer_is_not_success(pipeline: VlmPipeline) -> None:
    conv_res = _conv_res([_page(1, HEALTHY), _page(2, "")])
    assert pipeline._determine_status(conv_res) != ConversionStatus.SUCCESS
    assert [e.page_no for e in conv_res.errors] == [2]


def test_repetition_loop_is_not_success(pipeline: VlmPipeline) -> None:
    conv_res = _conv_res([_page(1, LOOP)])
    assert pipeline._determine_status(conv_res) != ConversionStatus.SUCCESS
    assert len(conv_res.errors) == 1


def test_healthy_answer_stays_success(pipeline: VlmPipeline) -> None:
    conv_res = _conv_res([_page(1, HEALTHY)])
    assert pipeline._determine_status(conv_res) == ConversionStatus.SUCCESS
    assert conv_res.errors == []


def test_failed_inference_is_reported_once(pipeline: VlmPipeline) -> None:
    """Upstream (#4332) already flags a failed inference call; an empty answer from
    that same page must not add a second error."""
    conv_res = _conv_res([_page(1, HEALTHY), _page(2, "", VlmStopReason.INFERENCE_ERROR)])
    pipeline._determine_status(conv_res)
    assert [e.page_no for e in conv_res.errors] == [2]
