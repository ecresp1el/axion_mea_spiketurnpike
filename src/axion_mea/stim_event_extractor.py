#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from .io import AxionStimFile


class StimExtractionApp:
    def __init__(self, raw_path: Path, output_dir: Path) -> None:
        self.raw_path = raw_path.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stim_file = AxionStimFile(self.raw_path)

    def run(self) -> None:
        self.stim_file.parse()
        summaries = self.stim_file.summarize_stimulation_events()

        stem = self.raw_path.stem
        csv_path = self.output_dir / f"{stem}_stim_events.csv"
        json_path = self.output_dir / f"{stem}_stim_events.json"

        self.stim_file.write_event_csv(csv_path)
        self.stim_file.write_event_json(json_path)

        print(f"Raw file: {self.raw_path}")
        print(f"CSV output: {csv_path}")
        print(f"JSON output: {json_path}")
        print(f"Stimulation events found: {len(summaries)}")

        if summaries:
            led_events = [event for event in summaries if event.source_kind == "led"]
            electrode_events = [event for event in summaries if event.source_kind == "electrode"]
            unlinked_events = [event for event in summaries if event.source_kind == "unlinked"]
            stimulated_wells = sorted({well for event in summaries for well in event.stimulated_wells})

            print(f"LED-linked events: {len(led_events)}")
            print(f"Electrode-linked events: {len(electrode_events)}")
            print(f"Unlinked events: {len(unlinked_events)}")
            if stimulated_wells:
                print(f"Stimulated wells: {', '.join(stimulated_wells)}")
            print("First event times (s):")
            for event in summaries[:10]:
                print(f"  {event.event_time_s:.6f}  {event.source_kind}  seq={event.sequence_number}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Axion stimulation event times from a .raw file."
    )
    parser.add_argument("--raw-file", type=Path, required=True, help="Path to the Axion .raw file")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/stim_times"),
        help="Directory for CSV and JSON outputs",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    app = StimExtractionApp(args.raw_file, args.output_dir)
    app.run()


if __name__ == "__main__":
    main()
