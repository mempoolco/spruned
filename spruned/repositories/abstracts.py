from enum import Enum
from typing import Dict, List
import abc


class BlockchainRepositoryAbstract(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    def set_cache(self, cache):
        pass

    @staticmethod
    @abc.abstractmethod
    def _get_key(name: (bytes, str), prefix: Enum):
        pass

    @abc.abstractmethod
    async def save_block(self, block: Dict, tracker=None) -> Dict:
        pass

    @abc.abstractmethod
    async def save_blocks(self, *blocks: Dict) -> List[Dict]:
        pass

    @abc.abstractmethod
    async def _save_transaction(self, transaction: Dict) -> Dict:
        pass

    @abc.abstractmethod
    async def get_transaction(self, txid) -> (None, Dict):
        pass

    @abc.abstractmethod
    async def remove_block(self, blockhash: str):
        pass
