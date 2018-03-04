from spruned.application import settings
from spruned.services.http_client import HTTPClient
from spruned.services.insight_service import InsightService


class BlockexplorerService(InsightService):
    def __init__(self, coin, httpclient=HTTPClient, utxo_tracker=None):
        assert coin == settings.Network.BITCOIN
        self.client = httpclient(baseurl='https://blockexplorer.com/api/')
        self.throttling_error_codes = []
        self.utxo_tracker = utxo_tracker


if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    api = BlockexplorerService(settings.NETWORK)
    print(loop.run_until_complete(api.gettxout('8e4c29e2c37a1107f732492a94a94197bbbc6f93aa97b7b3e58852d42680b923', 0)))
