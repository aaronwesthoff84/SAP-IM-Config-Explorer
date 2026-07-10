from __future__ import annotations

import re
from xml.etree import ElementTree as ET


TEXT_LABEL_TAGS = {
    "EVENT_TYPE",
    "CREDIT_TYPE",
    "EARNING_CODE",
    "EARNINGCODE",
    "EARNING_GROUP",
    "EARNINGGROUP",
    "BUSINESS_UNIT",
    "BUSINESSUNIT",
    "PROCESSING_UNIT",
    "PROCESSINGUNIT",
    "CALENDAR",
}


def normalize_identity(value: str) -> str:
    segments = value.split(":")
    return ":".join(
        re.sub(r"[^a-z0-9]+", "-", segment.strip().lower()).strip("-")
        for segment in segments
    )


def infer_label(element: ET.Element) -> str:
    for attribute in ("NAME", "DISPLAY_NAME", "ID", "OBJECT_ID", "CODE", "SEQUENCE"):
        value = element.get(attribute)
        if value:
            return value.strip()
    if element.tag.upper() in TEXT_LABEL_TAGS:
        return (element.text or "").strip()
    return ""


def normalized_dates(element: ET.Element) -> dict[str, str]:
    dates: dict[str, str] = {}
    start = element.get("EFFECTIVE_START_DATE")
    end = element.get("EFFECTIVE_END_DATE")
    if start and start.strip():
        dates["effectiveStartDate"] = start.strip()
    if end and end.strip():
        dates["effectiveEndDate"] = end.strip()
    return dates


def trim_raw_xml(element: ET.Element, limit: int = 4000) -> str:
    raw = ET.tostring(element, encoding="unicode")
    if len(raw) <= limit:
        return raw
    marker = "\n..."
    if limit <= len(marker):
        return raw[: max(0, limit)]
    return raw[: limit - len(marker)] + marker
