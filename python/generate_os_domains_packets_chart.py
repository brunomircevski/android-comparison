#!/usr/bin/env python3
"""Generate a compact OS/domain-count chart with packet volume bubbles."""

from __future__ import annotations

import csv
import html
import math
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "all_tasks_df.csv"
SVG_PATH = BASE_DIR / "os-domains-packets-acm.svg"

OS_ORDER = [
    ("stock", "Stock Android"),
    ("grapheneos", "GrapheneOS"),
    ("iode", "iodéOS"),
    ("lineage-gapps", "LineageOS (Gapps)"),
    ("lineage-microg", "LineageOS (microG)"),
]

GROUPS = [
    ("Google", "#0072B2", -4.7),
    ("Other", "#E69F00", 4.7),
]

WIDTH = 320
HEIGHT = 238
MARGIN_LEFT = 107
MARGIN_RIGHT = 36
MARGIN_TOP = 26
MARGIN_BOTTOM = 38
PLOT_WIDTH = WIDTH - MARGIN_LEFT - MARGIN_RIGHT
PLOT_HEIGHT = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM


def bool_value(value: str) -> bool:
    return value.strip().lower() == "true"


def load_data() -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], set[str]]]:
    packets: dict[tuple[str, str], int] = defaultdict(int)
    domains: dict[tuple[str, str], set[str]] = defaultdict(set)

    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["Scenario"] != "A":
                continue
            group = "Google" if bool_value(row["isGoogle"]) else "Other"
            key = (row["OS"], group)
            packets[key] += int(row["Sent_Packets"]) + int(row["Recv_Packets"])
            domains[key].add(row["Domain"])

    return dict(packets), dict(domains)


def text(
    x: float,
    y: float,
    value: str,
    *,
    size: float = 10,
    anchor: str = "start",
    weight: str = "normal",
    fill: str = "#222222",
) -> str:
    escaped = html.escape(value)
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" '
        f'font-family="Arial, Helvetica, sans-serif" text-anchor="{anchor}" '
        f'font-weight="{weight}" fill="{fill}">{escaped}</text>'
    )


def line(x1: float, y1: float, x2: float, y2: float, stroke: str = "#d8d8d8") -> str:
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{stroke}" stroke-width="0.6"/>'
    )


def rect(x: float, y: float, width: float, height: float, fill: str) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'fill="{fill}"/>'
    )


def circle(x: float, y: float, radius: float, fill: str) -> str:
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{fill}" '
        f'fill-opacity="0.82" stroke="#333333" stroke-width="0.5"/>'
    )


def packet_label(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.0f}k"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def radius_for_packets(value: int, min_log: float, max_log: float) -> float:
    if value <= 0:
        return 0
    position = (math.log10(value) - min_log) / (max_log - min_log)
    return 3.0 + position * 7.0


def build_svg() -> str:
    packets, domains = load_data()
    domain_counts = {key: len(value) for key, value in domains.items()}

    max_domains = max(domain_counts.values())
    axis_max = int(math.ceil(max_domains / 10.0) * 10)
    x_scale = PLOT_WIDTH / axis_max
    plot_left = MARGIN_LEFT
    plot_right = MARGIN_LEFT + PLOT_WIDTH
    plot_top = MARGIN_TOP
    plot_bottom = MARGIN_TOP + PLOT_HEIGHT

    positive_packets = [value for value in packets.values() if value > 0]
    min_log = math.log10(min(positive_packets))
    max_log = math.log10(max(positive_packets))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="3.33in" height="2.48in" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        text(8, 15, "Bubble size shows packets count", size=7.8, fill="#555555"),
    ]

    legend_x = 172
    legend_y = 15
    for idx, (group, color, _) in enumerate(GROUPS):
        x = legend_x + idx * 65
        parts.append(rect(x, legend_y - 7, 8, 8, color))
        parts.append(text(x + 11, legend_y, group, size=8.5))

    row_height = PLOT_HEIGHT / len(OS_ORDER)
    for tick in range(0, axis_max + 1, 10):
        x = plot_left + tick * x_scale
        parts.append(line(x, plot_top, x, plot_bottom))
        parts.append(text(x, plot_bottom + 12, str(tick), size=8, anchor="middle", fill="#555555"))

    parts.append(line(plot_left, plot_bottom, plot_right, plot_bottom, stroke="#555555"))
    parts.append(text((plot_left + plot_right) / 2, HEIGHT - 9, "Unique domains contacted", size=9, anchor="middle"))

    for row_idx, (os_key, os_label) in enumerate(OS_ORDER):
        row_top = plot_top + row_idx * row_height
        row_center = row_top + row_height / 2
        if row_idx > 0:
            parts.append(line(MARGIN_LEFT - 4, row_top, plot_right, row_top, stroke="#eeeeee"))

        parts.append(text(MARGIN_LEFT - 7, row_center + 3, os_label, size=8.6, anchor="end"))

        for group, color, y_offset in GROUPS:
            key = (os_key, group)
            count = domain_counts.get(key, 0)
            packet_count = packets.get(key, 0)
            if count == 0 or packet_count == 0:
                continue

            x = plot_left + count * x_scale
            y = row_center + y_offset
            radius = radius_for_packets(packet_count, min_log, max_log)
            parts.append(circle(x, y, radius, color))

            label = packet_label(packet_count)
            label_x = x + radius + 2.5
            label_anchor = "start"
            if label_x > WIDTH - 4:
                label_x = x - radius - 2.5
                label_anchor = "end"
            parts.append(text(label_x, y + 2.4, label, size=7.3, anchor=label_anchor, fill="#333333"))

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    SVG_PATH.write_text(build_svg(), encoding="utf-8")
    print(SVG_PATH)


if __name__ == "__main__":
    main()
