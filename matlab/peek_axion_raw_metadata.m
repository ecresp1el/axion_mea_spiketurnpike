function info = peek_axion_raw_metadata(rawFile)
%PEEK_AXION_RAW_METADATA Read Axion raw metadata without constructing datasets.
%
% This uses AxionFileLoader classes for headers, channel arrays, tags, plate
% maps, and combined block metadata, but deliberately skips data payloads and
% does not build loadable DataSet objects.

arguments
    rawFile (1, 1) string
end

MAGIC_WORD = 'AxionBio';
EXPECTED_NOTES_LENGTH_FIELD = 600;
PRIMARY_HEADER_CRCSIZE = 1018;
SUBHEADER_CRCSIZE = 1016;
PRIMARY_HEADER_MAXENTRIES = 123;
SUBHEADER_MAXENTRIES = 126;
CRC_POLYNOMIAL = hex2dec('edb88320');
CRC_SEED = hex2dec('ffffffff');

fid = fopen(rawFile, 'r');
if fid <= 0
    error("Could not open raw file: %s", rawFile);
end
cleanup = onCleanup(@() fclose(fid));

info = struct( ...
    "axis_filename", rawFile, ...
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
    "metadata_barcode", "", ...
    "metadata_biocore_version", "", ...
    "metadata_keys", "");

magicRead = fread(fid, length(MAGIC_WORD), '*char').';
if ~strcmp(MAGIC_WORD, magicRead)
    error("File format not recognized: %s", rawFile);
end

info.primary_data_type = double(fread(fid, 1, 'uint16=>uint16'));
info.header_version_major = double(fread(fid, 1, 'uint16=>uint16'));
info.header_version_minor = double(fread(fid, 1, 'uint16=>uint16'));
notesStart = fread(fid, 1, 'uint64=>uint64');
notesLength = fread(fid, 1, 'uint32=>uint32');

if notesLength ~= EXPECTED_NOTES_LENGTH_FIELD
    error("Incorrect legacy notes length field");
end

if info.header_version_major ~= 1
    error("Unsupported metadata peep for AxIS file version %u.%u", ...
        info.header_version_major, info.header_version_minor);
end

entriesStart = fread(fid, 1, 'int64=>int64');
entrySlots = fread(fid, PRIMARY_HEADER_MAXENTRIES, 'uint64=>uint64');
entryRecords = EntryRecord.FromUint64(entrySlots);

fseek(fid, 0, 'bof');
crcBytes = fread(fid, PRIMARY_HEADER_CRCSIZE, 'uint8');
readCrc = fread(fid, 1, 'uint32');
calcCrc = CRC32(CRC_POLYNOMIAL, CRC_SEED).Compute(crcBytes);
if readCrc ~= calcCrc
    error("File header checksum was incorrect: %s", rawFile);
end

fseek(fid, entriesStart, 'bof');
terminated = false;
tagEntries = TagEntry.empty(0);
notes = Note.empty(0, 0);
channelArray = [];
combinedHeaders = CombinedBlockVectorHeaderEntry.empty(0, 1);

while ~terminated
    for entryRecord = entryRecords
        entryStart = ftell(fid);
        entryLength = double(entryRecord.Length);

        if isinf(entryLength)
            fseek(fid, 0, 'eof');
            terminated = true;
            break
        end

        entryEnd = entryStart + entryLength;

        switch entryRecord.Type
            case EntryRecordID.Terminate
                terminated = true;
                break

            case EntryRecordID.ChannelArray
                channelArray = ChannelArray(entryRecord, fid);

            case EntryRecordID.NotesArray
                notes = [notes; Note.ParseArray(entryRecord, fid)]; %#ok<AGROW>

            case EntryRecordID.Tag
                tagEntries(end + 1) = TagEntry(entryRecord, fid); %#ok<AGROW>

            case EntryRecordID.CombinedBlockVectorHeader
                combinedHeader = CombinedBlockVectorHeaderEntry.Deserialize(entryRecord, fid);
                combinedHeaders(end + 1) = combinedHeader; %#ok<AGROW>

            otherwise
                % Metadata peep only: skip block data and unsupported entries.
        end

        currentPos = ftell(fid);
        if currentPos < entryEnd
            fseek(fid, entryEnd, 'bof');
        elseif currentPos > entryEnd
            warning( ...
                'AxionMetadataPeep:EntryOverRead', ...
                'Entry parser read past expected entry boundary. Continuing at current position.');
        end
    end

    if ~terminated
        magicRead = fread(fid, length(MAGIC_WORD), '*char').';
        if ~strcmp(MAGIC_WORD, magicRead)
            error("Bad sub header magic numbers: %s", rawFile);
        end

        entrySlots = fread(fid, SUBHEADER_MAXENTRIES, 'uint64=>uint64');
        entryRecords = EntryRecord.FromUint64(entrySlots);

        fseek(fid, (-1 * length(MAGIC_WORD)) - (8 * SUBHEADER_MAXENTRIES), 'cof');
        crcBytes = fread(fid, SUBHEADER_CRCSIZE, 'uint8');
        readCrc = fread(fid, 1, 'uint32');
        calcCrc = CRC32(CRC_POLYNOMIAL, CRC_SEED).Compute(crcBytes);
        if readCrc ~= calcCrc
            error("Bad sub header checksum: %s", rawFile);
        end

        fseek(fid, 4, 'cof');
    end
end

if ~isempty(channelArray)
    info.num_channels = numel(channelArray.Channels);
    info.plate_type_id = double(channelArray.PlateType);
    info.plate_type_name = plate_type_name(channelArray.PlateType);
    info.well_dimensions = mat2str(PlateTypes.GetWellDimensions(channelArray.PlateType));
    info.electrode_dimensions = mat2str(PlateTypes.GetElectrodeDimensions(channelArray.PlateType));
end

info.num_datasets = numel(combinedHeaders);
if ~isempty(combinedHeaders)
    combinedHeader = combinedHeaders(1);
    info.dataset_class = "CombinedBlockVectorHeaderEntry";
    info.dataset_name = string_or_empty(combinedHeader.Name);
    info.dataset_description = string_or_empty(combinedHeader.Description);
    info.sampling_frequency_hz = double(combinedHeader.SamplingFrequency);
    info.voltage_scale_v_per_sample = double(combinedHeader.VoltageScale);
    info.block_vector_start_time = datetime_string(combinedHeader.BlockVectorStartTime);
    info.experiment_start_time = datetime_string(combinedHeader.ExperimentStartTime);
    info.added_date = datetime_string(combinedHeader.AddedDate);
    info.modified_date = datetime_string(combinedHeader.ModifiedDate);
    info.sample_type = double(combinedHeader.SampleType);
    info.num_channels_per_block = double(combinedHeader.NumChannelsPerBlock);
    info.num_samples_per_block = double(combinedHeader.NumSamplesPerBlock);
    info.data_region_start = double(combinedHeader.DataRegionStart);
    info.data_region_length = double(combinedHeader.DataRegionLength);
    if ~isempty(combinedHeader.Duration)
        info.duration_s = double(combinedHeader.Duration);
    end
end

[metadata, plateMapCount] = promote_tags(fid, tagEntries);
if metadata.Count == 0 && ~isempty(notes)
    [~, idx] = sort([notes.Revision]);
    notes = notes(idx);
    metadata("RecordingName") = notes(end).RecordingName;
    metadata("Investigator") = notes(end).Investigator;
    metadata("Description") = notes(end).Description;
end

info.num_plate_map_entries = plateMapCount;
info.metadata_recording_name = metadata_value(metadata, "RecordingName");
info.metadata_description = metadata_value(metadata, "Description");
info.metadata_investigator = metadata_value(metadata, "Investigator");
info.metadata_analog_mode = metadata_value(metadata, "AnalogMode");
info.metadata_barcode = metadata_value(metadata, "Barcode");
info.metadata_biocore_version = metadata_value(metadata, "BioCoreVersion");
info.metadata_keys = strjoin(string(keys(metadata)), ";");
end

function [metadata, plateMapCount] = promote_tags(fid, tagEntries)
metadata = containers.Map('KeyType', 'char', 'ValueType', 'char');
plateMapCount = 0;
tagMap = containers.Map();

for idx = 1:length(tagEntries)
    tagEntry = tagEntries(idx);
    tagGuid = tagEntry.TagGuid;
    if tagMap.isKey(tagGuid)
        tag = tagMap(tagGuid);
    else
        tag = Tag(tagGuid);
        tagMap(tagGuid) = tag;
    end
    tag.AddNode(tagEntry);
end

for key = tagMap.keys
    tagKey = key{1};
    promotedTag = tagMap(tagKey).Promote(fid);
    if isa(promotedTag, 'WellInformation')
        plateMapCount = plateMapCount + 1;
    elseif isa(promotedTag, 'KeyValuePairTag')
        metadata(promotedTag.Key) = promotedTag.Value;
    end
end
end

function value = metadata_value(metadata, key)
if isKey(metadata, key)
    value = string(metadata(key));
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
