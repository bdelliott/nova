import mock

from nova.api.openstack.compute.contrib import rax_services
from nova import test
from nova.tests.api.openstack import fakes


class TestRAXServicesController(test.TestCase):

    non_compute_service = {
        'disabled': False,
        'updated_at': None,
        'report_count': 123,
        'topic': 'not_compute',
        'host': 'c0001@non_compute_host',
        'href': 'http://test/v1/services/c0001@1',
        'id': 'c0001@1',
    }

    compute_service = {
        'topic': 'compute',
        'host': 'c0001@compute_host',
        'compute_node': [{
            'vcpus': 1,
            'memory_mb': 1024,
            'local_gb': 10,
            'vcpus_used': 1,
            'memory_mb_used': 123,
            'local_gb_used': 4,
            'cpu_info': '',
            'hypervisor_type': 'xen',
            'hypervisor_version': 6,
            'hypervisor_hostname': 'hypervisor_host',
        }],
        'id': 'c0001@2',
    }

    def setUp(self):
        super(TestRAXServicesController, self).setUp()
        self.flags(compute_api_class='nova.compute.cells_api.ComputeCellsAPI')

        # Fake/Mock Nova Context
        self.fake_context = mock.Mock()
        self.fake_context.read_deleted = "no"
        self.fake_context.project_id = "fake_project"

        # Fake/Mock WSGI Request
        self.fake_req = mock.MagicMock()
        self.fake_req.environ = {"nova.context": self.fake_context}
        self.fake_req.application_url = "http://test/v1"

        # Mock/Patch the cell_broadcast_call method
        sg_patch = mock.patch("nova.cells.rpcapi.CellsAPI.service_get")
        self.sg_mock = sg_patch.start()

        # Mock/Patch the cell_broadcast_call method
        sga_patch = mock.patch("nova.cells.rpcapi.CellsAPI.service_get_all")
        self.sga_mock = sga_patch.start()

        # Mock/Patch db.instance_get_all_by_host
        inst_get_all_patch = mock.patch('nova.compute.cells_api.HostAPI.'
                                      'instance_get_all_by_host')
        self.inst_get_all_mock = inst_get_all_patch.start()

        def _cleanup():
            sg_patch.stop()
            sga_patch.stop()
            inst_get_all_patch.stop()

        self.addCleanup(_cleanup)

        # Create controller to be used in each test
        self.controller = rax_services.ServicesController()

    def test_empty_index(self):
        """
        Test showing empty index of services.
        """
        self.sg_mock.return_value = []
        response = self.controller.index(self.fake_req)
        self.assertEqual({"services": []}, response)

    def test_index(self):
        """
        Test showing index of services.
        """
        self.sga_mock.return_value = [self.non_compute_service.copy()]
        response = self.controller.index(self.fake_req)

        expected = self.non_compute_service.copy()
        expected['id'] = 'c0001@1'

        self.assertEqual({"services": [expected]}, response)

    def test_show(self):
        """
        Test showing a single service.
        """
        self.sg_mock.return_value = self.non_compute_service.copy()
        response = self.controller.show(self.fake_req, "c0001@1")

        expected = self.non_compute_service.copy()
        expected['id'] = 'c0001@1'

        self.assertEqual({"service": expected}, response)

    def test_details_non_compute(self):
        """
        Test retrieving details on a non compute-type service.
        """
        self.sg_mock.return_value = self.non_compute_service.copy()
        response = self.controller.details(self.fake_req, "c0001@1")
        self.assertEqual({"details": {}}, response)

    def test_details_compute(self):
        """
        Test retrieving details on a compute-type service.
        """
        self.sg_mock.return_value = self.compute_service
        response = self.controller.details(self.fake_req, "c0001@2")

        expected = {
            'details': {
                'vcpus': 1,
                'memory_mb': 1024,
                'local_gb': 10,
                'vcpus_used': 1,
                'memory_mb_used': 123,
                'memory_mb_used_servers': 0,
                'local_gb_used': 4,
                'cpu_info': '',
                'hypervisor_type': 'xen',
                'hypervisor_version': 6,
                'hypervisor_hostname': 'hypervisor_host',
            }
        }
        self.assertEqual(expected, response)

    def test_no_servers_for_service(self):
        """
        Test retrieving an empty list of servers on a compute node.
        """
        self.sg_mock.return_value = self.compute_service
        response = self.controller.servers(self.fake_req, "c0001@2")
        self.assertEqual({"servers": []}, response)

    def test_servers_for_service(self):
        """
        Test retrieving a list of servers on a compute node.
        """
        self.sg_mock.return_value = self.compute_service
        self.inst_get_all_mock.return_value = [
            fakes.fake_instance_get()(self.fake_context, "fake_uuid1"),
            fakes.fake_instance_get()(self.fake_context, "fake_uuid2"),
        ]
        response = self.controller.servers(self.fake_req, "c0001@2")
        self.assertEqual(2, len(response["servers"]))
