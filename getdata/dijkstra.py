import collections
import requests
import heapq
import math

from .globals import SPARK_TOKEN, SPARK_URL

Route = collections.namedtuple("Route", "price chan_fee_abs chan_fee_rel path")


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

    def neighbors(self, node, price):
        for v in self._neighbors[node]:
            if v[1] * 0.99 > price:
                yield v
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
                channel["satoshis"],
                channel["base_fee_millisatoshi"],
                channel["fee_per_millionth"],
            )
            graph._neighbors[channel["source"]].add(chandef)

        return graph

    def dijkstra(self, origin, destination, msatoshi):
        routes = Heap()
        for neighbor, _, base, ppm in self.neighbors(origin, msatoshi):
            chan_fee_abs = base
            chan_fee_rel = ppm * msatoshi / 1000000
            price = msatoshi + chan_fee_abs + chan_fee_rel
            routes.push(
                Route(
                    price=price,
                    chan_fee_abs=chan_fee_abs,
                    chan_fee_rel=chan_fee_rel,
                    path=[origin, neighbor],
                )
            )

        visited = set()
        visited.add(origin)

        while routes:
            # find the nearest yet-to-visit node
            price, chan_fee_abs, chan_fee_rel, path = routes.pop()

            node = path[-1]
            if node in visited:
                continue

            # we have arrived! wo-hoo!
            if node == destination:
                return price, chan_fee_abs, chan_fee_rel, path

            # tentative distances to all the unvisited neighbors
            for neighbor, _, base, ppm in self.neighbors(node, price):
                if neighbor not in visited:
                    # Total spent so far plus the price of getting there
                    cur_chan_fee_abs = base
                    cur_chan_fee_rel = ppm * price / 1000000
                    new_price = price + cur_chan_fee_abs + cur_chan_fee_rel
                    new_chan_fee_abs = chan_fee_abs + cur_chan_fee_abs
                    new_chan_fee_rel = chan_fee_rel + cur_chan_fee_rel
                    new_path = path + [neighbor]
                    routes.push(
                        Route(
                            price=new_price,
                            chan_fee_abs=new_chan_fee_abs,
                            chan_fee_rel=new_chan_fee_rel,
                            path=new_path,
                        )
                    )

            visited.add(node)

        return math.inf, math.inf, math.inf, None
