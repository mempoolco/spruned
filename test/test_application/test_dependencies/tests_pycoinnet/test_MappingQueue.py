import asyncio
import unittest

from spruned.dependencies.pycoinnet.MappingQueue import MappingQueue


async def flatten_callback(items, output_q):
    for item in items:
        await output_q.put(item)


class MappingQueueTest(unittest.TestCase):

    def test_pipeline(self):
        loop = asyncio.get_event_loop()
        results = []

        async def callback_f(item, q):
            await q.put(item)
            results.append(item)

        q = MappingQueue({"callback_f": callback_f})

        async def go(q):
            await q.put(5)
            await q.put(4)
            await q.put(3)
            q.stop()
            await q.wait()

        loop.run_until_complete(go(q))
        self.assertEqual(results, [5, 4, 3])

    def test_asyncmap(self):

        def make_async_transformation_f(results):
            async def async_transformation_f(item, q):
                await q.put(item)
                results.append(item)
            return async_transformation_f

        def sync_transformation_f(item, q):
            pass

        async def go(q):
            await q.put(5)
            await q.put(4)
            await q.put(3)
            q.stop()
            await q.wait()

        loop = asyncio.get_event_loop()

        results = []
        loop.run_until_complete(go(MappingQueue({"callback_f": make_async_transformation_f(results), "worker_count": 1})))
        self.assertEqual(results, [5, 4, 3])

        results = []
        loop.run_until_complete(go(MappingQueue({"callback_f": make_async_transformation_f(results), "worker_count": 1})))
        self.assertEqual(results, [5, 4, 3])

        self.assertRaises(ValueError, lambda: MappingQueue(
            {"callback_f": sync_transformation_f, "worker_count": 1}))

    def test_make_flattener(self):
        loop = asyncio.get_event_loop()

        async def go(q):
            r = []
            await q.put([0, 1, 2, 3])
            for _ in range(3):
                r.append(await q.get())
            await q.put([4, 5, 6, 7])
            for _ in range(5):
                r.append(await q.get())
            q.stop()
            await q.wait()
            return r

        r = loop.run_until_complete(go(MappingQueue({"callback_f": flatten_callback})))
        self.assertEqual(r, list(range(8)))

    def test_make_pipe(self):
        loop = asyncio.get_event_loop()

        async def map_f(x, q):
            await asyncio.sleep(x / 10.0)
            await q.put(x * x)

        async def go(q):
            r = []
            for _ in range(4):
                await q.put(_)
            for _ in range(3, 9):
                await q.put(_)
            for _ in range(10):
                r.append(await q.get())
            q.stop()
            await q.wait()
            return r

        r = loop.run_until_complete(go(MappingQueue(dict(callback_f=map_f))))
        r1 = sorted([_*_ for _ in range(4)] + [_ * _ for _ in range(3, 9)])
        self.assertEqual(r, r1)

    def test_make_simple_pipeline(self):
        loop = asyncio.get_event_loop()

        q = MappingQueue(
            dict(callback_f=flatten_callback),
            dict(callback_f=flatten_callback),
        )

        async def go(q):
            await q.put([
                (0, 0, 1, 0),
                (1, 1, 1, 1),
                (2, 0, 0, 1),
                (3, 1, 2, 0),
                (0, 0, 0, 7),
            ])
            r = []
            for _ in range(20):
                p = await q.get()
                r.append(p)
            q.stop()
            await q.wait()
            return r
        r = loop.run_until_complete(go(q))
        self.assertEqual(r, [0, 0, 1, 0, 1, 1, 1, 1, 2, 0, 0, 1, 3, 1, 2, 0, 0, 0, 0, 7])

    def test_make_delayed_pipeline(self):
        loop = asyncio.get_event_loop()

        def make_wait_index(idx):

            async def wait(item, q):
                await asyncio.sleep(item[idx] / 10.)
                await q.put(item)

            return wait

        q = MappingQueue(
            dict(callback_f=flatten_callback),
            dict(callback_f=make_wait_index(0), worker_count=10),
            dict(callback_f=make_wait_index(1), worker_count=10),
            dict(callback_f=make_wait_index(2), worker_count=10),
            dict(callback_f=make_wait_index(3), worker_count=10),
        )

        TEST_CASE = [
            (0, 0, 0, 7),
            (5, 0, 0, 0),
            (0, 0, 1, 0),
            (1, 1, 1, 1),
            (2, 0, 0, 1),
            (3, 1, 2, 0),
        ]

        async def go(case, q):
            await q.put(case)
            r = []
            for _ in range(len(case)):
                p = await q.get()
                r.append(p)
            q.stop()
            await q.wait()
            return r
        r = loop.run_until_complete(go(TEST_CASE, q))
        r1 = sorted(r, key=lambda x: sum(x))
        self.assertEqual(r, r1)

    def test_filter_pipeline(self):
        loop = asyncio.get_event_loop()

        async def filter(item_list_of_lists, q):
            for l1 in item_list_of_lists:
                for item in l1:
                    if item != 0:
                        await q.put(item)

        q = MappingQueue(
            dict(callback_f=filter),
        )

        TEST_CASE = [
            (0, 0, 0, 7),
            (5, 0, 0, 0),
            (0, 0, 1, 0),
            (1, 1, 1, 1),
            (2, 0, 0, 1),
            (3, 1, 2, 0),
        ]

        async def go(case, q):
            await q.put(case)
            r = []
            for _ in range(12):
                p = await q.get()
                r.append(p)
            q.stop()
            await q.wait()
            return r
        r = loop.run_until_complete(go(TEST_CASE, q))
        r1 = [7, 5, 1, 1, 1, 1, 1, 2, 1, 3, 1, 2]
        self.assertEqual(r, r1)
