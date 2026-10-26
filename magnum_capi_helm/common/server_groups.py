# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""Nova server groups that the driver creates and owns for nodegroups."""

from magnum.common import clients
from openstack.compute.v2 import server_group as sdk_server_group
from openstack import utils as sdk_utils
from oslo_log import log as logging

from magnum_capi_helm import driver_utils

LOG = logging.getLogger(__name__)

POLICIES = (
    "affinity",
    "anti-affinity",
    "soft-affinity",
    "soft-anti-affinity",
)

# The soft-affinity and soft-anti-affinity policies were added in compute
# microversion 2.15. Magnum's compute client does not ask for a microversion
# itself, so without this Nova treats the request as 2.1 and rejects them.
MIN_MICROVERSION = "2.15"
# 'policies' was replaced by 'policy' in compute microversion 2.64
MAX_MICROVERSION = "2.64"


def _name_prefix(cluster):
    return f"magnum-{cluster.uuid}-"


def managed_name(cluster, nodegroup_name):
    """Return the name of the server group the driver owns for a nodegroup."""
    return _name_prefix(cluster) + driver_utils.sanitized_name(nodegroup_name)


def _is_novaclient(nova):
    # NOTE: the openstacksdk compute proxy also has a server_groups()
    # method, so look for the novaclient manager's list() instead.
    return hasattr(nova.server_groups, "list")


def list_managed(context, cluster):
    """Return (name, id) for each server group the driver owns for cluster."""
    nova = clients.OpenStackClients(context).nova()
    # An admin acting on another project's cluster has to look across all
    # projects to see the server groups of the cluster's project.
    all_projects = context.project_id != cluster.project_id
    if _is_novaclient(nova):
        groups = nova.server_groups.list(all_projects=all_projects)
    else:
        query = {"all_projects": True} if all_projects else {}
        groups = nova.server_groups(**query)
    prefix = _name_prefix(cluster)
    return [
        (group.name, group.id)
        for group in groups
        if (group.name or "").startswith(prefix)
        and (not all_projects or group.project_id == cluster.project_id)
    ]


def create(context, cluster, nodegroup_name, policy):
    """Create the server group for a nodegroup and return its ID."""
    nova = clients.OpenStackClients(context).nova()
    name = managed_name(cluster, nodegroup_name)
    LOG.info(
        f"Creating server group {name} with policy {policy} "
        f"for cluster {cluster.uuid}"
    )
    if _is_novaclient(nova):
        if nova.api_version.ver_minor < 15:
            # This client is only used for this call, so it is safe to raise
            # its version. Build novaclient's APIVersion from the existing
            # one, as newer Magnum does not install novaclient at all.
            nova.api_version = type(nova.api_version)(MIN_MICROVERSION)
        if nova.api_version.ver_minor >= 64:
            group = nova.server_groups.create(name=name, policy=policy)
        else:
            group = nova.server_groups.create(name=name, policies=[policy])
    else:
        # openstacksdk only sends a microversion when it can negotiate one
        # with the endpoint, and Proxy.create_server_group() cannot take one,
        # so create the resource directly with an explicit microversion.
        # openstacksdk converts 'policy' for older microversions itself.
        microversion = (
            sdk_utils.maximum_supported_microversion(nova, MAX_MICROVERSION)
            or MIN_MICROVERSION
        )
        group = sdk_server_group.ServerGroup.new(
            name=name, policy=policy
        ).create(nova, microversion=microversion)
    return group.id


def delete_managed(context, cluster, nodegroup_name=None):
    """Delete the cluster's server groups, or only those of one nodegroup.

    Failures are logged rather than raised, so that they never block the
    deletion of the cluster or nodegroup itself.
    """
    try:
        groups = list_managed(context, cluster)
    except Exception as e:
        LOG.warning(
            f"Failed to list server groups for cluster {cluster.uuid}: {e}"
        )
        return
    if nodegroup_name:
        name = managed_name(cluster, nodegroup_name)
        groups = [group for group in groups if group[0] == name]

    nova = clients.OpenStackClients(context).nova()
    for name, group_id in groups:
        LOG.info(
            f"Deleting server group {name} ({group_id}) "
            f"for cluster {cluster.uuid}"
        )
        try:
            if _is_novaclient(nova):
                nova.server_groups.delete(group_id)
            else:
                nova.delete_server_group(group_id, ignore_missing=True)
        except Exception as e:
            LOG.warning(
                f"Failed to delete server group {name} ({group_id}) "
                f"for cluster {cluster.uuid}: {e}"
            )
