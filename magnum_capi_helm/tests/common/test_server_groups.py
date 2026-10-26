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
from unittest import mock

from magnum.tests.unit.db import base
from magnum.tests.unit.objects import utils as obj_utils
from openstack.compute.v2 import _proxy as compute_proxy

from magnum_capi_helm.common import server_groups


class FakeAPIVersion:
    """Stand-in for novaclient's APIVersion, as novaclient is not installed."""

    def __init__(self, version):
        self.ver_minor = int(version.split(".")[1])


def _group(name, group_id, project_id):
    group = mock.Mock(id=group_id, project_id=project_id)
    # 'name' is special to Mock, so it has to be set afterwards
    group.name = name
    return group


@mock.patch("magnum.common.clients.OpenStackClients.nova")
class TestServerGroups(base.DbTestCase):
    def setUp(self):
        super().setUp()
        self.cluster_obj = obj_utils.create_test_cluster(
            self.context,
            name="cluster_example_$A",
            master_flavor_id="flavor_small",
            flavor_id="flavor_medium",
        )
        self.project_id = self.cluster_obj.project_id
        self.ctx = mock.Mock(project_id=self.project_id)
        self.prefix = f"magnum-{self.cluster_obj.uuid}-"
        self.sdk = mock.create_autospec(compute_proxy.Proxy, instance=True)

    def _novaclient(self, version="2.15"):
        nova = mock.MagicMock()
        nova.api_version = FakeAPIVersion(version)
        return nova

    def test_managed_name(self, mock_nova):
        self.assertEqual(
            self.prefix + "my-workers",
            server_groups.managed_name(self.cluster_obj, "My_Workers"),
        )

    def test_list_managed_openstacksdk(self, mock_nova):
        mock_nova.return_value = self.sdk
        self.sdk.server_groups.return_value = [
            _group(self.prefix + "ng-1", "id1", self.project_id),
            _group("magnum-other-cluster-ng-1", "id2", self.project_id),
            _group("user-group", "id3", self.project_id),
            _group(None, "id4", self.project_id),
        ]

        groups = server_groups.list_managed(self.ctx, self.cluster_obj)

        self.assertEqual([(self.prefix + "ng-1", "id1")], groups)
        self.sdk.server_groups.assert_called_once_with()

    def test_list_managed_openstacksdk_other_project(self, mock_nova):
        mock_nova.return_value = self.sdk
        self.sdk.server_groups.return_value = [
            _group(self.prefix + "ng-1", "id1", self.project_id),
            _group(self.prefix + "ng-1", "id2", "another-project"),
        ]
        ctx = mock.Mock(project_id="admin-project")

        groups = server_groups.list_managed(ctx, self.cluster_obj)

        self.assertEqual([(self.prefix + "ng-1", "id1")], groups)
        self.sdk.server_groups.assert_called_once_with(all_projects=True)

    def test_list_managed_novaclient(self, mock_nova):
        nova = self._novaclient()
        nova.server_groups.list.return_value = [
            _group(self.prefix + "ng-1", "id1", self.project_id),
            _group("user-group", "id2", self.project_id),
        ]
        mock_nova.return_value = nova

        groups = server_groups.list_managed(self.ctx, self.cluster_obj)

        self.assertEqual([(self.prefix + "ng-1", "id1")], groups)
        nova.server_groups.list.assert_called_once_with(all_projects=False)

    @mock.patch.object(
        server_groups.sdk_server_group.ServerGroup, "create", autospec=True
    )
    @mock.patch.object(
        server_groups.sdk_utils,
        "maximum_supported_microversion",
        return_value=None,
    )
    def test_create_openstacksdk_no_negotiated_microversion(
        self, mock_max, mock_create, mock_nova
    ):
        # Without a negotiated microversion Nova would use 2.1, which does
        # not know the soft-* policies, so at least 2.15 must be requested
        mock_nova.return_value = self.sdk
        mock_create.return_value = mock.Mock(id="new-id")

        group_id = server_groups.create(
            self.ctx, self.cluster_obj, "ng-1", "soft-anti-affinity"
        )

        self.assertEqual("new-id", group_id)
        mock_max.assert_called_once_with(self.sdk, "2.64")
        mock_create.assert_called_once_with(
            mock.ANY, self.sdk, microversion="2.15"
        )
        group = mock_create.call_args[0][0]
        self.assertEqual(self.prefix + "ng-1", group.name)
        self.assertEqual("soft-anti-affinity", group.policy)

    @mock.patch.object(
        server_groups.sdk_server_group.ServerGroup, "create", autospec=True
    )
    @mock.patch.object(
        server_groups.sdk_utils,
        "maximum_supported_microversion",
        return_value="2.64",
    )
    def test_create_openstacksdk_negotiated_microversion(
        self, mock_max, mock_create, mock_nova
    ):
        mock_nova.return_value = self.sdk
        mock_create.return_value = mock.Mock(id="new-id")

        server_groups.create(
            self.ctx, self.cluster_obj, "ng-1", "soft-affinity"
        )

        mock_create.assert_called_once_with(
            mock.ANY, self.sdk, microversion="2.64"
        )

    def test_create_novaclient_default_microversion(self, mock_nova):
        # Older Magnum's novaclient defaults to 2.1, which does not know
        # the soft-* policies, so the version is raised to 2.15
        nova = self._novaclient(version="2.1")
        nova.server_groups.create.return_value = mock.Mock(id="new-id")
        mock_nova.return_value = nova

        group_id = server_groups.create(
            self.ctx, self.cluster_obj, "ng-1", "soft-anti-affinity"
        )

        self.assertEqual("new-id", group_id)
        self.assertEqual(15, nova.api_version.ver_minor)
        nova.server_groups.create.assert_called_once_with(
            name=self.prefix + "ng-1", policies=["soft-anti-affinity"]
        )

    def test_create_novaclient_old_microversion(self, mock_nova):
        nova = self._novaclient(version="2.15")
        nova.server_groups.create.return_value = mock.Mock(id="new-id")
        mock_nova.return_value = nova

        group_id = server_groups.create(
            self.ctx, self.cluster_obj, "ng-1", "anti-affinity"
        )

        self.assertEqual("new-id", group_id)
        self.assertEqual(15, nova.api_version.ver_minor)
        nova.server_groups.create.assert_called_once_with(
            name=self.prefix + "ng-1", policies=["anti-affinity"]
        )

    def test_create_novaclient_new_microversion(self, mock_nova):
        nova = self._novaclient(version="2.64")
        nova.server_groups.create.return_value = mock.Mock(id="new-id")
        mock_nova.return_value = nova

        server_groups.create(
            self.ctx, self.cluster_obj, "ng-1", "anti-affinity"
        )

        self.assertEqual(64, nova.api_version.ver_minor)
        nova.server_groups.create.assert_called_once_with(
            name=self.prefix + "ng-1", policy="anti-affinity"
        )

    def test_delete_managed_all(self, mock_nova):
        mock_nova.return_value = self.sdk
        self.sdk.server_groups.return_value = [
            _group(self.prefix + "ng-1", "id1", self.project_id),
            _group(self.prefix + "ng-2", "id2", self.project_id),
            _group("user-group", "id3", self.project_id),
        ]

        server_groups.delete_managed(self.ctx, self.cluster_obj)

        self.assertEqual(
            [
                mock.call("id1", ignore_missing=True),
                mock.call("id2", ignore_missing=True),
            ],
            self.sdk.delete_server_group.call_args_list,
        )

    def test_delete_managed_one_nodegroup(self, mock_nova):
        mock_nova.return_value = self.sdk
        self.sdk.server_groups.return_value = [
            _group(self.prefix + "ng-1", "id1", self.project_id),
            _group(self.prefix + "ng-1-extra", "id2", self.project_id),
        ]

        server_groups.delete_managed(self.ctx, self.cluster_obj, "ng-1")

        self.sdk.delete_server_group.assert_called_once_with(
            "id1", ignore_missing=True
        )

    def test_delete_managed_novaclient(self, mock_nova):
        nova = self._novaclient()
        nova.server_groups.list.return_value = [
            _group(self.prefix + "ng-1", "id1", self.project_id),
        ]
        mock_nova.return_value = nova

        server_groups.delete_managed(self.ctx, self.cluster_obj)

        nova.server_groups.delete.assert_called_once_with("id1")

    def test_delete_managed_list_error_is_ignored(self, mock_nova):
        mock_nova.return_value = self.sdk
        self.sdk.server_groups.side_effect = Exception("nova is down")

        server_groups.delete_managed(self.ctx, self.cluster_obj)

        self.sdk.delete_server_group.assert_not_called()

    def test_delete_managed_delete_error_continues(self, mock_nova):
        mock_nova.return_value = self.sdk
        self.sdk.server_groups.return_value = [
            _group(self.prefix + "ng-1", "id1", self.project_id),
            _group(self.prefix + "ng-2", "id2", self.project_id),
        ]
        self.sdk.delete_server_group.side_effect = [Exception("boom"), None]

        server_groups.delete_managed(self.ctx, self.cluster_obj)

        self.assertEqual(2, self.sdk.delete_server_group.call_count)
