#!/usr/bin/env python3
"""Rebuild LNCS data-usage PDFs from existing figures, adding [MB] to the y-label."""

from __future__ import annotations

import re
import zlib
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR.parent / "images"

RECV_RGB = (0.4352941176, 0.6431372549, 0.8392156863)
SENT_RGB = (0.8941176471, 0.3411764706, 0.337254902)

OS_SCENARIOS = [
    ("stock", "A"),
    ("stock", "A2"),
    ("stock", "B"),
    ("lineage-gapps", "A"),
    ("lineage-gapps", "A2"),
    ("lineage-gapps", "B"),
    ("lineage-microg", "A"),
    ("lineage-microg", "B"),
    ("lineage-microg", "C"),
    ("lineage", "C"),
    ("iode", "A"),
    ("iode", "B"),
    ("iode", "C"),
    ("grapheneos", "A"),
    ("grapheneos", "B"),
    ("grapheneos", "C"),
]

CHARTS = [
    "setup-data-usage",
    "idle-data-usage",
    "apps-data-usage",
]


def pdf_content(path: Path) -> str:
    data = path.read_bytes()
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        raw = match.group(1)
        try:
            decoded = zlib.decompress(raw)
        except zlib.error:
            decoded = raw
        if b"0.4352941176" in decoded or b"/F1" in decoded:
            return decoded.decode("latin1")
    raise ValueError(f"No drawing stream found in {path}")


def decode_pdf_string(raw: str) -> str:
    raw = raw.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    data = raw.encode("latin1")
    if b"\x00" in data:
        if len(data) % 2:
            data += b"\x00"
        return data.decode("utf-16-be", errors="ignore")
    return raw


def y_scale(content: str) -> tuple[float, float]:
    ticks: list[tuple[float, float]] = []
    for match in re.finditer(
        r"1 0 -0 1 ([0-9.]+) ([0-9.]+) cm\nBT\n/F2 7 Tf\n0 0 Td\n\[ \((.*?)\) \] TJ",
        content,
    ):
        x, y, raw = float(match.group(1)), float(match.group(2)), match.group(3)
        text = decode_pdf_string(raw).strip()
        if x < 30 and re.fullmatch(r"[0-9]+", text):
            ticks.append((y, float(text)))
    if len(ticks) < 2:
        raise ValueError("Could not read y-axis ticks from PDF")
    ticks.sort()
    (y0, v0), (y1, v1) = ticks[0], ticks[-1]
    return (y1 - y0) / (v1 - v0), y0 - v0 * ((y1 - y0) / (v1 - v0))


def parse_bars(content: str) -> tuple[list[dict], list[dict]]:
    color_pat = re.compile(
        r"([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+rg"
    )
    path_pat = re.compile(
        r"([0-9.]+)\s+([0-9.]+)\s+m\n"
        r"([0-9.]+)\s+([0-9.]+)\s+l\n"
        r"([0-9.]+)\s+([0-9.]+)\s+l\n"
        r"([0-9.]+)\s+([0-9.]+)\s+l\nh"
    )
    colors = [(m.start(), tuple(float(g) for g in m.groups())) for m in color_pat.finditer(content)]
    recv: list[dict] = []
    sent: list[dict] = []
    for match in path_pat.finditer(content):
        xs = [float(match.group(i)) for i in (1, 3, 5, 7)]
        ys = [float(match.group(i)) for i in (2, 4, 6, 8)]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        width, height = x1 - x0, y1 - y0
        if width < 12 or width > 40 or y0 > 180:
            continue
        preceding = [c for c in colors if c[0] < match.start()]
        if not preceding:
            continue
        rgb = preceding[-1][1]
        bar = {"x0": x0, "y0": y0, "y1": y1, "height": height}
        if np.allclose(rgb, RECV_RGB, atol=0.02):
            recv.append(bar)
        elif np.allclose(rgb, SENT_RGB, atol=0.02):
            sent.append(bar)
    recv.sort(key=lambda b: b["x0"])
    sent.sort(key=lambda b: b["x0"])
    return recv, sent


def recover_df(pdf_path: Path) -> pd.DataFrame:
    content = pdf_content(pdf_path)
    pt_per_unit, _ = y_scale(content)
    recv, sent = parse_bars(content)
    if len(recv) != len(OS_SCENARIOS) or len(sent) != len(OS_SCENARIOS):
        raise ValueError(
            f"{pdf_path.name}: expected {len(OS_SCENARIOS)} bars, "
            f"got recv={len(recv)} sent={len(sent)}"
        )
    y_base = float(np.median([bar["y0"] for bar in recv]))
    rows = []
    for (os_name, scenario), recv_bar, sent_bar in zip(OS_SCENARIOS, recv, sent):
        recv_mb = max(0.0, (recv_bar["y1"] - y_base) / pt_per_unit)
        sent_mb = max(0.0, (sent_bar["y1"] - sent_bar["y0"]) / pt_per_unit)
        rows.append(
            {
                "OS": os_name,
                "Scenario": scenario,
                "Sent_Bytes": sent_mb * 1024 * 1024,
                "Recv_Bytes": recv_mb * 1024 * 1024,
            }
        )
    return pd.DataFrame(rows)


def plot_total_data_usage_lncs(df: pd.DataFrame, out_dir: Path, base_filename: str) -> None:
    os_display_order = [
        ("stock", "Stock Android"),
        ("lineage-gapps", "LineageOS (Gapps)"),
        ("lineage-microg", "LineageOS (microG)"),
        ("lineage", "LineageOS"),
        ("iode", "iodéOS"),
        ("grapheneos", "GrapheneOS"),
    ]
    display_map = dict(os_display_order)
    order_keys = [key for key, _ in os_display_order]
    scenario_order = ("A", "A2", "B", "C")
    allowed_scenarios = {
        "stock": {"A", "A2", "B"},
        "lineage-gapps": {"A", "A2", "B"},
        "lineage-microg": {"A", "B", "C"},
        "lineage": {"C"},
        "iode": {"A", "B", "C"},
        "grapheneos": {"A", "B", "C"},
    }

    agg_df = (
        df.groupby(["OS", "Scenario"], as_index=False)[["Sent_Bytes", "Recv_Bytes"]]
        .sum(numeric_only=True)
    )
    grid_rows = [
        {"OS": os_key, "Scenario": scenario}
        for os_key in order_keys
        for scenario in scenario_order
        if scenario in allowed_scenarios[os_key]
    ]
    plot_df = pd.DataFrame(grid_rows).merge(agg_df, on=["OS", "Scenario"], how="left").fillna(
        {"Sent_Bytes": 0, "Recv_Bytes": 0}
    )
    plot_df["Sent_MB"] = plot_df["Sent_Bytes"] / (1024 * 1024)
    plot_df["Recv_MB"] = plot_df["Recv_Bytes"] / (1024 * 1024)

    x, recv, sent, scen_labels = [], [], [], []
    os_centers, separators = [], []
    idx = 0.0
    gap = 0.7
    for os_name in order_keys:
        os_rows = plot_df[plot_df["OS"] == os_name].sort_values("Scenario")
        start = idx
        for _, row in os_rows.iterrows():
            x.append(idx)
            recv.append(float(row["Recv_MB"]))
            sent.append(float(row["Sent_MB"]))
            label = "A1" if row["Scenario"] == "A" else str(row["Scenario"])
            scen_labels.append(label)
            idx += 1.0
        end = idx - 1.0
        os_centers.append(((start + end) / 2.0, display_map[os_name]))
        separators.append(idx - 0.5)
        idx += gap

    x = np.array(x, dtype=float)
    recv = np.array(recv, dtype=float)
    sent = np.array(sent, dtype=float)
    totals = recv + sent

    mpl.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 600,
            "pdf.fonttype": 42,
            "font.family": "serif",
            "font.serif": ["DejaVu Serif", "Times New Roman", "Times", "Nimbus Roman"],
            "font.size": 8.0,
            "axes.titlesize": 9.2,
            "axes.labelsize": 8.0,
            "legend.fontsize": 8.0,
            "xtick.labelsize": 7.0,
            "ytick.labelsize": 7.0,
            "axes.linewidth": 0.6,
            "xtick.major.width": 0.6,
            "ytick.major.width": 0.6,
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    c_recv = "#6FA4D6"
    c_sent = "#E45756"
    figsize = (7.1, 2.9)

    def render(ax, log: bool = False) -> None:
        width = 0.72
        ax.bar(x, recv, width=width, color=c_recv, edgecolor="white", linewidth=0.35, label="Download", zorder=3)
        ax.bar(
            x,
            sent,
            width=width,
            bottom=recv,
            color=c_sent,
            edgecolor="white",
            linewidth=0.35,
            label="Upload",
            zorder=3,
        )
        ax.set_ylabel("Total usage [MB]")
        ax.set_xticks(x)
        ax.set_xticklabels(scen_labels)
        ax.set_xlim(x.min() - 0.6, x.max() + 0.6)
        max_total = float(max(totals.max(), 0.0))
        if log:
            ax.set_yscale("log")
            ymin = 1e-3
            ax.set_ylim(ymin, max(max_total * 3.6, ymin * 10.0))
            ax.grid(axis="y", which="minor", linestyle=":", linewidth=0.4, alpha=0.18)
        else:
            ax.set_ylim(0.0, max(max_total * 1.32, 1e-6))
        ax.grid(axis="y", linestyle="--", linewidth=0.5, alpha=0.30, zorder=0)

        sec = ax.secondary_xaxis("bottom")
        sec.set_xticks([center for center, _ in os_centers])
        sec.set_xticklabels([name for _, name in os_centers], fontweight="bold")
        sec.spines["bottom"].set_visible(False)
        sec.tick_params(axis="x", pad=16, length=0)
        for separator in separators[:-1]:
            ax.axvline(x=separator, color="0.88", linewidth=0.8, zorder=1)
        ax.legend(
            loc="upper left",
            bbox_to_anchor=(0.0, 1.03),
            frameon=False,
            ncol=2,
            handlelength=1.2,
            columnspacing=1.0,
            borderaxespad=0.0,
        )

        y_top = ax.get_ylim()[1]
        lin_offset = y_top * 0.018
        for xi, total in zip(x, totals):
            total_bytes = float(total * 1024 * 1024)
            if total_bytes <= 0:
                continue
            if total_bytes < 1024:
                txt = f"{total_bytes:.0f} B"
            elif total_bytes < 1024 * 1024:
                txt = f"{total_bytes / 1024:.0f} KB"
            else:
                txt = f"{total_bytes / (1024 * 1024):.0f} MB"
            if log:
                y = min(max(total, 1e-6) * 1.14, y_top * 0.88)
            else:
                y = min(total + lin_offset, y_top * 0.88)
            ax.text(
                xi,
                y,
                txt,
                ha="center",
                va="bottom",
                fontsize=5.5,
                fontweight="bold",
                color="0.25",
                clip_on=True,
                zorder=5,
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)
    render(ax, log=False)
    fig.savefig(out_dir / f"{base_filename}.pdf", format="pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=figsize, constrained_layout=True)
    render(ax, log=True)
    fig.savefig(out_dir / f"{base_filename}-log.pdf", format="pdf")
    plt.close(fig)
    print(f"Wrote {out_dir / (base_filename + '.pdf')} and -log.pdf")


def main() -> None:
    mpl.use("Agg")
    for name in CHARTS:
        src = IMAGES_DIR / f"{name}.pdf"
        df = recover_df(src)
        print(f"{name}: recovered {len(df)} bars, max {df[['Sent_Bytes','Recv_Bytes']].sum(axis=1).max() / 1024 / 1024:.2f} MB")
        plot_total_data_usage_lncs(df, IMAGES_DIR, name)


if __name__ == "__main__":
    main()
