===================
Configuration Guide
===================

For complete reference of configuration options for this driver used in
magnum.conf plesese refer to:

.. toctree::
   :maxdepth: 1

   Configuration Reference <config-reference>


Features
========

The driver currently supports create, delete and upgrade operations as well
as updates to node groups and their sizes.

The Kubernetes versions against which the CAPI Helm charts are currently being
tested can be found `here <https://github.com/azimuth-cloud/capi-helm-charts/blob/main/.github/workflows/ensure-capi-images.yaml#L9>`__.

The driver supports cluster labels to customise cluster behaviour. The full
list of supported labels, their types, defaults, and descriptions is
maintained in the :doc:`Configuration Reference <config-reference>` under
the ``[capi_helm_cluster_labels]`` section.

Default values for all labels can be set operator-wide in ``magnum.conf``
under ``[capi_helm_cluster_labels]`` and overridden per cluster or template
by the user via Magnum labels.

.. note::

   ``capi_helm_chart_version`` can only be set via a cluster template label
   and cannot be overridden per cluster. When unset it falls back to
   ``[capi_helm] default_helm_chart_version``.


Server groups
-------------

Worker nodes can be booted into an existing Nova server group, for example to
spread a nodegroup across hypervisors. Create the server group first, then
pass its ID with the ``server_group_id`` nodegroup label:

.. code-block:: bash

   openstack server group create --policy soft-anti-affinity my-workers
   openstack coe nodegroup create my-cluster my-workers \
       --flavor m1.large --node-count 3 \
       --labels server_group_id=<server-group-uuid>

A ``server_group_id`` label on the nodegroup takes precedence over one set on
the cluster or cluster template. Control plane nodes use the separate
``master_server_group_id`` cluster label. The driver checks that the server
group exists when the cluster or nodegroup is created, and never deletes a
server group passed in this way.

Alternatively, let the driver manage the server group by setting only a
policy, with the ``server_group_policy`` nodegroup label (or
``master_server_group_policy`` cluster label for the control plane). The
policy is one of ``affinity``, ``anti-affinity``, ``soft-affinity`` or
``soft-anti-affinity``:

.. code-block:: bash

   openstack coe nodegroup create my-cluster my-workers \
       --flavor m1.large --node-count 3 \
       --labels server_group_policy=soft-anti-affinity

The driver creates a server group named
``magnum-<cluster-uuid>-<nodegroup-name>`` in the cluster's project, and
deletes it when the nodegroup or cluster is deleted. If a ``server_group_id``
label is also set, it takes precedence and no server group is created.
Operators can set a default policy for all clusters with
``[capi_helm_cluster_labels] server_group_policy`` in ``magnum.conf``.

The policy of a server group cannot be changed once it is created, so changing
the policy label later has no effect on an existing server group. If a
driver-created server group is deleted by hand, the driver creates a new one on
the next cluster update, which replaces the nodes of that nodegroup.

.. note::

   With a hard ``anti-affinity`` policy, every node needs its own hypervisor,
   and rolling upgrades create one extra node at a time. A nodegroup of N
   nodes therefore needs N+1 hypervisors, and N+1 must fit in the
   ``server_group_members`` quota (10 by default). Remember to allow for
   ``max_node_count`` when autoscaling. ``soft-anti-affinity`` avoids these
   limits.



Tip & Tricks
=============

Currently, all clusters use the Calico CNI. While Cilium is also supported
in the Helm charts, it is not currently regularly tested.

We have found that cluster upgrades with ClusterAPI don't work well without
using a load balancer, even with a single node control plane, so we currently
ignore the "master-lb-enabled" flag.


