class HeadersSQLiteRepository:
    def __init__(self):
        pass

    def get_best_height(self):
        pass

    def get_best_hash(self):
        pass

    def get_header_at_height(self, height: int):
        pass

    def get_header_for_hash(self, blockhash: str):
        pass

    def save_header(self, data: dict):
        pass

    def delete_headers_from_height(self, height: int):
        pass
