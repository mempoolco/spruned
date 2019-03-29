from unittest import TestCase

from spruned.application.jsonrpc_server import JSONRPCServer


class TestFormatter(TestCase):
    def test_1(self):
        payload = {
            'error': None,
            'jsonrpc': '2.0',
            'id': 1,
            'result': {
                'bestblock': '000000000000000000084b9258ca7c4bed889bf07e2bbcb839e509b0ce2d8fc4',
                'value': "0.00020000",
                'confirmations': 481,
                'scriptPubKey': {
                    'addresses': [],
                    'hex': '002023df98f8eada1ba8d57c06f311e33cd5dbb4fd875c8887e04e81688c527d5902',
                    'reqSigs': 0,
                    'asm': '',
                    'type': ''
                }
            }
        }
        res = JSONRPCServer._json_dumps_with_fixed_float_precision(payload)
        self.assertTrue('"jsonrpc": "2.0"' in res)
        self.assertTrue('"value": 0.00020000' in res)

    def test_2(self):
        payload = {
            "value": "{:.8f}".format(0.00002342),
            "feerate": "{:.8f}".format(0.00000022),
            "jsonrpc": "2.0"
        }
        res = JSONRPCServer._json_dumps_with_fixed_float_precision(payload)
        self.assertTrue(
            all([
                '"value": 0.00002342' in res,
                '"feerate": 0.00000022' in res,
                '"jsonrpc": "2.0"' in res
                ])
        )
