import unittest
import vgmparse

class TestParsing(unittest.TestCase):
    
    def test_vgm_1_01(self):
        with open('Alex Kidd in Miracle World - 01 - Title Screen.vgm', 'rb') as f:
            file_data = f.read()
            parser = vgmparse.Parser(file_data)
        
if __name__ == '__main__':
    unittest.main()