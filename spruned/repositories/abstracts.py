from typing import Dict, List
import abc


class BlockchainRepositoryAbstract(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def set_cache(self, cache):
        pass

    @abc.abstractmethod
    def get_key(self, name: str, prefix=b''):
        pass

    @abc.abstractmethod
    async def async_save_block(self, block: Dict, tracker=None, callback=None):
        pass

    @abc.abstractmethod
    def save_block(self, block: Dict, tracker=None) -> Dict:
        pass

    @abc.abstractmethod
    def save_blocks(self, *blocks: Dict) -> List[Dict]:
        pass

    @abc.abstractmethod
    def save_transaction(self, transaction: Dict) -> Dict:
        pass

    @abc.abstractmethod
    def get_transaction(self, txid) -> (None, Dict):
        pass

    @abc.abstractmethod
    def remove_block(self, blockhash: str):
        pass
