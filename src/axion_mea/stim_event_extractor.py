from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .io import AxionStimFile


@dataclass(frozen=True)
class StimEventExtractionResult:
    """Summary of files and counts produced by raw stimulation parsing."""

    raw_file: Path
    csv_path: Path
    json_path: Path
    event_count: int
    led_event_count: int
    electrode_event_count: int
    unlinked_event_count: int
    stimulated_wells: list[str]


class StimEventExtractor:
    """Extract stimulation timing metadata from one Axion `.raw` file.

    This class is intentionally narrow: it delegates all binary decoding to
    `AxionStimFile`, then writes the normalized event exports used by the rest
    of the repository.
    """

    def __init__(self, raw_path: Path, output_dir: Path) -> None:
        """Store paths and prepare the destination directory."""
        self.raw_path = raw_path.expanduser().resolve()
        self.output_dir = output_dir.expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stim_file = AxionStimFile(self.raw_path)

    def extract(self) -> StimEventExtractionResult:
        """Parse the raw file and return the normalized extraction summary."""
        self.stim_file.parse()
        summaries = self.stim_file.summarize_stimulation_events()
        csv_path = self.output_dir / f"{self.raw_path.stem}_stim_events.csv"
        json_path = self.output_dir / f"{self.raw_path.stem}_stim_events.json"
        self.stim_file.write_event_csv(csv_path)
        self.stim_file.write_event_json(json_path)

        led_event_count = sum(event.source_kind == "led" for event in summaries)
        electrode_event_count = sum(event.source_kind == "electrode" for event in summaries)
        unlinked_event_count = sum(event.source_kind == "unlinked" for event in summaries)
        stimulated_wells = sorted({well for event in summaries for well in event.stimulated_wells})
        return StimEventExtractionResult(
            raw_file=self.raw_path,
            csv_path=csv_path,
            json_path=json_path,
            event_count=len(summaries),
            led_event_count=led_event_count,
            electrode_event_count=electrode_event_count,
            unlinked_event_count=unlinked_event_count,
            stimulated_wells=stimulated_wells,
        )

    @staticmethod
    def print_summary(result: StimEventExtractionResult) -> None:
        """Print the exact extraction outputs emitted for one recording."""
        print(f"Raw file: {result.raw_file}")
        print(f"CSV output: {result.csv_path}")
        print(f"JSON output: {result.json_path}")
        print(f"Stimulation events found: {result.event_count}")
        print(f"LED-linked events: {result.led_event_count}")
        print(f"Electrode-linked events: {result.electrode_event_count}")
        print(f"Unlinked events: {result.unlinked_event_count}")
        if result.stimulated_wells:
            print(f"Stimulated wells: {', '.join(result.stimulated_wells)}")
