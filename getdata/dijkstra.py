import collections
import requests
import heapq

from .globals import SPARK_TOKEN, SPARK_URL

Route = collections.namedtuple("Route", "price path")


class Heap(object):
    def __init__(self):
        self._values = []

    def push(self, value):
        """Push the value item onto the heap."""
        heapq.heappush(self._values, value)

    def pop(self):
        """ Pop and return the smallest item from the heap."""
        return heapq.heappop(self._values)

    def __len__(self):
        return len(self._values)


class Graph(object):
    def __init__(self):
        # Map each node to a set of nodes connected to it
        self._neighbors = collections.defaultdict(set)

    def neighbors(self, node):
        yield from self._neighbors[node]

    @classmethod
    def load(cls):
        graph = cls()

        r = requests.post(
            SPARK_URL,
            headers={"X-Access": SPARK_TOKEN},
            json={"method": "listchannels"},
            verify=False,
        )
        for channel in r.json()["channels"]:
            chandef = (
                channel["destination"],
                channel["base_fee_millisatoshi"],
                channel["fee_per_millionth"],
            )
            graph._neighbors[channel["source"]].add(chandef)

        return graph

    def dijkstra(self, origin, destination, msatoshi):
        routes = Heap()
        for neighbor, base, ppm in self.neighbors(origin):
            chan_price = base + ppm * msatoshi / 1000000
            price = msatoshi + chan_price
            routes.push(Route(price=price, path=[origin, neighbor]))

        visited = set()
        visited.add(origin)

        while routes:
            # find the nearest yet-to-visit node
            price, path = routes.pop()

            node = path[-1]
            if node in visited:
                continue

            # we have arrived! wo-hoo!
            if node == destination:
                return price, path

            # tentative distances to all the unvisited neighbors
            for neighbor, base, ppm in self.neighbors(node):
                if neighbor not in visited:
                    # Total spent so far plus the price of getting there
                    chan_price = base + ppm * price / 1000000
                    new_price = price + chan_price
                    new_path = path + [neighbor]
                    routes.push(Route(new_price, new_path))

            visited.add(node)

        return float("infinity"), None
