"""Capture a deterministic converter snapshot for temporary development comparison."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sap_im_config_graph_explorer.xml_to_html_converter import Transformer


DEFAULT_SOURCE = ROOT / "tests" / "fixtures" / "html_sorting_comparison.xml"
OUTPUT_DIR = ROOT / "sap_im_config_graph_explorer" / "development_html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", choices=("baseline", "candidate"))
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help="XML fixture used to produce the comparison HTML.",
    )
    args = parser.parse_args()

    transformer = Transformer()
    transformer.parse(str(args.source))
    output = OUTPUT_DIR / f"{args.snapshot}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(transformer.html(), encoding="utf-8")
    print(f"Captured {args.snapshot} HTML: {output}")


if __name__ == "__main__":
    main()
