from spruned.application import settings
from spruned.services.http_client import HTTPClient
from spruned.services.insight_service import InsightService


class BlockexplorerService(InsightService):
    def __init__(self, coin, httpclient=HTTPClient, utxo_tracker=None):
        assert coin == settings.Network.BITCOIN
        self.client = httpclient(baseurl='https://blockexplorer.com/api/')
        self.throttling_error_codes = []
        self.utxo_tracker = utxo_tracker
