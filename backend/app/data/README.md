# Philippine location reference data

`psgc-2026-07-13.json` is the flat PSGC hierarchy from `barangay` package version
`2026.7.13.0`, based on the PSA second-quarter 2026 masterlist (released 13 July
2026). It contains 18 regions, 82 provinces, 1,643 cities/municipalities, and
42,010 barangays. The source package is MIT licensed; its license is included
beside the data. PSGC names and codes originate from the Philippine Statistics
Authority. The canonical current source and quarterly updates are published at
<https://psa.gov.ph/classification/psgc>.

The API serves this checked-in snapshot locally; address entry does not depend
on a third-party service at runtime. Refresh the snapshot from a new PSA release,
review the resulting hierarchy changes, and update this note and the bundled
license when upgrading the source package. The codes are stored as text because
leading zeroes are significant.
