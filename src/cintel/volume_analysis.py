"""Compare service reliability by request volume.

Author: Darrion Maurice Stringer
Date: 2026-11
"""

from pathlib import Path

import polars as pl

from cintel.utils_system import design_signals, load_system_metrics


def main() -> None:
    """Save grouped signals, a comparison table, and a chart."""
    root = Path.cwd()
    artifacts = root / "artifacts"
    images = root / "docs" / "images"
    artifacts.mkdir(parents=True, exist_ok=True)
    images.mkdir(parents=True, exist_ok=True)

    raw = load_system_metrics(root / "data" / "system_metrics.csv")
    required = ["requests", "errors", "total_latency_ms"]
    if not all(column in raw.columns for column in required):
        raise ValueError("Required data columns are missing.")
    if any(raw[column].null_count() for column in required):
        raise ValueError("Required columns contain missing values.")
    if raw.filter(
        (pl.col("requests") < 0)
        | (pl.col("errors") < 0)
        | (pl.col("errors") > pl.col("requests"))
        | (pl.col("total_latency_ms") < 0)
    ).height:
        raise ValueError("Invalid request, error, or latency values.")

    signals = design_signals(raw).with_columns(
        pl.when(pl.col("requests") < 120)
        .then(pl.lit("Lower volume"))
        .otherwise(pl.lit("Higher volume"))
        .alias("volume_group")
    )
    signals.write_csv(artifacts / "volume_signals.csv")

    summary = (
        signals.group_by("volume_group")
        .agg(
            pl.len().alias("observations"),
            pl.col("requests").sum().alias("total_requests"),
            pl.col("errors").sum().alias("total_errors"),
            pl.col("total_latency_ms").sum().alias("total_latency_ms"),
        )
        .with_columns(
            pl.when(pl.col("total_requests") > 0)
            .then(100 * pl.col("total_errors") / pl.col("total_requests"))
            .otherwise(None)
            .alias("error_rate_pct"),
            pl.when(pl.col("total_requests") > 0)
            .then(
                100
                * (pl.col("total_requests") - pl.col("total_errors"))
                / pl.col("total_requests")
            )
            .otherwise(None)
            .alias("success_rate_pct"),
            pl.when(pl.col("total_requests") > 0)
            .then(pl.col("total_latency_ms") / pl.col("total_requests"))
            .otherwise(None)
            .alias("avg_latency_ms"),
        )
        .sort("total_requests")
    )

    summary.write_csv(artifacts / "volume_comparison.csv")

    svg = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" '
            'viewBox="0 0 800 300">'
        ),
        '<rect width="800" height="300" fill="white"/>',
        '<g font-family="Arial" fill="#172033">',
        '<text x="25" y="35" font-size="24">Error Rate by Request Volume</text>',
        (
            '<text x="25" y="65" font-size="15">'
            "Lower: fewer than 120 requests; Higher: 120 or more</text>"
        ),
    ]
    for index, row in enumerate(summary.iter_rows(named=True)):
        y = 100 + index * 80
        rate = row["error_rate_pct"]
        if rate is None:
            raise ValueError("A group has no requests; chart rate is undefined.")
        width = rate * 150
        svg.extend(
            [
                (
                    f'<text x="25" y="{y + 25}" font-size="18">'
                    f"{row['volume_group']}</text>"
                ),
                (
                    f'<rect x="180" y="{y}" width="{width:.2f}" height="40" '
                    'fill="#2563eb"/>'
                ),
                (
                    f'<text x="{195 + width:.2f}" y="{y + 26}" font-size="18">'
                    f"{rate:.2f}%</text>"
                ),
            ]
        )
    svg.append(
        '<text x="25" y="270" font-size="14">'
        "Group error rate = total errors / total requests × 100.</text>"
        "</g></svg>"
    )
    (images / "volume-error-rates.svg").write_text("\n".join(svg), encoding="utf-8")

    print(summary)
    print("Saved volume_signals.csv and volume_comparison.csv in artifacts/.")
    print("Saved chart to docs/images/volume-error-rates.svg.")


if __name__ == "__main__":
    main()
