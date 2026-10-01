| strategy | workload | ms_per_op | J_per_op | W | cv_J_per_op | J_per_op_active |
|---|---|---|---|---|---|---|
| PLATFORM_THREADS | CPU | 156.8 | 1.771 | 11.27 | 0.005691 | 1.767 |
| PLATFORM_THREADS | IO | 16.61 | 0.02514 | 1.528 | 0.0478 | 0.02465 |
| FIXED_POOL | CPU | 182.2 | 1.987 | 10.88 | 0.00888 | 1.982 |
| FIXED_POOL | IO | 458.6 | 0.01736 | 0.05193 | 0.4863 | 0.003784 |
| FORK_JOIN | CPU | 182.2 | 1.974 | 10.84 | 0.007178 | 1.968 |
| FORK_JOIN | IO | 397.5 | 0.008 | 0.05702 | 1.164 | -0.003771 |
| VIRTUAL_THREADS | CPU | 154.8 | 1.767 | 11.4 | 0.009357 | 1.763 |
| VIRTUAL_THREADS | IO | 12.61 | 0.0003451 | 0.02701 | 0.02133 | -2.843e-05 |
