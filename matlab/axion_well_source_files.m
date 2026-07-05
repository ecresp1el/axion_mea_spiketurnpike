function files = axion_well_source_files(dataDir, well, varargin)
%AXION_WELL_SOURCE_FILES Resolve Axion source files and geometry for one well.
%
% files = axion_well_source_files(dataDir, "A1", ...
%     "PlateMap", "../metadata/plate_maps/axion_48_well_opto_plate_map.csv", ...
%     "ElectrodeGeometry", "../metadata/plate_maps/axion_per_well_4x4_electrode_geometry.csv")
%
% The helper does not parse or modify Axion raw data. It gives MATLAB code a
% reproducible way to validate the well against a repo-controlled plate map,
% locate the matching Axion export set, and load the per-well electrode geometry
% that is also used for Kilosort probe generation.

parser = inputParser;
parser.addRequired("dataDir", @(x) ischar(x) || isstring(x));
parser.addRequired("well", @(x) ischar(x) || isstring(x));
parser.addParameter("PlateMap", "", @(x) ischar(x) || isstring(x));
parser.addParameter("ElectrodeGeometry", "", @(x) ischar(x) || isstring(x));
parser.addParameter("RecordingStem", "", @(x) ischar(x) || isstring(x));
parser.parse(dataDir, well, varargin{:});

dataDir = char(parser.Results.dataDir);
well = upper(char(parser.Results.well));
plateMapPath = char(parser.Results.PlateMap);
geometryPath = char(parser.Results.ElectrodeGeometry);
recordingStem = char(parser.Results.RecordingStem);

if strlength(plateMapPath) == 0
    plateMapPath = fullfile(repo_root_from_this_file(), "metadata", "plate_maps", "axion_48_well_opto_plate_map.csv");
end
if strlength(geometryPath) == 0
    geometryPath = fullfile(repo_root_from_this_file(), "metadata", "plate_maps", "axion_per_well_4x4_electrode_geometry.csv");
end

plateMap = readtable(plateMapPath, "TextType", "string");
geometry = readtable(geometryPath, "TextType", "string");
plateRow = plateMap(strcmpi(plateMap.well, well), :);
if height(plateRow) ~= 1
    error("Well %s was not found exactly once in plate map %s.", well, plateMapPath);
end

if strlength(recordingStem) == 0
    listing = dir(fullfile(dataDir, "**", "*_spike_list.csv"));
    listing = listing(~startsWith({listing.name}, "._"));
    if isempty(listing)
        error("No *_spike_list.csv files found under %s.", dataDir);
    end
    spikeList = fullfile(listing(1).folder, listing(1).name);
    recordingStem = erase(listing(1).name, "_spike_list.csv");
else
    listing = dir(fullfile(dataDir, "**", string(recordingStem) + "_spike_list.csv"));
    if isempty(listing)
        error("Could not find %s_spike_list.csv under %s.", recordingStem, dataDir);
    end
    spikeList = fullfile(listing(1).folder, listing(1).name);
end

recordingDir = fileparts(spikeList);
files = struct();
files.data_dir = string(dataDir);
files.recording_dir = string(recordingDir);
files.recording_stem = string(recordingStem);
files.well = string(well);
files.plate_map_csv = string(plateMapPath);
files.electrode_geometry_csv = string(geometryPath);
files.plate_row = plateRow;
files.electrode_geometry = geometry;
files.spike_list_csv = string(spikeList);
files.spike_counts_csv = string(fullfile(recordingDir, recordingStem + "_spike_counts.csv"));
files.environmental_csv = string(fullfile(recordingDir, recordingStem + "_environmental_data.csv"));
files.raw_file = string(fullfile(recordingDir, recordingStem + ".raw"));
files.spk_file = string(fullfile(recordingDir, recordingStem + ".spk"));
files.kilosort_binary_expected = "";

required = ["spike_counts_csv", "raw_file"];
for idx = 1:numel(required)
    field = char(required(idx));
    if ~isfile(files.(field))
        warning("Expected Axion file is missing: %s", files.(field));
    end
end
end

function repoRoot = repo_root_from_this_file()
thisFile = mfilename("fullpath");
repoRoot = fileparts(fileparts(thisFile));
end
