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


Air-gapped and private registries
---------------------------------

By default, cluster nodes pull images through mirrors on ``quay.io``, falling
back to the public registries, and add-on charts are fetched from public Helm
repositories. To use a private registry, a registry cache or an air-gapped
cloud, give the driver YAML files of extra Helm values for the
``openstack-cluster`` chart:

.. code-block:: ini

   [capi_helm]
   extra_helm_values_files = /etc/magnum/capi-helm/registry.yaml

For example, for a Harbor registry with proxy-cache projects:

.. code-block:: yaml

   registryMirrors:
     docker.io: ["https://harbor.example.com/v2/dockerhub-proxy"]
     registry.k8s.io: ["https://harbor.example.com/v2/k8s-proxy"]
     quay.io: ["https://harbor.example.com/v2/quay-proxy"]
     ghcr.io: ["https://harbor.example.com/v2/ghcr-proxy"]
     # Remove the chart default mirror for a registry that is not used
     nvcr.io: null
   registryAuth:
     harbor.example.com:
       username: robot$capi
       password: "..."
   trustedCAs:
     harbor-ca: |
       -----BEGIN CERTIFICATE-----
       ...
   autoscaler:
     image:
       repository: harbor.example.com/k8s-proxy/autoscaling/cluster-autoscaler
   addons:
     cni:
       calico:
         chart:
           repo: https://charts.example.com/projectcalico

Any value of the chart can be set this way. The values are merged as follows:

* Later files take precedence over earlier ones, and the values the driver
  generates from the cluster, its template and its labels take precedence over
  all of them. Values that the driver sets on every cluster, such as
  ``kubernetesVersion``, ``machineImageId``, ``controlPlane``, ``nodeGroups``,
  ``clusterNetworking`` and ``kubeNetwork``, have no effect in these files.
* Mappings are merged, while lists and other values replace earlier ones, as
  when passing several values files to Helm.
* ``null`` removes a chart default. The chart defaults ``registryMirrors`` for
  ``docker.io``, ``ghcr.io``, ``nvcr.io``, ``quay.io`` and
  ``registry.k8s.io``, so set every one of them, either to your mirror or to
  ``null``.

The files are read again on every Helm release update, so a change applies to
a cluster on its next create, resize, upgrade or nodegroup change, without
restarting magnum-conductor. Keep the files identical on every conductor host.

.. warning::

   Changing values that end up in the node bootstrap configuration, such as
   ``registryMirrors``, ``registryAuth`` or ``trustedCAs``, replaces every node
   of a cluster, one at a time, on that cluster's next update.

.. note::

   ``registryAuth`` holds passwords in clear text. Make the files readable only
   by the user running magnum-conductor (mode ``0600``), and use read-only,
   pull-only accounts: the credentials are stored in Secrets in the management
   cluster and written to every node of each cluster.

A fully air-gapped cloud also needs node images with the Kubernetes binaries
built in, an internal registry holding every image the chart and its add-ons
use, an internal chart repository for the add-on charts and the
``openstack-cluster`` chart (see ``[capi_helm] helm_chart_repo``), and a
management cluster installed without internet access, for example with
``clusterctl`` image overrides.



Tip & Tricks
=============

Currently, all clusters use the Calico CNI. While Cilium is also supported
in the Helm charts, it is not currently regularly tested.

We have found that cluster upgrades with ClusterAPI don't work well without
using a load balancer, even with a single node control plane, so we currently
ignore the "master-lb-enabled" flag.


