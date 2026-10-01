# Backing up and restoring etcd

etcd holds the whole state of a Kubernetes cluster: every object, secret and lease. Losing it means rebuilding the cluster from manifests, so a tested backup matters more than any other.

Take a snapshot with `etcdctl` against a healthy member:

    ETCDCTL_API=3 etcdctl snapshot save /backup/etcd-$(date +%F).db \
      --endpoints=https://127.0.0.1:2379 \
      --cacert=/etc/kubernetes/pki/etcd/ca.crt \
      --cert=/etc/kubernetes/pki/etcd/server.crt \
      --key=/etc/kubernetes/pki/etcd/server.key

Check it with `etcdutl snapshot status /backup/etcd-2026-01-10.db`, which prints the revision and the number of keys.

Restoring never overwrites a live data directory. You restore into a new directory and point etcd at it:

    etcdutl snapshot restore /backup/etcd-2026-01-10.db --data-dir /var/lib/etcd-restored

Then stop the API server, change the etcd static pod (or systemd unit) to use the new data directory, and start everything again. In a multi-member cluster every member is restored from the same snapshot with its own `--name` and `--initial-cluster` flags.

Things that bite people:

- A snapshot is only as good as the last restore test. Schedule one.
- Snapshots contain Secrets in clear text unless encryption at rest is on. Store them encrypted.
- k3s with embedded etcd has its own commands: `k3s etcd-snapshot save` and `k3s server --cluster-reset --cluster-reset-restore-path=...`.
- Managed control planes (EKS, GKE, AKS) do not give you etcd access; back up objects with Velero instead.
