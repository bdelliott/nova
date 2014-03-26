# Copyright (c) 2014 Rackspace Hosting
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


from nova import memutils
from nova import test


class _Foo(object):
    def __init__(self):
        self.abc = 0

    def foo(self, x, y=1):
        # alloc some memory
        l = range(500000)
        return x, y, len(l)


class MemoryUtilsTestCase(test.NoDBTestCase):

    def test_memwrap(self):
        f = _Foo()
        f = memutils.MemWrap(f)

        self.assertEqual(0, f.abc)

        # sample memory
        mem1 = memutils.maxmem()

        # alloc memory
        x, y, sz = f.foo(1, y=2)

        # mem usage should have gone up.
        mem2 = memutils.maxmem()
        self.assertTrue(mem2 > mem1)

        # also verify the plumbing
        self.assertEqual(1, x)
        self.assertEqual(2, y)
