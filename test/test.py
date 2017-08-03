import unittest
import vgmparse
import tempfile, time

class TestParsing(unittest.TestCase):
    
    def test_vgm_1_01(self):
        with open('Alex Kidd in Miracle World - 01 - Title Screen.vgm', 'rb') as f:
            file_data = f.read()
            parser = vgmparse.Parser(file_data)
            
            # The first command is a GG Stereo command
            self.assertEqual(0x4F, ord(parser.command_list[0]['command']))
            self.assertEqual(0xFF, ord(parser.command_list[0]['data']))
            
            # The second command is a SN76496 Latch/Data command
            self.assertEqual(0x50, ord(parser.command_list[1]['command']))
            self.assertEqual(0x80, ord(parser.command_list[1]['data']))
            
    def test_save(self):
        with open('Alex Kidd in Miracle World - 01 - Title Screen.vgm', 'rb') as f:
            file_data = f.read()
            parser = vgmparse.Parser(file_data)
            
            with open('{0}/test-save-{1}.vgm'.format(tempfile.gettempdir(), time.time()), 'wb') as o:
                parser.save(o)
        
if __name__ == '__main__':
    unittest.main()