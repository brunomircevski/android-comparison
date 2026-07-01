#!/usr/bin/env python3
"""Generate an ACM-column-sized data usage chart from all_tasks_df.csv."""

from __future__ import annotations

import csv
import html
import math
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "all_tasks_df.csv"
SVG_PATH = BASE_DIR / "all-tasks-data-usage-acm.svg"

OS_ORDER = [
    ("stock", "Stock Android"),
    ("grapheneos", "GrapheneOS"),
    ("iode", "iodéOS"),
    ("lineage-gapps", "LineageOS (Gapps)"),
    ("lineage-microg", "LineageOS (microG)"),
    ("lineage", "LineageOS"),
]

SCENARIO_ORDER = ["A", "A2", "B", "C"]
SCENARIO_LABELS = {
    "A": "A1",
    "A2": "A2",
    "B": "B",
    "C": "C",
}
SCENARIO_COLORS = {
    "A": "#0072B2",
    "A2": "#56B4E9",
    "B": "#E69F00",
    "C": "#009E73",
}

WIDTH = 320
HEIGHT = 274
MARGIN_LEFT = 96
MARGIN_RIGHT = 35
MARGIN_TOP = 34
MARGIN_BOTTOM = 44
PLOT_WIDTH = WIDTH - MARGIN_LEFT - MARGIN_RIGHT
PLOT_HEIGHT = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM


def bool_value(value: str) -> bool:
    return value.strip().lower() == "true"


def load_totals() -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], float] = defaultdict(float)
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if bool_value(row["isUpdatePayload"]):
                continue
            total_bytes = int(row["Sent_Bytes"]) + int(row["Recv_Bytes"])
            totals[(row["OS"], row["Scenario"])] += total_bytes / 1024 / 1024
    return dict(totals)


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


def rect(x: float, y: float, width: float, height: float, fill: str, *, opacity: float = 1.0) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
        f'fill="{fill}" fill-opacity="{opacity:.2f}"/>'
    )


def format_mb(value: float) -> str:
    if value >= 10:
        return f"{value:.0f}"
    if value >= 1:
        return f"{value:.1f}"
    return f"{value:.2f}"


def nice_axis_max(max_value: float) -> int:
    return int(math.ceil(max_value / 25.0) * 25)


def build_svg() -> str:
    totals = load_totals()
    max_value = max(totals.values())
    axis_max = nice_axis_max(max_value)
    scale = PLOT_WIDTH / axis_max
    plot_left = MARGIN_LEFT
    plot_right = MARGIN_LEFT + PLOT_WIDTH
    plot_top = MARGIN_TOP
    plot_bottom = MARGIN_TOP + PLOT_HEIGHT

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="3.33in" height="2.85in" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
    ]

    legend_x = MARGIN_LEFT
    legend_y = 17
    parts.append(text(legend_x, legend_y, "Scenarios:", size=8.5, weight="bold"))
    scenario_legend_x = legend_x + 54
    for idx, scenario in enumerate(SCENARIO_ORDER):
        x = scenario_legend_x + idx * 32
        parts.append(rect(x, legend_y - 7, 8, 8, SCENARIO_COLORS[scenario]))
        parts.append(text(x + 11, legend_y, SCENARIO_LABELS[scenario], size=8.5))

    for tick in range(0, axis_max + 1, 25):
        x = plot_left + tick * scale
        parts.append(line(x, plot_top, x, plot_bottom))
        parts.append(text(x, plot_bottom + 12, str(tick), size=8, anchor="middle", fill="#555555"))

    parts.append(line(plot_left, plot_bottom, plot_right, plot_bottom, stroke="#555555"))
    parts.append(text((plot_left + plot_right) / 2, HEIGHT - 10, "Total data usage (MB)", size=9, anchor="middle"))

    group_height = PLOT_HEIGHT / len(OS_ORDER)
    bar_height = 5.6
    bar_gap = 1.8

    for group_idx, (os_key, os_label) in enumerate(OS_ORDER):
        group_top = plot_top + group_idx * group_height
        group_center = group_top + group_height / 2
        parts.append(text(MARGIN_LEFT - 7, group_center + 3, os_label, size=8.6, anchor="end"))

        scenarios = [scenario for scenario in SCENARIO_ORDER if (os_key, scenario) in totals]
        total_bar_height = len(scenarios) * bar_height + max(0, len(scenarios) - 1) * bar_gap
        start_y = group_center - total_bar_height / 2

        if group_idx > 0:
            parts.append(line(MARGIN_LEFT - 4, group_top, plot_right, group_top, stroke="#eeeeee"))

        for scenario_idx, scenario in enumerate(scenarios):
            value = totals[(os_key, scenario)]
            bar_y = start_y + scenario_idx * (bar_height + bar_gap)
            bar_width = max(1.0, value * scale)
            color = SCENARIO_COLORS[scenario]
            parts.append(rect(plot_left, bar_y, bar_width, bar_height, color))

            label = format_mb(value)
            label_x = plot_left + bar_width + 2.2
            label_anchor = "start"
            label_color = "#222222"
            if label_x > WIDTH - 6:
                label_x = plot_left + bar_width - 2.2
                label_anchor = "end"
                label_color = "white"
            parts.append(text(label_x, bar_y + bar_height - 0.4, label, size=7.2, anchor=label_anchor, fill=label_color))

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    SVG_PATH.write_text(build_svg(), encoding="utf-8")
    print(SVG_PATH)


if __name__ == "__main__":
    main()
