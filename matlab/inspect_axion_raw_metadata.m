function metadataTable = inspect_axion_raw_metadata(sourceRoot, outputCsv, axionLoaderRoot)
%INSPECT_AXION_RAW_METADATA Inventory Axion .raw files using MATLAB metadata peep.
%
% metadataTable = inspect_axion_raw_metadata(sourceRoot, outputCsv, axionLoaderRoot)
%
% This function intentionally reads metadata through MATLAB AxionFileLoader
% classes. It does not copy raw files, parse derived CSV exports, construct
% loadable DataSet objects, or load continuous voltage traces into memory.

arguments
    sourceRoot (1, 1) string
    outputCsv (1, 1) string = ""
    axionLoaderRoot (1, 1) string = "/nfs/turbo/umms-parent/MannyAxionMEAscripts_v1/AxionFileLoader-main"
end

addpath(genpath(axionLoaderRoot), "-end");
addpath(fullfile(repo_root_from_this_file(), "matlab", "axionfileloader_overrides"), "-begin");

if isfile(sourceRoot)
    rawFiles = dir(sourceRoot);
else
    rawFiles = dir(fullfile(sourceRoot, "**", "*.raw"));
end
rawFiles = rawFiles(~startsWith(string({rawFiles.name}), "._"));

rows = struct([]);
for idx = 1:numel(rawFiles)
    rawPath = string(fullfile(rawFiles(idx).folder, rawFiles(idx).name));
    fprintf("Inspecting raw metadata %d/%d: %s\n", idx, numel(rawFiles), rawPath);

    clear metadataInfo
    row = empty_row();
    row.source_root = sourceRoot;
    row.source_dir = string(rawFiles(idx).folder);
    row.raw_file = rawPath;
    row.raw_name = string(rawFiles(idx).name);
    row.raw_size_bytes = rawFiles(idx).bytes;
    row.raw_file_kind = raw_file_kind(rawFiles(idx).name);
    row.recording_stem = recording_stem_from_raw(rawFiles(idx).name);

    try
        metadataInfo = peek_axion_raw_metadata(rawPath);
        metadataFields = fieldnames(metadataInfo);
        for fieldIdx = 1:numel(metadataFields)
            fieldName = metadataFields{fieldIdx};
            row.(fieldName) = metadataInfo.(fieldName);
        end

    catch ME
        row.status = "error";
        row.error_message = string(ME.message);
    end

    clear metadataInfo

    if row.status == ""
        row.status = "ok";
    end

    rows = [rows; row]; %#ok<AGROW>
end

metadataTable = struct2table(rows);
if strlength(outputCsv) > 0
    outputDir = fileparts(outputCsv);
    if strlength(outputDir) > 0 && ~isfolder(outputDir)
        mkdir(outputDir);
    end
    writetable(metadataTable, outputCsv);
    fprintf("Wrote MATLAB raw metadata inventory: %s\n", outputCsv);
end
end

function row = empty_row()
row = struct( ...
    "status", "", ...
    "error_message", "", ...
    "source_root", "", ...
    "source_dir", "", ...
    "raw_file", "", ...
    "raw_name", "", ...
    "raw_file_kind", "", ...
    "recording_stem", "", ...
    "raw_size_bytes", 0, ...
    "axis_filename", "", ...
    "primary_data_type", NaN, ...
    "header_version_major", NaN, ...
    "header_version_minor", NaN, ...
    "num_datasets", NaN, ...
    "num_plate_map_entries", NaN, ...
    "num_channels", NaN, ...
    "plate_type_id", NaN, ...
    "plate_type_name", "", ...
    "well_dimensions", "", ...
    "electrode_dimensions", "", ...
    "dataset_class", "", ...
    "dataset_name", "", ...
    "dataset_description", "", ...
    "sampling_frequency_hz", NaN, ...
    "voltage_scale_v_per_sample", NaN, ...
    "block_vector_start_time", "", ...
    "experiment_start_time", "", ...
    "added_date", "", ...
    "modified_date", "", ...
    "sample_type", NaN, ...
    "num_channels_per_block", NaN, ...
    "num_samples_per_block", NaN, ...
    "data_region_start", NaN, ...
    "data_region_length", NaN, ...
    "duration_s", NaN, ...
    "metadata_recording_name", "", ...
    "metadata_description", "", ...
    "metadata_investigator", "", ...
    "metadata_analog_mode", "", ...
    "metadata_high_pass_filter", "", ...
    "metadata_high_pass_cutoff", "", ...
    "metadata_low_pass_filter", "", ...
    "metadata_low_pass_cutoff", "", ...
    "metadata_axis_version", "", ...
    "metadata_instrument", "", ...
    "metadata_firmware_version", "", ...
    "metadata_barcode", "", ...
    "metadata_biocore_version", "", ...
    "block_vector_warning_seen", false, ...
    "block_vector_warning_ids", "", ...
    "block_vector_warning_messages", "", ...
    "metadata_keys", "");
end

function kind = raw_file_kind(name)
if endsWith(string(name), "_BroadbandProcessor.raw")
    kind = "broadband_processor_raw";
else
    kind = "primary_raw";
end
end

function stem = recording_stem_from_raw(name)
stem = string(name);
stem = erase(stem, "_BroadbandProcessor.raw");
stem = erase(stem, ".raw");
end

function value = metadata_value(axisFile, key)
if isKey(axisFile.MetaData, key)
    value = string(axisFile.MetaData(key));
else
    value = "";
end
end

function value = string_or_empty(inputValue)
if isempty(inputValue)
    value = "";
else
    value = string(inputValue);
end
end

function value = datetime_string(inputValue)
if isempty(inputValue)
    value = "";
else
    value = string(inputValue.ToDateTimeString());
end
end

function name = plate_type_name(plateType)
plateType = uint32(plateType);
if plateType == PlateTypes.SixWell
    name = "SixWell";
elseif plateType == PlateTypes.TwentyFourWell
    name = "TwentyFourWell";
elseif plateType == PlateTypes.TwentyFourWellLumos
    name = "TwentyFourWellLumos";
elseif plateType == PlateTypes.FortyEightWell
    name = "FortyEightWell";
elseif plateType == PlateTypes.FortyEightWellTransparent
    name = "FortyEightWellTransparent";
elseif plateType == PlateTypes.FortyEightWellLumos
    name = "FortyEightWellLumos";
elseif plateType == PlateTypes.FortyEightWellOrganoid
    name = "FortyEightWellOrganoid";
elseif plateType == PlateTypes.NinetySixWell
    name = "NinetySixWell";
elseif plateType == PlateTypes.NinetySixWellLumos
    name = "NinetySixWellLumos";
else
    name = "Unknown";
end
end

function repoRoot = repo_root_from_this_file()
thisFile = mfilename("fullpath");
repoRoot = fileparts(fileparts(thisFile));
end
