from spruned.application.tools import serialize_header


def serialize_verbose_block(rawblock: dict):
    block = {}
    header = serialize_header(rawblock['header_bytes'])

