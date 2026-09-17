# Multi Channel Systems MEA2100 intake

## Current sorting adaptation checkpoint (2026-09-17)

See [Axion-to-MCS workflow map](AXION_TO_MCS_WORKFLOW_MAP.md) for the code behind
the Turbo project README, the adopted Axion TH5 spike-sorting workflow, and the
remaining MCS changes. The subsequent user-approved
[single-recording AIND run](MCS_SINGLE_RECORDING_RUN_20260917.md) records the new
adapter, actual run status and saving paths. This document's earlier pilot
examples are not a complete production sorting recipe.

The staged archive has 114 recordings: **90 have 59 exported channels and 24
have 60**, all int32 at 10 kHz. Available source XML declares both
`60MEA200/30iR` and `60MEA100/10` configurations; the current exporter assigned
200 um coordinates universally. Resolve geometry per recording before sorting.
All preparation manifests also retain Mac paths that the runner must resolve
against their current input directory. The old direct `run_mcs_kilosort.py`
runner has not adopted the full TH5 settings or saved SpikeInterface
sorting/analyzer output contract. The new `scripts/prepare_mcs_aind_recording.py`
adapter instead prepares source-verified inputs for the established full AIND
workflow, with one recording per run and no invented well identity.

The [staged inventory](../audit-output/mcs_staged_inventory_20260917.csv) and
[source geometry audit](../audit-output/mcs_source_geometry_20260917.csv) record
the evidence. No sorting was launched during the initial mapping checkpoint;
the subsequent one-recording execution is documented separately above.

The Axion project builder cannot consume Multi Channel Systems (MCS) exports
directly: Axion starts with detected spike CSVs and an Axion `.raw` stimulus
file, while MCS stores continuous amplifier counts and event streams in HDF5.
This repository now has a separate, read-only MCS preparation path.

The repository also directly reads the legacy Multi Channel Suite v17 `.msrd`
format found in this archive. It follows its linked blocks of uncompressed
little-endian 32-bit samples and hardware-event records; no Windows conversion
tool is required.

## What was verified in the supplied data

`353.1/2021-06-22T15-23-26McsRecording.h5` is an MCS `60MEA200/30iR`
recording with 60 stored channels (59 electrodes and `Ref`), 10 kHz sampling,
and 618.4 s of continuous data. Its MCS event stream records five `STG 1
Single Pulse Start` events at 299.3519, 299.3621, 299.3723, 299.3825, and
299.3927 seconds from the first recorded sample.

The same recording's legacy `.msrd` file was independently decoded and matched
the HDF5 sample values, channel order, sampling rate, and ten hardware event
records. The legacy reader therefore provides a path when an HDF5 sidecar is
missing or corrupt.

The full archive audit found 118 legacy acquisitions. Of the 99 recordings in
the three primary experimental groups, 95 are ready for direct binary export.
Three are unreadable and one is a 1.9 KB incomplete file. The separate `MEA
2023` collection has 19 directly readable acquisitions.

## Inspect first

```bash
python run_mcs_h5_prepare.py \
  --input-h5 '/Volumes/MannySSD/final_chemogenetics_raw_data_2026/MANNY MEAs chemogenetics/Actuators & Effectors/Stim 1/353.1/2021-06-22T15-23-26McsRecording.h5'
```

For a legacy acquisition, substitute `--input-msrd` for `--input-h5`:

```bash
python run_mcs_h5_prepare.py \
  --input-msrd '/path/to/McsRecording.msrd'
```

## Geometry

The initial verified example uses the MCS `60MEA200/30iR` layout. It has an 8×8 grid at 200 µm
pitch; the four corners are absent and `Ref` is the non-signal reference site.
Numeric MCS labels encode the row and column, so channel `47` has `x=1400 µm`
and `y=800 µm`. Sorting excludes `Ref`; `channels.csv` and analysis HDF5 both
retain the 59 signal-site coordinates for that example. This is not a universal
archive geometry; see the current checkpoint above for the source XML evidence.

## Write an analysis HDF5 copy

```bash
python run_mcs_h5_prepare.py \
  --input-msrd '/path/to/McsRecording.msrd' \
  --output-dir /path/to/derived/recording \
  --export-h5
```

This writes `McsRecording.analysis.h5` with unchanged int32 trace counts,
MCS-style analog/event stream paths, channel metadata, and
`Geometry/ChannelGeometry`. It is an analysis export created by this repository,
not a claim that MCS DataManager generated the file.

To convert every source marked ready by the archive audit, preserving its group
and condition hierarchy and validating each written HDF5 file, run:

```bash
python scripts/convert_mcs_msrd_archive.py \
  --readiness-csv audit-output/mcs_sorting_readiness.csv \
  --output-root /Volumes/MannySSD/final_chemogenetics_raw_data_2026/mcs_msrd_analysis_h5
```

The batch creates a resumable `conversion_manifest.csv`. It uses uncompressed,
chunked HDF5 so all int32 counts are copied without scaling or compression
loss. Each file is written to a temporary `.partial` file and renamed only
after closing successfully.

This only prints metadata: channel order, sampling rate, duration, integer to
volt conversion, and event times relative to recording start.

## Explicit export for spike sorting

```bash
python run_mcs_h5_prepare.py \
  --input-msrd '/path/to/McsRecording.msrd' \
  --output-dir /path/to/derived/mcs_353_1 \
  --export-binary
```

The output is `mcs_signal_channels.int16.bin`, sample-major (time × channel)
and ready for a sorter; `Ref` is excluded. `channels.csv` provides the
standard 200 um grid inferred from MCS labels such as `47` (row 4, column 7),
and `events.csv` preserves the hardware event times. The JSON manifest retains
the MCS scale (`ConversionFactor × 10^Exponent` volts per integer count).

This is the historical single-file pilot interface. The archive's values do
not fit int16; use the existing staged int32 exports described below. Do not
re-export the archive with this pilot command.

This export is intentionally not fed to the Axion CSV response pipeline. The
next analysis stage should run spike sorting on the continuous binary, then
normalize sorter output and MCS `events.csv` into a platform-neutral spike/event
table for spontaneous and stimulus-locked analyses.

## Archive-wide spike-sorting handoff

The completed HDF5 conversion is the fixed input boundary for sorting. The
conversion manifest records which sources were losslessly copied and validated;
the next command reads only its successful rows and writes one identical sorter
input contract per recording:

```bash
python scripts/prepare_mcs_sorting_inputs.py \
  --conversion-manifest /Volumes/MannySSD/final_chemogenetics_raw_data_2026/mcs_msrd_analysis_h5/conversion_manifest.csv \
  --output-root /Volumes/MannySSD/final_chemogenetics_raw_data_2026/mcs_sorting_inputs
```

For every recording this creates, under the same experimental-group and
condition hierarchy:

- `mcs_signal_channels.int32.bin`: continuous sample-major trace matrix
  (`time × declared channel count`), with literal `Ref` labels excluded;
- `channels.csv`: channel order and currently assigned x/y coordinates, which
  require reconciliation with source acquisition geometry before sorting;
- `events.csv`: original hardware events in seconds from recording start; and
- `mcs_preparation_manifest.json`: sample count, 10 kHz sampling frequency,
  binary layout, channel count, event count, source HDF5 path, and volts/count
  metadata. The source counts exceed the signed-int16 range, so int32 is used
  to retain every raw value without clipping or rescaling; Kilosort accepts
  int32 input when the readiness manifest's dtype is used.

`sorting_input_manifest.csv` is the archive-level progress ledger. It is
append-only and resumable: completed sources are checked for the expected binary
size before being marked `already_validated`; failed exports are recorded rather
than silently skipped.

Prepare an individual binary for Kilosort4 without sorting it:

```bash
python run_mcs_kilosort.py \
  --input-dir /Volumes/MannySSD/final_chemogenetics_raw_data_2026/mcs_sorting_inputs/<group>/<condition>/<recording> \
  --output-dir /path/to/kilosort_runs/<recording>
```

This writes `mcs_kilosort_ready_manifest.json` with the declared channel probe,
10 kHz sampling frequency, binary dimensions, and Kilosort settings. Add
`--run` only on a CUDA-capable Linux machine with Kilosort4 installed; this Mac
is suitable for conversion and preparation but not GPU spike sorting. After
sorting, retain the Kilosort spike times/clusters alongside that readiness
manifest and join spike times to `events.csv` for stimulus-locked analyses.

## Great Lakes staging status

On 2026-09-15, the complete standardized sorter-input archive was transferred
from the Mac to Great Lakes. The transfer contains 114 validated recordings
(about 100 GiB): lossless int32 binaries, per-recording geometry and
event tables, preparation manifests, and the archive-level ledger.

Great Lakes input root:

```text
/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/mcs_sorting_inputs
```

The Mac's bundled rsync is an older version and does not support
`--info=progress2` or necessarily `--append-verify`. The compatible, resumable
command used for staging was:

```bash
rsync -aH -P \
  --exclude='*.int16.bin' \
  '/Volumes/MannySSD/final_chemogenetics_raw_data_2026/mcs_sorting_inputs/' \
  'elcrespo@greatlakes.arc-ts.umich.edu:/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/mcs_sorting_inputs/'
```

`-P` retains partial files and reports progress. The excluded int16 file is a
failed pilot artifact; all 114 validated sorter binaries are `.int32.bin`.

Before scheduling GPU sorting, verify the transfer on Great Lakes:

```bash
INPUT_ROOT=/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/mcs_sorting_inputs
find "$INPUT_ROOT" -name '*.int32.bin' | wc -l
python - <<'PY'
import csv
from pathlib import Path
p = Path('/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder/data/interim/mcs_sorting_inputs/sorting_input_manifest.csv')
latest = {}
for row in csv.DictReader(p.open()):
    latest[row['source_h5_path']] = row
assert len(latest) == 114
assert all(row['status'] in {'prepared', 'already_validated'} for row in latest.values())
print('114 manifest rows and validated statuses')
PY
```

The original next task was a Slurm-array wrapper around `run_mcs_kilosort.py`.
The 2026-09-17 audit establishes prerequisite work: portable paths, source-backed
geometry/reference mapping, explicit adopted TH5 settings, and the saved-spike/
analyzer contract. Use the sequence in [the workflow map](AXION_TO_MCS_WORKFLOW_MAP.md#6-implementation-sequence-and-acceptance-checks)
before scheduling. Each task still represents one complete single-MEA recording.
The formerly proposed `results/kilosort/mcs_60mea200` name should not imply that
all acquisitions used that array model.

## Direct-reader contract

The direct reader supports Multi Channel Suite `.msrd` files with
`FileVersion=17`, the format in this archive. It reads the embedded ASCII
recording index, follows per-channel `FPosNextID` links through raw little-endian
int32 blocks, and reads stimulation event links in the same file. It validates
that all channels have the same sample count before export. It does not modify
the `.msrd`, `.msrs`, XML, or HDF5 source files.

This is not a generic decoder for every historical MCS file version. The audit
marks any other or structurally incomplete input as blocked rather than guessing
at trace boundaries.

## Audit an archive before conversion

```bash
python scripts/audit_mcs_sorting_readiness.py \
  --data-root '/Volumes/MannySSD/final_chemogenetics_raw_data_2026/MANNY MEAs chemogenetics' \
  --output-csv audit-output/mcs_sorting_readiness.csv
```

The audit writes one row per legacy `.msrd` acquisition and performs direct
format validation. It distinguishes readable raw input from an unreadable or
implausibly small legacy data file. It never changes the source archive.
