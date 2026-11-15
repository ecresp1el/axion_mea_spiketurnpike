# LD1–LD2–LD3 unit and recording view

The requested 3D figure follows the 2D group/PSAM recording-cloud view. It uses
all 1,554 Actuators + effectors units and the identical 215 selected raw metrics.
SUA/MUA are pooled; units remain the observations.

## Where LD3 comes from

The locked model file stores only two projection columns. A separate LDA is
therefore fitted with three components, using the **frozen** signed-log1p,
imputation, and scaling parameters, the same class encoding and empirical
class priors, `solver=eigen`, and shrinkage 0.01. No feature selection or tuning
is repeated. Signs of the first two refitted columns are aligned to the
original columns and their coordinates must match within 1e-7 before proceeding.

The output retains the original LD1/LD2 coordinates exactly and appends LD3
from this matched fit. The three-column extension is saved independently.
The active two-axis model, its configuration, and the temporal decoders are
unchanged. This is a descriptive full-data extension, not held-out validation.
Its LD3 sign has no intrinsic biological meaning.

## Reading the figure

- Left: all units colored by construct, with 29 solid colored recording-centroid
  circles and four larger dark filled group-centroid circles.
- Right: all 339 PSAM units colored by their five unique recordings, with
  matching solid centroid circles and a dark PSAM group centroid.
- Wireframes: covariance ellipsoids with radii of two standard deviations
  along each of the three covariance principal axes. These show unit spread,
  not confidence intervals or guaranteed empirical coverage. Overlap is retained.

Each recording centroid is the arithmetic mean of that recording's unit scores.
Each group centroid is the unit-weighted group mean. A single camera angle can
hide overlapping points; the self-contained HTML allows rotation and zoom.

## Files

```text
/scratch/parent_root/parent0/elcrespo/mcs_unit_analysis/lda_3d/
```

- `lda_215_3d_recordings.png` / `.pdf`: static 3D group/recording figure.
- `lda_3d_interactive.html`: offline rotatable view; open in a browser, drag to
  rotate, scroll to zoom, toggle cloud outlines. It needs no server or network.
- `unit_ld1_ld2_ld3.csv`: all unit keys, constructs, and three LD coordinates.
- `recording_centroids_3d.csv`, `group_centroids_3d.csv`: exact summary coordinates.
- `extension_215_lda_state.npz`: frozen preprocessing and the three-column extension.
- `manifest.json`: fit/alignment checks, ellipsoid parameters, source/output hashes.

Use **recording_id + unit_id** to identify units. Generator:
[plot_mcs_lda_3d.py](../scripts/plot_mcs_lda_3d.py).
The interactive view is an orthographic canvas rendering of the same coordinates
and ellipsoid curves; it adds no embedding, normalization, or alternative model.

## Marker and grid styling

All recording centroids are solid colored circles. Group centroids are solid dark circles explicitly layered above every unit, recording marker, and wireframe. Matplotlib automatic depth-based artist reordering is disabled for this annotation priority; group positions remain unchanged. The HTML likewise draws group centroids last at every rotation. Axis grids use at most three major intervals and lighter lines; ellipsoid wireframes use fewer meridians/parallels.
