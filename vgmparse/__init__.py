import gzip
import struct
import sys

if (sys.version_info > (3, 0)):
    from io import BytesIO as ByteBuffer
else:
    from StringIO import StringIO as ByteBuffer


class VersionError(Exception):
    pass


class Parser:
    # VGM file identifier
    vgm_magic_number = b'Vgm '

    # Supported VGM versions
    supported_ver_list = [
        0x00000101,
        0x00000150,
    ]

    # VGM metadata offsets
    metadata_offsets = {
        'vgm_ident': {'offset': 0x00, 'size': 4, 'type_format': None},
        'eof_offset': {'offset': 0x04, 'size': 4, 'type_format': '<I'},
        'version': {'offset': 0x08, 'size': 4, 'type_format': '<I'},
        'sn76489_clock': {'offset': 0x0c, 'size': 4, 'type_format': '<I'},
        'ym2413_clock': {'offset': 0x10, 'size': 4, 'type_format': '<I'},
        'gd3_offset': {'offset': 0x14, 'size': 4, 'type_format': '<I'},
        'total_samples': {'offset': 0x18, 'size': 4, 'type_format': '<I'},
        'loop_offset': {'offset': 0x1c, 'size': 4, 'type_format': '<I'},
        'loop_samples': {'offset': 0x20, 'size': 4, 'type_format': '<I'},
        'rate': {'offset': 0x24, 'size': 4, 'type_format': '<I'},
        'sn76489_feedback': {
            'offset': 0x28,
            'size': 2,
            'type_format': '<H',
        },
        'sn76489_shift_register_width': {
            'offset': 0x2a,
            'size': 1,
            'type_format': 'B',
        },
        'ym2612_clock': {'offset': 0x2c, 'size': 4, 'type_format': '<I'},
        'ym2151_clock': {'offset': 0x30, 'size': 4, 'type_format': '<I'},
        'vgm_data_offset': {
            'offset': 0x34,
            'size': 4,
            'type_format': '<I',
        },
    }

    def __init__(self, vgm_data):
        # Store the VGM data and validate it
        self.data = ByteBuffer(vgm_data)
        self.validate_vgm_data()

        # Set up the variables that will be populated
        self.command_list = []
        self.data_block = None
        self.gd3_data = {}
        self.metadata = {}

        # Parse the VGM metadata and validate the VGM version
        self.parse_metadata()
        self.validate_vgm_version()

        # Parse GD3 data and the VGM commands
        self.parse_gd3()
        self.parse_commands()

    def parse_commands(self):
        # Save the current position of the VGM data
        original_pos = self.data.tell()

        # Seek to the start of the VGM data
        self.data.seek(
            self.metadata['vgm_data_offset'] +
            self.metadata_offsets['vgm_data_offset']['offset']
        )

        while True:
            # Read a byte, this will be a VGM command, we will then make
            # decisions based on the given command
            command = self.data.read(1)

            # Break if we are at the end of the file
            if command == '':
                break

            # 0x4f dd - Game Gear PSG stereo, write dd to port 0x06
            # 0x50 dd - PSG (SN76489/SN76496) write value dd
            if command in [b'\x4f', b'\x50']:
                self.command_list.append({
                    'command': command,
                    'data': self.data.read(1),
                })

            # 0x51 aa dd - YM2413, write value dd to register aa
            # 0x52 aa dd - YM2612 port 0, write value dd to register aa
            # 0x53 aa dd - YM2612 port 1, write value dd to register aa
            # 0x54 aa dd - YM2151, write value dd to register aa
            elif command in [b'\x51', b'\x52', b'\x53', b'\x54']:
                self.command_list.append({
                    'command': command,
                    'data': self.data.read(2),
                })

            # 0x61 nn nn - Wait n samples, n can range from 0 to 65535
            elif command == b'\x61':
                self.command_list.append({
                    'command': command,
                    'data': self.data.read(2),
                })

            # 0x62 - Wait 735 samples (60th of a second)
            # 0x63 - Wait 882 samples (50th of a second)
            # 0x66 - End of sound data
            elif command in [b'\x62', b'\x63', b'\x66']:
                self.command_list.append({'command': command, 'data': None})

                # Stop processing commands if we are at the end of the music
                # data
                if command == b'\x66':
                    break

            # 0x67 0x66 tt ss ss ss ss - Data block
            elif command == b'\x67':
                # Skip the compatibility and type bytes (0x66 tt)
                self.data.seek(2, 1)

                # Read the size of the data block
                data_block_size = struct.unpack('<I', self.data.read(4))[0]

                # Store the data block for later use
                self.data_block = ByteBuffer(self.data.read(data_block_size))

            # 0x7n - Wait n+1 samples, n can range from 0 to 15
            # 0x8n - YM2612 port 0 address 2A write from the data bank, then
            #        wait n samples; n can range from 0 to 15
            elif b'\x70' <= command <= b'\x8f':
                self.command_list.append({'command': command, 'data': None})

            # 0xe0 dddddddd - Seek to offset dddddddd (Intel byte order) in PCM
            #                 data bank
            elif command == b'\xe0':
                self.command_list.append({
                    'command': command,
                    'data': self.data.read(4),
                })

        # Seek back to the original position in the VGM data
        self.data.seek(original_pos)

    def parse_gd3(self):
        # Save the current position of the VGM data
        original_pos = self.data.tell()

        # Seek to the start of the GD3 data
        self.data.seek(
            self.metadata['gd3_offset'] +
            self.metadata_offsets['gd3_offset']['offset']
        )

        # Skip 8 bytes ('Gd3 ' string and 4 byte version identifier)
        self.data.seek(8, 1)

        # Get the length of the GD3 data, then read it
        gd3_length = struct.unpack('<I', self.data.read(4))[0]
        gd3_data = ByteBuffer(self.data.read(gd3_length))

        # Parse the GD3 data
        gd3_fields = []
        current_field = b''
        while True:
            # Read two bytes. All characters (English and Japanese) in the GD3
            # data use two byte encoding
            char = gd3_data.read(2)

            # Break if we are at the end of the GD3 data
            if char == b'':
                break

            # Check if we are at the end of a field, if not then continue to
            # append to "current_field"
            if char == b'\x00\x00':
                gd3_fields.append(current_field)
                current_field = b''
            else:
                current_field += char

        # Once all the fields have been parsed, create a dict with the data
        self.gd3_data = {
            'title_eng': gd3_fields[0],
            'title_jap': gd3_fields[1],
            'game_eng': gd3_fields[2],
            'game_jap': gd3_fields[3],
            'console_eng': gd3_fields[4],
            'console_jap': gd3_fields[5],
            'artist_eng': gd3_fields[6],
            'artist_jap': gd3_fields[7],
            'date': gd3_fields[8],
            'vgm_creator': gd3_fields[9],
            'notes': gd3_fields[10],
        }

        # Seek back to the original position in the VGM data
        self.data.seek(original_pos)

    def parse_metadata(self):
        # Save the current position of the VGM data
        original_pos = self.data.tell()

        # Create the list to store the VGM metadata
        self.metadata = {}

        # Iterate over the offsets and parse the metadata
        for value, offset_data in self.metadata_offsets.items():

            # Seek to the data location and read the data
            self.data.seek(offset_data['offset'])
            data = self.data.read(offset_data['size'])

            # Unpack the data if required
            if offset_data['type_format'] is not None:
                self.metadata[value] = struct.unpack(
                    offset_data['type_format'],
                    data,
                )[0]
            else:
                self.metadata[value] = data

        # Seek back to the original position in the VGM data
        self.data.seek(original_pos)

    def validate_vgm_data(self):
        # Save the current position of the VGM data
        original_pos = self.data.tell()

        # Seek to the start of the file
        self.data.seek(0)

        # Perform basic validation on the given file by checking for the VGM
        # magic number ('Vgm ')
        if self.data.read(4) != self.vgm_magic_number:
            # Could not find the magic number. The file could be gzipped (e.g.
            # a vgz file). Try un-gzipping the file and trying again.
            self.data.seek(0)
            self.data = gzip.GzipFile(fileobj=self.data, mode='rb')

            try:
                if self.data.read(4) != self.vgm_magic_number:
                    raise ValueError('Data does not appear to be a valid VGM file')
            except IOError:
                # IOError will be raised if the file is not a valid gzip file
                raise ValueError('Data does not appear to be a valid VGM file')

        # Seek back to the original position in the VGM data
        self.data.seek(original_pos)

    def validate_vgm_version(self):
        if self.metadata['version'] not in self.supported_ver_list:
            raise VersionError('VGM version %s is not supported' % self.version_str())
        
    def version_str(self):
        version = self.metadata['version']
        return '%01x.%02x' % (version >> 8, version & 0xFF)
    
    def save(self, buffer):
        # Pre-fill the header with zeroes
        buffer.seek(0)
        buffer.write(b'\0' * 0x40)

        # Iterate over the offsets and write the metadata
        for value, offset_data in self.metadata_offsets.items():

            # Seek to the data location and read the data
            buffer.seek(offset_data['offset'])

            # Unpack the data if required
            if offset_data['type_format'] is not None:
                data = struct.pack(
                    offset_data['type_format'],
                    self.metadata[value],
                )
                buffer.write(data)
            else:
                buffer.write(self.metadata[value])
                
        # Write out the commands
        for cmd in self.command_list:
            buffer.write(cmd['command'])
            if cmd['data']:
                buffer.write(cmd['data']) 
        