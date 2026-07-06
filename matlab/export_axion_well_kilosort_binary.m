function manifest = export_axion_well_kilosort_binary(rawFile, well, outputBin, varargin)
%EXPORT_AXION_WELL_KILOSORT_BINARY Export one Axion well as Kilosort binary.
%
% manifest = export_axion_well_kilosort_binary(rawFile, "A1", outputBin, ...)
%
% The output binary is int16, time-major/interleaved by channel:
% sample 1 channel 1..N, sample 2 channel 1..N, etc. Channel order is driven
% by the repo-controlled electrode geometry CSV.

parser = inputParser;
parser.addRequired("rawFile", @(x) ischar(x) || isstring(x));
parser.addRequired("well", @(x) ischar(x) || isstring(x));
parser.addRequired("outputBin", @(x) ischar(x) || isstring(x));
parser.addParameter("ElectrodeGeometry", fullfile(repo_root_from_this_file(), "metadata", "plate_maps", "axion_per_well_4x4_electrode_geometry.csv"), @(x) ischar(x) || isstring(x));
parser.addParameter("OutputDir", "", @(x) ischar(x) || isstring(x));
parser.addParameter("AxionLoaderRoot", "/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main", @(x) ischar(x) || isstring(x));
parser.addParameter("StartTime", 0, @(x) isnumeric(x) && isscalar(x) && x >= 0);
parser.addParameter("Duration", NaN, @(x) isnumeric(x) && isscalar(x));
parser.addParameter("Dataset", "BroadbandHighFrequency", @(x) ischar(x) || isstring(x));
parser.addParameter("RecordingStem", "", @(x) ischar(x) || isstring(x));
parser.parse(rawFile, well, outputBin, varargin{:});

rawFile = string(parser.Results.rawFile);
well = upper(string(parser.Results.well));
outputBin = string(parser.Results.outputBin);
geometryPath = string(parser.Results.ElectrodeGeometry);
outputDir = string(parser.Results.OutputDir);
axionLoaderRoot = string(parser.Results.AxionLoaderRoot);
startTime = double(parser.Results.StartTime);
duration = double(parser.Results.Duration);
datasetName = string(parser.Results.Dataset);
recordingStem = string(parser.Results.RecordingStem);

if strlength(outputDir) == 0
    outputDir = string(fileparts(outputBin));
end
if strlength(recordingStem) == 0
    [~, rawName] = fileparts(rawFile);
    recordingStem = erase(string(rawName), "_BroadbandProcessor");
end
if ~isfolder(outputDir)
    mkdir(outputDir);
end

addpath(genpath(axionLoaderRoot), "-end");
addpath(fullfile(repo_root_from_this_file(), "matlab", "axionfileloader_overrides"), "-begin");

geometry = readtable(geometryPath, "TextType", "string");
geometry = sortrows(geometry, ["electrode_row", "electrode_col"]);
if ~ismember("connected", string(geometry.Properties.VariableNames))
    geometry.connected = true(height(geometry), 1);
end
geometry = geometry(connected_mask(geometry.connected), :);

axisFile = AxisFile(char(rawFile));
cleanupAxis = onCleanup(@() delete(axisFile));
dataSet = select_dataset(axisFile, datasetName);
if isempty(dataSet)
    error("Dataset %s was not found in %s.", datasetName, rawFile);
end
if numel(dataSet) > 1
    dataSet = dataSet(1);
end

if isnan(duration) || duration <= 0
    timeRange = "all";
else
    timeRange = [startTime, startTime + duration];
end

fprintf("Loading %s, well %s, dataset %s, time range %s\n", rawFile, well, datasetName, mat2str(timeRange));
waveforms = dataSet.LoadData(char(well), "all", timeRange, LoadArgs.ByElectrodeDimensions);

wellRow = char(well);
wellRow = double(upper(wellRow(1)) - 'A' + 1);
wellCol = str2double(extractAfter(well, 1));

channelVectors = cell(height(geometry), 1);
mappingRows = struct([]);
for idx = 1:height(geometry)
    electrodeLabel = char(string(geometry.channel_in_well(idx)));
    electrodeCol = double(geometry.electrode_col(idx));
    electrodeRow = double(geometry.electrode_row(idx));
    waveform = waveforms{wellRow, wellCol, electrodeCol, electrodeRow};
    if isempty(waveform)
        error("Missing waveform for %s_%s at Axion index {%d,%d,%d,%d}.", ...
            well, electrodeLabel, wellRow, wellCol, electrodeCol, electrodeRow);
    end
    channelVectors{idx} = waveform.Data(:);

    mappingRows(idx).channel_index_zero_based = idx - 1; %#ok<AGROW>
    mappingRows(idx).channel_index_one_based = idx; %#ok<AGROW>
    mappingRows(idx).well = well; %#ok<AGROW>
    mappingRows(idx).channel_in_well = string(electrodeLabel); %#ok<AGROW>
    mappingRows(idx).electrode_row = electrodeRow; %#ok<AGROW>
    mappingRows(idx).electrode_col = electrodeCol; %#ok<AGROW>
    mappingRows(idx).x_um = geometry.x_um(idx); %#ok<AGROW>
    mappingRows(idx).y_um = geometry.y_um(idx); %#ok<AGROW>
    mappingRows(idx).axion_well_row = wellRow; %#ok<AGROW>
    mappingRows(idx).axion_well_col = wellCol; %#ok<AGROW>
    mappingRows(idx).axion_electrode_col = electrodeCol; %#ok<AGROW>
    mappingRows(idx).axion_electrode_row = electrodeRow; %#ok<AGROW>
    mappingRows(idx).channel_achk = double(waveform.Channel.ChannelAchk); %#ok<AGROW>
    mappingRows(idx).channel_index = double(waveform.Channel.ChannelIndex); %#ok<AGROW>
end

lengths = cellfun(@numel, channelVectors);
if numel(unique(lengths)) ~= 1
    error("Loaded channel lengths differ: %s", mat2str(lengths(:)'));
end
nSamples = lengths(1);
nChannels = numel(channelVectors);
data = zeros(nSamples, nChannels, "int16");
for idx = 1:nChannels
    data(:, idx) = int16(channelVectors{idx});
end

outputParent = fileparts(outputBin);
if strlength(outputParent) > 0 && ~isfolder(outputParent)
    mkdir(outputParent);
end
fid = fopen(outputBin, "w");
if fid <= 0
    error("Could not open output binary for writing: %s", outputBin);
end
cleanupBin = onCleanup(@() fclose(fid));
count = fwrite(fid, data.', "int16");
expected = nSamples * nChannels;
if count ~= expected
    error("Wrote %d int16 values but expected %d.", count, expected);
end
clear cleanupBin
fclose(fid);

mappingTable = struct2table(mappingRows);
mappingCsv = fullfile(outputDir, "channel_mapping.csv");
writetable(mappingTable, mappingCsv);

manifest = struct();
manifest.analysis_kind = "axion_well_kilosort_binary_export";
manifest.raw_file = rawFile;
manifest.recording_stem = recordingStem;
manifest.well = well;
manifest.dataset = datasetName;
manifest.output_bin = outputBin;
manifest.channel_mapping_csv = string(mappingCsv);
manifest.electrode_geometry_csv = geometryPath;
manifest.fs = double(dataSet.SamplingFrequency);
manifest.dtype = "int16";
manifest.n_chan_bin = nChannels;
manifest.n_samples = nSamples;
manifest.duration_s = nSamples / double(dataSet.SamplingFrequency);
manifest.start_time_s = startTime;
manifest.requested_duration_s = duration;
manifest.voltage_scale_v_per_sample = double(dataSet.VoltageScale);
manifest.write_order = "time_major_interleaved; fwrite(data.', 'int16')";
manifest.notes = [
    "Axion LoadData indexes as {well_row, well_col, electrode_col, electrode_row}.", ...
    "Axion electrode labels are column-row, so electrode 31 is electrode_col=3 and electrode_row=1.", ...
    "Channel order is sorted by electrode_row then electrode_col from the geometry CSV.", ...
    "Values are raw int16 ADC samples; Kilosort receives data_dtype=int16."
];

manifestPath = fullfile(outputDir, "binary_export_manifest.json");
write_text_file(manifestPath, jsonencode(manifest, PrettyPrint=true));
fprintf("Wrote binary: %s\n", outputBin);
fprintf("Wrote mapping: %s\n", mappingCsv);
fprintf("Wrote manifest: %s\n", manifestPath);
end

function dataSet = select_dataset(axisFile, datasetName)
switch lower(string(datasetName))
    case "rawvoltagedata"
        dataSet = axisFile.RawVoltageData;
    case "broadbandhighfrequency"
        dataSet = axisFile.BroadbandHighFrequency;
    case "broadbandlowfrequency"
        dataSet = axisFile.BroadbandLowFrequency;
    otherwise
        error("Unsupported dataset selector: %s", datasetName);
end
end

function mask = connected_mask(values)
if islogical(values)
    mask = values;
elseif isnumeric(values)
    mask = values ~= 0;
else
    textValues = lower(strtrim(string(values)));
    mask = ismember(textValues, ["1", "true", "yes", "y"]);
end
end

function write_text_file(path, text)
fid = fopen(path, "w");
if fid <= 0
    error("Could not open text file for writing: %s", path);
end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, "%s\n", text);
clear cleanup
fclose(fid);
end

function repoRoot = repo_root_from_this_file()
thisFile = mfilename("fullpath");
repoRoot = fileparts(fileparts(thisFile));
end
