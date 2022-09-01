import time
import requests
from prometheus_client.core import GaugeMetricFamily, REGISTRY
from prometheus_client import start_http_server
import yaml, json

def print_headers(headers):
    print("HTTP Headers START")
    print('\r\n'.join('{}:{}'.format(k, v) for k, v in headers.items()),)
    print("HTTP Headers END")


class Config(object):
    def __init__(self, file):
        self.file = file
        try:
            with open(self.file, 'r') as file:
                self.config = yaml.safe_load(file)
        except FileNotFoundError as e:
            print('Error: {}', e)


class DockerHubCollector(object):

    """
    Initiate an DockerHubCollector object by using the following arguments :
    - verbose
    - username
    - password
    - repository
    """

    def __init__(self, verbose, username, password, repository):
        self.verbose = verbose
        self.username = username
        self.password = password
        self.repository = repository
    
        self.token_url = 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:' + self.repository + ':pull'
        
        self.registry_url = 'https://registry-1.docker.io/v2/' + self.repository + '/manifests/latest'


    def do_verbose(self, text):
        if self.verbose:
            print("Notice: " + text)


    # Extract Docker Hub Bearer token using username & password
    def get_token(self):

        if self.username and self.password:
            r_token = requests.get(self.token_url, auth=(self.username, self.password))

            self.do_verbose("Using Docker Hub credentials for '" + self.username + "'")
        else:
            r_token = requests.get(self.token_url)

            self.do_verbose("Using anonymous Docker Hub token")

        r_token.raise_for_status()

        resp_token = r_token.json()

        self.do_verbose("Response token:'" + json.dumps(resp_token) + "'")

        token = resp_token.get('token')

        if not token:
            raise Exception('Cannot obtain token from Docker Hub. Please try again!')

        return token

    # Extract ratelimit-limit, ratelimit-remaining & rateLimit-reset from Headers
    def limit_extractor(self, str_raw):
        self.do_verbose("Extracting limit from string " + str(str_raw))

        if ";" in str_raw:
            split_arr = str_raw.split(';')
            if len(split_arr) > 0:
                return split_arr[0]

            else:
                return str_raw

    # Extract Headers from DockerHub registry
    def get_registry_limits(self):
        headers_registry = {'Authorization': 'Bearer ' + self.get_token()}
        r_registry = requests.head(self.registry_url, headers=headers_registry)
        r_registry.raise_for_status()

        resp_headers = r_registry.headers
        if self.verbose:
            print_headers(resp_headers)

        limit = 0
        remaining = 0
        reset = 0

        # print(resp_headers)

        if "RateLimit-Limit" in resp_headers and "RateLimit-Remaining" in resp_headers:
            limit = self.limit_extractor(resp_headers["RateLimit-Limit"])
            remaining = self.limit_extractor(resp_headers["RateLimit-Remaining"])

        if "RateLimit-Reset" in resp_headers:
            reset = self.limit_extractor(resp_headers["RateLimit-Reset"])

        return limit, remaining, reset

    def collect(self):
        limit, remaining, reset = self.get_registry_limits()
        gr = GaugeMetricFamily("dockerhub_limit_remaining_requests_total",
                               'Docker Hub Rate Limit Remaining Requests', labels=['limit'])
        gr.add_metric(["remaining_requests_total"], remaining)

        yield gr

        gl = GaugeMetricFamily("dockerhub_limit_max_requests_total",
                               'Docker Hub Rate Limit Maximum Requests', labels=['limit'])
        gl.add_metric(["max_requests_total"], limit)

        yield gl


if __name__ == '__main__':

    values = Config('./config.yaml')
    port = values.config.get('config').get('DOCKERHUB_EXPORTER_PORT')

    if not port:
        port = 8881

    start_http_server(int(port))
    verbose = values.config.get('config').get('DOCKERHUB_EXPORTER_VERBOSE')
    if not verbose:
        verbose = False

    username = values.config.get('config').get('DOCKERHUB_USERNAME')
    password = values.config.get('config').get('DOCKERHUB_PASSWORD')
    repository = values.config.get('config').get('DOCKERHUB_EXPORTER_REPOSITORY')

    dhc = DockerHubCollector(bool(verbose), username, password, repository)

    REGISTRY.register(dhc)
    print("Starting exporter....")
    print(f'Listening on port : {port}')

    while True:
        time.sleep(5)
        dhc.collect()
