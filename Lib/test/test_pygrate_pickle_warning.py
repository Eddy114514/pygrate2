import unittest, warnings, pickle, base64, sys

class TestPickleDumpsWarning(unittest.TestCase):
    def test_pickle_dumps_warn(self):
        warnings.simplefilter('always', UserWarning)
        with warnings.catch_warnings(record=True) as w:
            w[:] = []
            b = pickle.dumps('test')
            self.assertTrue(any('PYGRATE2' in str(x.message) for x in w))
            self.assertIsInstance(b, str)
            self.assertIsInstance(base64.b64encode(b), str)

if __name__ == '__main__':
    unittest.main()