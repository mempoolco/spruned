from typing import List, Dict
from sqlalchemy.exc import IntegrityError
from spruned.application.abstracts import HeadersRepository
from spruned.application.logging_factory import Logger
from spruned.application.storage import StorageFileInterface
from spruned.daemon import exceptions
from spruned.application import database


class BlocksRepository(StorageFileInterface):
    def __init__(self, storage_directory):
        super().__init__(storage_directory + 'blocks', compress=False)

    def save_blocks(self, *blocks):
        Logger.repository.debug('fake save_blocks: %s', len(blocks))
        return blocks

    def get_block(self, blockhash: str):
        return
