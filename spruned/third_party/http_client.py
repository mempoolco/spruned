from requests import Session
import retrying


class HTTPClient:
    def __init__(self, baseurl):
        self.session = Session()
        self.baseurl = baseurl

    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=2)
    def get(self, *a, json_response=True, **kw):
        url = self.baseurl + a[0]
        response = self.session.get(url, **kw)
        response.raise_for_status()
        return response.json() if json_response else response.content

    @retrying.retry(wait_fixed=1000, stop_max_attempt_number=2)
    def post(self, *a, json_response=True, **kw):
        url = self.baseurl + a[0]
        response = self.session.post(url, **kw)
        response.raise_for_status()
        return response.json() if json_response else response.content

