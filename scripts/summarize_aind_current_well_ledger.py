#!/usr/bin/env python3
"""Build a single well-level status ledger for the current Axion AIND run."""

from __future__ import annotations

import argparse
import csv
import json
import getpass
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path("/nfs/turbo/umms-parent/axion_mea_spiketurnpike_projectfolder")
RESULTS_ROOT = PROJECT_ROOT / "results" / "aind"
SCRATCH_ROOT = PROJECT_ROOT / "scratch" / "aind_nextflow"

TASK_ORDER = [
    "job_dispatch",
    "preprocessing",
    "nwb_ecephys",
    "spikesort_kilosort4",
    "postprocessing",
    "curation",
    "visualization",
    "results_collector",
    "quality_control",
    "quality_control_collector",
    "nwb_units",
]

TASK_INDEX = {task: i for i, task in enumerate(TASK_ORDER)}


def parse_key_value_line(line: str) -> dict[str, str]:
    row: dict[str, str] = {}
    for item in line.strip().split():
        if "=" in item:
            key, value = item.split("=", 1)
            row[key] = value
    return row


def read_submitted_batches(path: Path, lane: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            parsed = parse_key_value_line(line)
            parsed["lane"] = lane
            parsed["source_manifest"] = str(path)
            rows.append(parsed)
    return rows


def read_smoke_row(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "recording": row["recording_stem"],
                    "well": row["well"],
                    "export_job": "",
                    "nwb_job": "",
                    "spikeinterface_job": "",
                    "aind_job": "",
                    "lane": "sixwell_smoke",
                    "source_manifest": str(path),
                }
            )
    return rows


def read_quote_fix_map(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["recording_stem"], row["well"]): row
            for row in csv.DictReader(handle)
        }


def run_text(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def sacct_states(job_ids: list[str]) -> dict[str, dict[str, str]]:
    clean_ids = sorted({jid for jid in job_ids if jid})
    if not clean_ids:
        return {}
    states: dict[str, dict[str, str]] = {}
    chunk_size = 300
    for start in range(0, len(clean_ids), chunk_size):
        chunk = clean_ids[start : start + chunk_size]
        output = run_text(
            [
                "sacct",
                "-X",
                "-n",
                "-P",
                "-j",
                ",".join(chunk),
                "-o",
                "JobIDRaw,State,ExitCode,JobName",
            ]
        )
        for line in output.splitlines():
            parts = line.split("|")
            if len(parts) < 4:
                continue
            job_id, state, exit_code, job_name = parts[:4]
            states[job_id] = {
                "state": state,
                "exit_code": exit_code,
                "job_name": job_name,
            }
    return states


def squeue_jobs() -> dict[str, dict[str, str]]:
    output = run_text(["squeue", "-u", getpass.getuser(), "-h", "-o", "%i|%T|%j|%R"])
    jobs: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        job_id, state, name, reason = parts
        jobs[job_id] = {"state": state, "job_name": name, "reason": reason}
    return jobs


def merged_job_state(job_id: str, sacct: dict[str, dict[str, str]], squeue: dict[str, dict[str, str]]) -> str:
    if not job_id:
        return ""
    if job_id in squeue:
        return squeue[job_id]["state"]
    if job_id in sacct:
        exit_code = sacct[job_id].get("exit_code", "")
        return f"{sacct[job_id].get('state', '')}:{exit_code}" if exit_code else sacct[job_id].get("state", "")
    return "UNKNOWN"


def base_task_name(name: str) -> str:
    return name.split()[0].strip()


def parse_trace(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        tasks: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in reader:
            task = base_task_name(row.get("name", ""))
            if task:
                tasks[task].append(row)
    state_by_task: dict[str, dict[str, str]] = {}
    for task, rows in tasks.items():
        completed = [row for row in rows if row.get("status") == "COMPLETED" and row.get("exit") == "0"]
        failed = [row for row in rows if row.get("status") == "FAILED"]
        running = [row for row in rows if row.get("status") == "RUNNING"]
        pending = [row for row in rows if row.get("status") in {"PENDING", "SUBMITTED"}]
        latest = rows[-1]
        if completed:
            chosen = completed[-1]
            status = "COMPLETED"
        elif failed:
            chosen = failed[-1]
            status = "FAILED"
        elif running:
            chosen = running[-1]
            status = "RUNNING"
        elif pending:
            chosen = pending[-1]
            status = chosen.get("status", "PENDING")
        else:
            chosen = latest
            status = chosen.get("status", "")
        state_by_task[task] = {
            "status": status,
            "hash": chosen.get("hash", ""),
            "native_id": chosen.get("native_id", ""),
            "exit": chosen.get("exit", ""),
            "duration": chosen.get("duration", ""),
            "submit": chosen.get("submit", ""),
        }
    return state_by_task


def task_failure_summary(recording: str, well: str, task: str, trace: dict[str, dict[str, str]]) -> str:
    task_hash = trace.get(task, {}).get("hash", "")
    if not task_hash:
        return ""
    command_err = SCRATCH_ROOT / recording / well / task_hash / ".command.err"
    if not command_err.exists():
        prefix_parts = task_hash.split("/", 1)
        if len(prefix_parts) == 2:
            candidates = sorted(
                (SCRATCH_ROOT / recording / well / prefix_parts[0]).glob(
                    f"{prefix_parts[1]}*/.command.err"
                )
            )
            if candidates:
                command_err = candidates[-1]
        if not command_err.exists():
            return ""
    interesting = []
    with command_err.open(errors="replace", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            if (
                text.startswith("ValueError:")
                or text.startswith("SpikeSortingError:")
                or text.startswith("Exception:")
                or text.startswith("RuntimeError:")
            ):
                interesting.append(text)
    if not interesting:
        return ""
    for text in reversed(interesting):
        if text.startswith("ValueError:"):
            return text
    return interesting[-1]


def read_unit_metrics(results_dir: Path) -> dict[str, str | int]:
    curated_dir = results_dir / "curated" / "block0_None_recording1"
    info_path = curated_dir / "numpysorting_info.json"
    labels_path = curated_dir / "properties" / "KSLabel.npy"
    spikes_path = curated_dir / "spikes.npy"
    if not info_path.exists():
        return {
            "unit_metrics_status": "missing_curated_sorting",
            "unit_label_source": "",
            "unit_label_warning": "",
            "unit_count_total": "",
            "kslabel_good_count": "",
            "kslabel_mua_count": "",
            "kslabel_noise_count": "",
            "unit_count_sua": "",
            "unit_count_mua": "",
            "unit_count_noise": "",
            "unit_label_counts": "",
            "spike_count_min_per_unit": "",
            "spike_count_max_per_unit": "",
            "spike_count_range_per_unit": "",
            "spike_count_median_per_unit": "",
            "spike_count_total": "",
            "units_with_spikes": "",
            "units_with_zero_spikes": "",
        }
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        unit_ids = info.get("unit_ids", [])
        unit_count = len(unit_ids)
        if labels_path.exists():
            labels = [str(value).lower() for value in np.load(labels_path, allow_pickle=True).tolist()]
        else:
            labels = []
        label_counts = Counter(labels)
        observed_labels = sorted(label_counts)
        label_source = (
            "curated/block0_None_recording1/properties/KSLabel.npy; "
            "Kilosort/Phy label propagated through AIND postprocessing/curation"
        )
        if "noise" in label_counts:
            label_warning = ""
        else:
            label_warning = (
                "No KSLabel=noise values observed. unit_count_noise=0 means the "
                "KSLabel source did not label any units as noise; it is not an "
                "independent AIND unit-classifier noise call."
            )

        if spikes_path.exists():
            spikes = np.load(spikes_path, allow_pickle=True, mmap_mode="r")
            if unit_count:
                unit_indices = np.asarray(spikes["unit_index"], dtype=np.int64)
                spike_counts = np.bincount(unit_indices, minlength=unit_count)[:unit_count]
            else:
                spike_counts = np.array([], dtype=np.int64)
        else:
            spike_counts = np.array([], dtype=np.int64)

        if unit_count and spike_counts.size:
            spike_min = int(spike_counts.min())
            spike_max = int(spike_counts.max())
            spike_median = float(np.median(spike_counts))
            spike_total = int(spike_counts.sum())
            units_with_spikes = int(np.count_nonzero(spike_counts > 0))
            units_with_zero = int(np.count_nonzero(spike_counts == 0))
        elif unit_count:
            spike_min = spike_max = spike_median = spike_total = units_with_spikes = units_with_zero = ""
        else:
            spike_min = spike_max = spike_median = spike_total = units_with_spikes = units_with_zero = 0

        return {
            "unit_metrics_status": "ok",
            "unit_label_source": label_source,
            "unit_label_warning": label_warning,
            "unit_count_total": unit_count,
            "kslabel_good_count": label_counts.get("good", 0),
            "kslabel_mua_count": label_counts.get("mua", 0),
            "kslabel_noise_count": label_counts.get("noise", 0),
            "unit_count_sua": label_counts.get("good", 0),
            "unit_count_mua": label_counts.get("mua", 0),
            "unit_count_noise": label_counts.get("noise", 0),
            "unit_label_counts": json.dumps(dict(sorted(label_counts.items())), sort_keys=True),
            "unit_labels_observed": ",".join(observed_labels),
            "spike_count_min_per_unit": spike_min,
            "spike_count_max_per_unit": spike_max,
            "spike_count_range_per_unit": f"{spike_min}-{spike_max}" if spike_min != "" and spike_max != "" else "",
            "spike_count_median_per_unit": spike_median,
            "spike_count_total": spike_total,
            "units_with_spikes": units_with_spikes,
            "units_with_zero_spikes": units_with_zero,
        }
    except Exception as exc:  # noqa: BLE001 - this is a status ledger, not a hard stop.
        return {
            "unit_metrics_status": f"failed:{type(exc).__name__}:{exc}",
            "unit_label_source": "",
            "unit_label_warning": "",
            "unit_count_total": "",
            "kslabel_good_count": "",
            "kslabel_mua_count": "",
            "kslabel_noise_count": "",
            "unit_count_sua": "",
            "unit_count_mua": "",
            "unit_count_noise": "",
            "unit_label_counts": "",
            "unit_labels_observed": "",
            "spike_count_min_per_unit": "",
            "spike_count_max_per_unit": "",
            "spike_count_range_per_unit": "",
            "spike_count_median_per_unit": "",
            "spike_count_total": "",
            "units_with_spikes": "",
            "units_with_zero_spikes": "",
        }


def infer_plate_family(recording: str, lane: str) -> str:
    if "FortyEightWellLumos" in recording or lane == "48well_auto":
        return "FortyEightWellLumos"
    if "sixwell" in recording.lower() or "sixwell" in lane.lower():
        return "SixWell"
    return ""


def infer_well_status(row: dict[str, str]) -> str:
    failed = row.get("first_failed_stage", "")
    if failed:
        return f"needs_attention:{failed}"
    if row.get("nwb_units_state") == "COMPLETED":
        return "complete_nwb_units"
    highest = row.get("highest_completed_stage", "")
    if highest in {"postprocessing", "curation", "visualization", "results_collector", "quality_control", "quality_control_collector"}:
        return "downstream_after_kilosort"
    if highest == "spikesort_kilosort4":
        return "passed_kilosort_waiting_downstream"
    if highest in {"job_dispatch", "preprocessing", "nwb_ecephys"}:
        return "before_or_waiting_kilosort"
    effective_state = row.get("effective_aind_job_state", "")
    if effective_state == "RUNNING":
        return "aind_parent_running_no_trace_or_waiting"
    if effective_state == "PENDING":
        return "aind_parent_pending"
    if effective_state.startswith("FAILED"):
        return "needs_attention:aind_parent_failed"
    return "not_started_or_unknown"


def summarize_recording(rows: list[dict[str, str]]) -> dict[str, str | int]:
    total = len(rows)
    nwb_units = sum(row["nwb_units_state"] == "COMPLETED" for row in rows)
    kilosort = sum(row["kilosort_state"] == "COMPLETED" for row in rows)
    failed = sum(row["well_status"].startswith("needs_attention") for row in rows)
    if total and nwb_units == total:
        status = "complete_all_wells"
    elif failed:
        status = "needs_attention"
    elif total and kilosort == total:
        status = "all_wells_passed_kilosort_downstream_active"
    elif kilosort:
        status = "partially_through_kilosort"
    else:
        status = "in_progress_before_or_waiting_kilosort"
    return {
        "recording": rows[0]["recording"],
        "lane": rows[0]["lane"],
        "plate_family": rows[0]["plate_family"],
        "total_wells": total,
        "nwb_units_completed_wells": nwb_units,
        "kilosort_completed_wells": kilosort,
        "failed_wells": failed,
        "recording_status": status,
    }


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--autolane-tsv",
        default=PROJECT_ROOT
        / "jobs"
        / "aind_autolane_new_upload_20260707_132852"
        / "recording_batch_plan"
        / "submitted_recording_batches.tsv",
        type=Path,
    )
    parser.add_argument(
        "--sixwell-tsv",
        default=PROJECT_ROOT
        / "jobs"
        / "aind_sixwell_manual_primary_20260707_133604"
        / "recording_batch_plan"
        / "submitted_recording_batches.tsv",
        type=Path,
    )
    parser.add_argument(
        "--smoke-manifest",
        default=PROJECT_ROOT
        / "jobs"
        / "aind_batches"
        / "sixwell_smoke_20260528_134-0150_pv_cl23_dv_exp17_2_000_primary_raw"
        / "well_batch_manifest.csv",
        type=Path,
    )
    parser.add_argument(
        "--quote-fix-manifest",
        default=PROJECT_ROOT
        / "jobs"
        / "aind_rerun_after_runoptions_quote_fix_20260707_1445"
        / "quote_fix_rerun_manifest.csv",
        type=Path,
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    expected_rows = []
    expected_rows.extend(read_submitted_batches(args.autolane_tsv, "48well_auto"))
    expected_rows.extend(read_submitted_batches(args.sixwell_tsv, "sixwell_manual_primary"))
    expected_rows.extend(read_smoke_row(args.smoke_manifest))

    quote_fix = read_quote_fix_map(args.quote_fix_manifest)
    all_job_ids: list[str] = []
    for row in expected_rows:
        all_job_ids.extend(
            [
                row.get("export_job", ""),
                row.get("nwb_job", ""),
                row.get("spikeinterface_job", ""),
                row.get("aind_job", ""),
            ]
        )
        qrow = quote_fix.get((row.get("recording", ""), row.get("well", "")))
        if qrow:
            all_job_ids.extend([qrow.get("failed_rerun_aind_job", ""), qrow.get("quote_fix_rerun_aind_job", "")])

    live_jobs = squeue_jobs()
    accounting = sacct_states(all_job_ids)

    well_rows: list[dict[str, str]] = []
    live_kilosort_state_counts = Counter(
        job["state"]
        for job in live_jobs.values()
        if "spikesort_kilosort4" in job.get("job_name", "")
    )
    live_aind_parent_state_counts = Counter(
        job["state"]
        for job in live_jobs.values()
        if job.get("job_name") == "axion-aind-nwb"
    )

    for original in expected_rows:
        recording = original.get("recording", "")
        well = original.get("well", "")
        qrow = quote_fix.get((recording, well), {})
        effective_aind_job = qrow.get("quote_fix_rerun_aind_job") or original.get("aind_job", "")
        trace_path = RESULTS_ROOT / recording / well / "nextflow" / "trace.txt"
        results_dir = RESULTS_ROOT / recording / well
        trace = parse_trace(trace_path)
        completed_stages = [
            task for task in TASK_ORDER if trace.get(task, {}).get("status") == "COMPLETED"
        ]
        failed_stages = [
            task for task in TASK_ORDER if trace.get(task, {}).get("status") == "FAILED"
        ]
        highest_completed = completed_stages[-1] if completed_stages else ""
        first_failed = failed_stages[0] if failed_stages else ""
        kilosort_state = trace.get("spikesort_kilosort4", {}).get("status") or "not_entered"
        row = {
            "lane": original.get("lane", ""),
            "recording": recording,
            "well": well,
            "plate_family": infer_plate_family(recording, original.get("lane", "")),
            "source_manifest": original.get("source_manifest", ""),
            "export_job": original.get("export_job", ""),
            "export_job_state": merged_job_state(original.get("export_job", ""), accounting, live_jobs),
            "nwb_job": original.get("nwb_job", ""),
            "nwb_job_state": merged_job_state(original.get("nwb_job", ""), accounting, live_jobs),
            "spikeinterface_job": original.get("spikeinterface_job", ""),
            "spikeinterface_job_state": merged_job_state(original.get("spikeinterface_job", ""), accounting, live_jobs),
            "original_aind_job": original.get("aind_job", ""),
            "original_aind_job_state": merged_job_state(original.get("aind_job", ""), accounting, live_jobs),
            "failed_first_rerun_aind_job": qrow.get("failed_rerun_aind_job", ""),
            "failed_first_rerun_aind_job_state": merged_job_state(qrow.get("failed_rerun_aind_job", ""), accounting, live_jobs),
            "quote_fix_rerun_aind_job": qrow.get("quote_fix_rerun_aind_job", ""),
            "quote_fix_rerun_aind_job_state": merged_job_state(qrow.get("quote_fix_rerun_aind_job", ""), accounting, live_jobs),
            "effective_aind_job": effective_aind_job,
            "effective_aind_job_state": merged_job_state(effective_aind_job, accounting, live_jobs),
            "trace_path": str(trace_path),
            "trace_exists": str(trace_path.exists()),
            "highest_completed_stage": highest_completed,
            "first_failed_stage": first_failed,
            "failure_summary": task_failure_summary(recording, well, first_failed, trace) if first_failed else "",
            "kilosort_state": kilosort_state,
            "kilosort_native_id": trace.get("spikesort_kilosort4", {}).get("native_id", ""),
            "kilosort_duration": trace.get("spikesort_kilosort4", {}).get("duration", ""),
            "nwb_units_state": trace.get("nwb_units", {}).get("status", "not_entered"),
            "nwb_units_native_id": trace.get("nwb_units", {}).get("native_id", ""),
        }
        row.update(read_unit_metrics(results_dir))
        for task in TASK_ORDER:
            row[f"{task}_state"] = trace.get(task, {}).get("status", "not_entered")
            row[f"{task}_native_id"] = trace.get(task, {}).get("native_id", "")
            row[f"{task}_hash"] = trace.get(task, {}).get("hash", "")
        row["well_status"] = infer_well_status(row)
        well_rows.append(row)

    recording_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in well_rows:
        recording_groups[row["recording"]].append(row)
    recording_rows = [summarize_recording(rows) for _, rows in sorted(recording_groups.items())]

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "expected_well_pipelines": len(well_rows),
        "expected_recordings": len(recording_rows),
        "plate_family_counts_by_well": dict(Counter(row["plate_family"] for row in well_rows)),
        "lane_counts_by_well": dict(Counter(row["lane"] for row in well_rows)),
        "well_status_counts": dict(Counter(row["well_status"] for row in well_rows)),
        "highest_completed_stage_counts": dict(Counter(row["highest_completed_stage"] or "none" for row in well_rows)),
        "kilosort_state_counts": dict(Counter(row["kilosort_state"] for row in well_rows)),
        "nwb_units_state_counts": dict(Counter(row["nwb_units_state"] for row in well_rows)),
        "effective_aind_job_state_counts": dict(Counter(row["effective_aind_job_state"] or "missing" for row in well_rows)),
        "recording_status_counts": dict(Counter(row["recording_status"] for row in recording_rows)),
        "live_slurm_kilosort_child_state_counts": dict(live_kilosort_state_counts),
        "live_slurm_aind_parent_state_counts": dict(live_aind_parent_state_counts),
        "unit_metrics_status_counts": dict(Counter(row["unit_metrics_status"] for row in well_rows)),
        "unit_metrics_totals": {
            "wells_with_unit_metrics": sum(row["unit_metrics_status"] == "ok" for row in well_rows),
            "units_total": sum(int(row["unit_count_total"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
            "kslabel_good_total": sum(int(row["kslabel_good_count"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
            "kslabel_mua_total": sum(int(row["kslabel_mua_count"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
            "kslabel_noise_total": sum(int(row["kslabel_noise_count"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
            "sua_total": sum(int(row["unit_count_sua"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
            "mua_total": sum(int(row["unit_count_mua"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
            "noise_total": sum(int(row["unit_count_noise"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
            "spike_count_total": sum(int(row["spike_count_total"] or 0) for row in well_rows if row["unit_metrics_status"] == "ok"),
        },
        "definition": {
            "unit_of_account": "one recording plus one well",
            "passed_kilosort": "spikesort_kilosort4 COMPLETED with exit 0 in the per-well Nextflow trace",
            "fully_done": "nwb_units COMPLETED with exit 0 in the per-well Nextflow trace",
            "effective_aind_job": "quote-fix rerun job when one exists, otherwise the originally submitted AIND parent job",
            "unit_count_sua": "KSLabel=good in curated SpikeInterface sorting properties",
            "unit_count_mua": "KSLabel=mua in curated SpikeInterface sorting properties",
            "unit_count_noise": "KSLabel=noise if present; absence of this label does not prove no noise",
            "kslabel_counts": "Explicit aliases for the actual observed Kilosort/Phy KSLabel source",
            "spike_count_range_per_unit": "min-max spike count across units in curated/block0_None_recording1/spikes.npy",
        },
    }

    well_fieldnames = [
        "lane",
        "recording",
        "well",
        "plate_family",
        "well_status",
        "highest_completed_stage",
        "first_failed_stage",
        "failure_summary",
        "kilosort_state",
        "nwb_units_state",
        "effective_aind_job",
        "effective_aind_job_state",
        "original_aind_job",
        "original_aind_job_state",
        "failed_first_rerun_aind_job",
        "failed_first_rerun_aind_job_state",
        "quote_fix_rerun_aind_job",
        "quote_fix_rerun_aind_job_state",
        "export_job",
        "export_job_state",
        "nwb_job",
        "nwb_job_state",
        "spikeinterface_job",
        "spikeinterface_job_state",
        "kilosort_native_id",
        "kilosort_duration",
        "nwb_units_native_id",
        "unit_metrics_status",
        "unit_count_total",
        "kslabel_good_count",
        "kslabel_mua_count",
        "kslabel_noise_count",
        "unit_count_sua",
        "unit_count_mua",
        "unit_count_noise",
        "unit_label_counts",
        "unit_labels_observed",
        "unit_label_source",
        "unit_label_warning",
        "spike_count_min_per_unit",
        "spike_count_max_per_unit",
        "spike_count_range_per_unit",
        "spike_count_median_per_unit",
        "spike_count_total",
        "units_with_spikes",
        "units_with_zero_spikes",
        "trace_exists",
        "trace_path",
        "source_manifest",
    ]
    for task in TASK_ORDER:
        well_fieldnames.extend([f"{task}_state", f"{task}_native_id", f"{task}_hash"])

    recording_fieldnames = [
        "recording",
        "lane",
        "plate_family",
        "recording_status",
        "total_wells",
        "nwb_units_completed_wells",
        "kilosort_completed_wells",
        "failed_wells",
    ]
    unit_fieldnames = [
        "lane",
        "recording",
        "well",
        "plate_family",
        "well_status",
        "kilosort_state",
        "nwb_units_state",
        "unit_metrics_status",
        "unit_count_total",
        "kslabel_good_count",
        "kslabel_mua_count",
        "kslabel_noise_count",
        "unit_count_sua",
        "unit_count_mua",
        "unit_count_noise",
        "unit_label_counts",
        "unit_labels_observed",
        "unit_label_source",
        "unit_label_warning",
        "spike_count_min_per_unit",
        "spike_count_max_per_unit",
        "spike_count_range_per_unit",
        "spike_count_median_per_unit",
        "spike_count_total",
        "units_with_spikes",
        "units_with_zero_spikes",
        "trace_path",
    ]

    write_csv(args.output_dir / "unified_well_status.csv", well_rows, well_fieldnames)
    write_csv(args.output_dir / "unified_recording_status.csv", recording_rows, recording_fieldnames)
    write_csv(args.output_dir / "unit_metrics_by_well.csv", well_rows, unit_fieldnames)
    (args.output_dir / "unified_status_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"created_at: {summary['created_at']}",
        f"expected_well_pipelines: {summary['expected_well_pipelines']}",
        f"expected_recordings: {summary['expected_recordings']}",
        f"plate_family_counts_by_well: {json.dumps(summary['plate_family_counts_by_well'], sort_keys=True)}",
        f"lane_counts_by_well: {json.dumps(summary['lane_counts_by_well'], sort_keys=True)}",
        f"well_status_counts: {json.dumps(summary['well_status_counts'], sort_keys=True)}",
        f"highest_completed_stage_counts: {json.dumps(summary['highest_completed_stage_counts'], sort_keys=True)}",
        f"kilosort_state_counts: {json.dumps(summary['kilosort_state_counts'], sort_keys=True)}",
        f"nwb_units_state_counts: {json.dumps(summary['nwb_units_state_counts'], sort_keys=True)}",
        f"effective_aind_job_state_counts: {json.dumps(summary['effective_aind_job_state_counts'], sort_keys=True)}",
        f"recording_status_counts: {json.dumps(summary['recording_status_counts'], sort_keys=True)}",
        f"live_slurm_kilosort_child_state_counts: {json.dumps(summary['live_slurm_kilosort_child_state_counts'], sort_keys=True)}",
        f"live_slurm_aind_parent_state_counts: {json.dumps(summary['live_slurm_aind_parent_state_counts'], sort_keys=True)}",
        f"unit_metrics_status_counts: {json.dumps(summary['unit_metrics_status_counts'], sort_keys=True)}",
        f"unit_metrics_totals: {json.dumps(summary['unit_metrics_totals'], sort_keys=True)}",
        "",
        "Definitions:",
        "- unit_of_account: one recording plus one well",
        "- passed_kilosort: spikesort_kilosort4 COMPLETED with exit 0 in the per-well Nextflow trace",
        "- fully_done: nwb_units COMPLETED with exit 0 in the per-well Nextflow trace",
        "- effective_aind_job: quote-fix rerun job when one exists, otherwise the originally submitted AIND parent job",
        "- unit_count_sua: KSLabel=good in curated SpikeInterface sorting properties",
        "- unit_count_mua: KSLabel=mua in curated SpikeInterface sorting properties",
        "- unit_count_noise: KSLabel=noise if present; absence of this label does not prove no noise",
        "- spike_count_range_per_unit: min-max spike count across units in curated/block0_None_recording1/spikes.npy",
        "",
        f"well_csv: {args.output_dir / 'unified_well_status.csv'}",
        f"recording_csv: {args.output_dir / 'unified_recording_status.csv'}",
        f"unit_metrics_csv: {args.output_dir / 'unit_metrics_by_well.csv'}",
        f"summary_json: {args.output_dir / 'unified_status_summary.json'}",
    ]
    (args.output_dir / "unified_status_summary.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    print((args.output_dir / "unified_status_summary.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
