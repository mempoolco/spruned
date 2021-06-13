from dataclasses import dataclass

import typing

from spruned.repositories.repository_types import Block


class FetchHeadersResponse(dict):
    pass


@dataclass
class DeserializedBlock:
    block: Block
    deserialized: typing.Dict
