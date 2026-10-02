from __future__ import annotations

from eastco_benchmark.adapters.hosted import build_cloud_hosted_adapter
from eastco_benchmark.adapters.llm import build_llm_adapter
from eastco_benchmark.adapters.ocr import build_ocr_adapter
from eastco_benchmark.adapters.vlm import build_vlm_adapter
from eastco_benchmark.config import Settings
from eastco_benchmark.pipelines.direct_vlm import DirectVLMPipeline
from eastco_benchmark.pipelines.hosted_cloud import CloudHostedOpenSourcePipeline
from eastco_benchmark.pipelines.hybrid import ConfidenceHybridPipeline
from eastco_benchmark.pipelines.ocr_llm import OCRThenLLMPipeline


def build_pipelines(settings: Settings):
    vlm = build_vlm_adapter(settings)
    ocr = build_ocr_adapter(settings)
    llm = build_llm_adapter(settings)
    hosted = build_cloud_hosted_adapter(settings)

    direct = DirectVLMPipeline(vlm)
    ocr_llm = OCRThenLLMPipeline(ocr, llm)
    cloud_hosted = CloudHostedOpenSourcePipeline(hosted)
    hybrid = ConfidenceHybridPipeline(ocr_llm, direct, settings.hybrid_confidence_threshold)

    return {
        direct.name: direct,
        ocr_llm.name: ocr_llm,
        cloud_hosted.name: cloud_hosted,
        hybrid.name: hybrid,
    }
