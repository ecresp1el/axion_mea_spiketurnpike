function result = preflight_axion_raw_ingestion(rawFile, outputJson, varargin)
%PREFLIGHT_AXION_RAW_INGESTION Diagnose whether an Axion raw can enter export.
%
% This is intentionally diagnostic. It does not write Kilosort binaries, NWB,
% or AIND inputs. It checks the exact ingestion path used by export:
%   1. metadata peek without AxisFile dataset construction,
%   2. real AxisFile(rawFile) construction,
%   3. requested dataset visibility,
%   4. optional tiny LoadData call for one well.

parser = inputParser;
parser.addRequired("rawFile", @(x) ischar(x) || isstring(x));
parser.addRequired("outputJson", @(x) ischar(x) || isstring(x));
parser.addParameter("AxionLoaderRoot", "/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main", @(x) ischar(x) || isstring(x));
parser.addParameter("Dataset", "BroadbandHighFrequency", @(x) ischar(x) || isstring(x));
parser.addParameter("TestWell", "A1", @(x) ischar(x) || isstring(x));
parser.addParameter("DoTinyLoad", false, @(x) islogical(x) || isnumeric(x));
parser.addParameter("TinyLoadDurationS", 1, @(x) isnumeric(x) && isscalar(x) && x > 0);
parser.parse(rawFile, outputJson, varargin{:});

rawFile = string(parser.Results.rawFile);
outputJson = string(parser.Results.outputJson);
axionLoaderRoot = string(parser.Results.AxionLoaderRoot);
datasetName = string(parser.Results.Dataset);
testWell = upper(string(parser.Results.TestWell));
doTinyLoad = logical(parser.Results.DoTinyLoad);
tinyLoadDurationS = double(parser.Results.TinyLoadDurationS);

addpath(genpath(axionLoaderRoot), "-end");
addpath(fullfile(repo_root_from_this_file(), "matlab", "axionfileloader_overrides"), "-begin");

result = struct();
result.analysis_kind = "axion_raw_ingestion_preflight";
result.checked_at = string(datetime("now", "TimeZone", "local", "Format", "yyyy-MM-dd HH:mm:ss ZZZZ"));
result.raw_file = rawFile;
result.raw_name = string(get_file_name(rawFile));
result.raw_file_kind = raw_file_kind(rawFile);
result.dataset = datasetName;
result.test_well = testWell;
result.do_tiny_load = doTinyLoad;
result.tiny_load_duration_s = tinyLoadDurationS;
result.peek_ok = false;
result.peek_error = "";
result.peek_warning_id = "";
result.peek_warning_message = "";
result.axisfile_ok = false;
result.axisfile_error = "";
result.axisfile_warning_id = "";
result.axisfile_warning_message = "";
result.dataset_ok = false;
result.dataset_error = "";
result.tiny_load_ok = false;
result.tiny_load_error = "";
result.overall_status = "not_run";

try
    lastwarn("");
    info = peek_axion_raw_metadata(rawFile);
    [warningMessage, warningId] = lastwarn;
    result.peek_warning_id = string(warningId);
    result.peek_warning_message = string(warningMessage);
    result.peek_ok = true;
    result.peek = info;
catch ME
    [warningMessage, warningId] = lastwarn;
    result.peek_warning_id = string(warningId);
    result.peek_warning_message = string(warningMessage);
    result.peek_error = string(getReport(ME, "extended", "hyperlinks", "off"));
end

axisFile = [];
cleanupAxis = [];
try
    lastwarn("");
    tic;
    axisFile = AxisFile(char(rawFile));
    result.axisfile_elapsed_s = toc;
    [warningMessage, warningId] = lastwarn;
    result.axisfile_warning_id = string(warningId);
    result.axisfile_warning_message = string(warningMessage);
    cleanupAxis = onCleanup(@() delete(axisFile)); %#ok<NASGU>
    result.axisfile_ok = true;
catch ME
    result.axisfile_elapsed_s = toc;
    [warningMessage, warningId] = lastwarn;
    result.axisfile_warning_id = string(warningId);
    result.axisfile_warning_message = string(warningMessage);
    result.axisfile_error = string(getReport(ME, "extended", "hyperlinks", "off"));
end

dataSet = [];
if result.axisfile_ok
    try
        dataSet = select_dataset(axisFile, datasetName);
        if isempty(dataSet)
            error("Dataset %s was not found.", datasetName);
        end
        if numel(dataSet) > 1
            dataSet = dataSet(1);
        end
        result.dataset_ok = true;
        result.dataset_sampling_frequency_hz = double(dataSet.SamplingFrequency);
        result.dataset_voltage_scale_v_per_sample = double(dataSet.VoltageScale);
        if isprop(dataSet, "Duration") && ~isempty(dataSet.Duration)
            result.dataset_duration_s = double(dataSet.Duration);
        end
    catch ME
        result.dataset_error = string(getReport(ME, "extended", "hyperlinks", "off"));
    end
end

if result.dataset_ok && doTinyLoad
    try
        tic;
        waveforms = dataSet.LoadData(char(testWell), [0, tinyLoadDurationS], LoadArgs.ByElectrodeDimensions);
        result.tiny_load_elapsed_s = toc;
        result.tiny_load_ok = true;
        result.tiny_load_class = string(class(waveforms));
        result.tiny_load_size = mat2str(size(waveforms));
    catch ME
        result.tiny_load_elapsed_s = toc;
        result.tiny_load_error = string(getReport(ME, "extended", "hyperlinks", "off"));
    end
elseif result.dataset_ok && ~doTinyLoad
    result.tiny_load_ok = true;
    result.tiny_load_error = "skipped";
end

if result.peek_ok && result.axisfile_ok && result.dataset_ok && result.tiny_load_ok
    result.overall_status = "ok";
elseif result.peek_ok && ~result.axisfile_ok
    result.overall_status = "axisfile_open_failed_after_metadata_peek";
elseif ~result.peek_ok
    result.overall_status = "metadata_peek_failed";
elseif result.axisfile_ok && ~result.dataset_ok
    result.overall_status = "dataset_unavailable";
else
    result.overall_status = "tiny_load_failed";
end

outputDir = fileparts(outputJson);
if strlength(outputDir) > 0 && ~isfolder(outputDir)
    mkdir(outputDir);
end
write_text_file(outputJson, jsonencode(result, PrettyPrint=true));
fprintf("Preflight status: %s\n", result.overall_status);
fprintf("Wrote preflight JSON: %s\n", outputJson);
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

function kind = raw_file_kind(rawFile)
if endsWith(rawFile, "_BroadbandProcessor.raw")
    kind = "broadband_processor_raw";
else
    kind = "primary_raw";
end
end

function name = get_file_name(pathValue)
[~, name, ext] = fileparts(pathValue);
name = name + ext;
end

function write_text_file(path, text)
fid = fopen(path, "w");
if fid <= 0
    error("Could not open text file for writing: %s", path);
end
fprintf(fid, "%s\n", text);
fclose(fid);
end

function repoRoot = repo_root_from_this_file()
thisFile = mfilename("fullpath");
repoRoot = fileparts(fileparts(thisFile));
end
