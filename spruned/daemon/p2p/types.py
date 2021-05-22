from dataclasses import dataclass

from spruned.daemon.abstracts import ConnectionAbstract
from spruned.dependencies.pycoinnet.pycoin.inv_item import InvItem


@dataclass
class P2PInvItemResponse:
    response: InvItem
    connection: ConnectionAbstract
