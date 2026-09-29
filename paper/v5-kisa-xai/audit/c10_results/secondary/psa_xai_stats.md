# PSA-XAI statistics

Protocol SHA-256: `c0c7b79775b3aa36d3dc59f5a8544e5248e9517ca218319cb8ee83d88c70e709`

One-sided superiority p values use 2,000 paired bootstrap draws; Holm adjusts H1/H2 within each population and scope.

## main

| Scope | H | Effect | 95% CI | Holm p | Eligible files | Groups | Empty CAM excluded |
|---|---|---:|---:|---:|---:|---:|---:|
| seed_42 | H1 | -0.00585099 | [-0.0190847, 0.0074296] | 0.807596 | 17353 | 5867 | 12 |
| seed_42 | H2 | 0.413501 | [0.390542, 0.43473] | 0.0009995 | 17353 | 5867 | 12 |
| seed_43 | H1 | -0.035678 | [-0.0446882, -0.0267321] | 1 | 17363 | 5874 | 2 |
| seed_43 | H2 | 0.298988 | [0.270763, 0.326272] | 0.0009995 | 17363 | 5874 | 2 |
| seed_44 | H1 | -0.0307891 | [-0.045538, -0.017265] | 1 | 17353 | 5869 | 12 |
| seed_44 | H2 | 0.279813 | [0.260243, 0.298238] | 0.0009995 | 17353 | 5869 | 12 |
| seed_average | H1 | -0.0245719 | [-0.0337451, -0.0155357] | 1 | 17346 | 5864 | {'seed_42': 12, 'seed_43': 2, 'seed_44': 12} |
| seed_average | H2 | 0.33059 | [0.312954, 0.348061] | 0.0009995 | 17346 | 5864 | {'seed_42': 12, 'seed_43': 2, 'seed_44': 12} |

### File bootstrap sensitivity

| Scope | H | Effect | 95% CI | p |
|---|---|---:|---:|---:|
| seed_42 | H1 | -0.000898709 | [-0.0077398, 0.00566264] | 0.595202 |
| seed_42 | H2 | 0.388323 | [0.375477, 0.400852] | 0.00049975 |
| seed_43 | H1 | -0.0268598 | [-0.0315845, -0.0220931] | 1 |
| seed_43 | H2 | 0.307951 | [0.292389, 0.32343] | 0.00049975 |
| seed_44 | H1 | -0.0538053 | [-0.062304, -0.0456154] | 1 |
| seed_44 | H2 | 0.338196 | [0.327102, 0.349684] | 0.00049975 |
| seed_average | H1 | -0.0273209 | [-0.0318284, -0.0225605] | 1 |
| seed_average | H2 | 0.344847 | [0.334974, 0.354841] | 0.00049975 |

### Correctly detected malicious subset

| Scope | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| seed_42 | H1 | -0.0144832 | [-0.0250287, -0.00421756] | 16616 |
| seed_42 | H2 | 0.43141 | [0.408818, 0.454365] | 16616 |
| seed_43 | H1 | -0.0310979 | [-0.0387933, -0.0237963] | 16445 |
| seed_43 | H2 | 0.318332 | [0.288413, 0.347871] | 16445 |
| seed_44 | H1 | -0.0343176 | [-0.0462929, -0.0226301] | 16403 |
| seed_44 | H2 | 0.297913 | [0.278424, 0.318624] | 16403 |
| seed_average | H1 | -0.025493 | [-0.0317173, -0.0194657] | 15823 |
| seed_average | H2 | 0.353816 | [0.334957, 0.373107] | 15823 |

### seed_42 subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.00651378 | [-0.020117, 0.00665379] | 15673 |
| mean_pool | H2 | 0.415635 | [0.393053, 0.438721] | 15673 |
| nearest_repetition | H1 | 0.00932974 | [-0.0227679, 0.0434092] | 1680 |
| nearest_repetition | H2 | 0.357569 | [0.287951, 0.430699] | 1680 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | -0.00509088 | 0.026713 | 17395 |
| 0.05 | local_median | entropy | H2 | -0.10158 | 3.09583 | 17395 |
| 0.05 | local_median | front_position | H1 | 0.0251102 | -0.00348801 | 17395 |
| 0.05 | local_median | front_position | H2 | 0.10699 | 2.88726 | 17395 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.018387 | 0.00328873 | 17353 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | 0.153091 | 2.83881 | 17353 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.0150261 | 0.00659606 | 17395 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | 0.244699 | 2.74955 | 17395 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.0188719 | 0.0460281 | 17395 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | 0.306298 | 6.67346 | 17395 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | 0.0524979 | -0.0246735 | 17395 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.5929 | 6.38848 | 17395 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | 0.00871648 | 0.0193084 | 17353 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.228968 | 6.75861 | 17353 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | 0.0161212 | 0.0117393 | 17395 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.248772 | 6.73698 | 17395 |
| 0.05 | zero | entropy | H1 | -0.044811 | 0.100668 | 17395 |
| 0.05 | zero | entropy | H2 | 0.850325 | 1.22767 | 17395 |
| 0.05 | zero | front_position | H1 | 0.0841023 | -0.0282452 | 17395 |
| 0.05 | zero | front_position | H2 | -1.05788 | 3.13588 | 17395 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | 0.00506249 | 0.0509024 | 17353 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 1.89733 | 0.180193 | 17353 |
| 0.05 | zero | uniform_random_20_repeats | H1 | 0.02591 | 0.0299472 | 17395 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 1.52798 | 0.55002 | 17395 |
| 0.1 | local_median | entropy | H1 | -0.0280173 | 0.0686861 | 17395 |
| 0.1 | local_median | entropy | H2 | -0.0480636 | 3.42501 | 17395 |
| 0.1 | local_median | front_position | H1 | 0.0125503 | 0.0281186 | 17395 |
| 0.1 | local_median | front_position | H2 | 0.0839866 | 3.29296 | 17395 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.0251994 | 0.0155684 | 17353 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | 0.332636 | 3.04231 | 17353 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.0261686 | 0.0145002 | 17395 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.508264 | 2.86869 | 17395 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0372991 | 0.0776118 | 17395 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | 0.459832 | 6.63829 | 17395 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0510439 | -0.010259 | 17395 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.713416 | 6.3853 | 17395 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.000898709 | 0.0414556 | 17353 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.388323 | 6.71133 | 17353 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | 0.0144855 | 0.0259618 | 17395 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.42927 | 6.67095 | 17395 |
| 0.1 | zero | entropy | H1 | 0.0154147 | 0.0829405 | 17395 |
| 0.1 | zero | entropy | H2 | 0.948814 | 1.94436 | 17395 |
| 0.1 | zero | front_position | H1 | 0.064653 | 0.0337022 | 17395 |
| 0.1 | zero | front_position | H2 | -0.846388 | 3.73956 | 17395 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.0258857 | 0.124421 | 17353 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 2.94751 | -0.0558168 | 17353 |
| 0.1 | zero | uniform_random_20_repeats | H1 | 0.0207129 | 0.0776423 | 17395 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 2.47414 | 0.419039 | 17395 |
| 0.2 | local_median | entropy | H1 | -0.059002 | 0.145174 | 17395 |
| 0.2 | local_median | entropy | H2 | 0.0782396 | 3.90738 | 17395 |
| 0.2 | local_median | front_position | H1 | 0.0255293 | 0.0606425 | 17395 |
| 0.2 | local_median | front_position | H2 | 0.353715 | 3.6319 | 17395 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.0286993 | 0.0576824 | 17353 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.500805 | 3.48277 | 17353 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.0502091 | 0.0359628 | 17395 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.82287 | 3.16275 | 17395 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.0734898 | 0.129773 | 17395 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | 0.663939 | 6.56617 | 17395 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0896993 | -0.0356835 | 17395 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.706209 | 6.52624 | 17395 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0303494 | 0.0850932 | 17353 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.625859 | 6.60627 | 17353 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.00170299 | 0.0566327 | 17395 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.808797 | 6.42172 | 17395 |
| 0.2 | zero | entropy | H1 | -0.000147468 | 0.176701 | 17395 |
| 0.2 | zero | entropy | H2 | 0.92599 | 3.17727 | 17395 |
| 0.2 | zero | front_position | H1 | 0.109613 | 0.0669404 | 17395 |
| 0.2 | zero | front_position | H2 | -0.635524 | 4.73879 | 17395 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.173458 | 0.350379 | 17353 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.2187 | -0.117543 | 17353 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.0847426 | 0.261296 | 17395 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 4.49663 | -0.393371 | 17395 |
| 0.4 | local_median | entropy | H1 | -0.140483 | 0.358355 | 17395 |
| 0.4 | local_median | entropy | H2 | 0.163673 | 4.71846 | 17395 |
| 0.4 | local_median | front_position | H1 | 0.0850183 | 0.132853 | 17395 |
| 0.4 | local_median | front_position | H2 | 0.898551 | 3.98359 | 17395 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.0514087 | 0.166991 | 17353 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.546204 | 4.33328 | 17353 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.112708 | 0.105163 | 17395 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 0.966459 | 3.91568 | 17395 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.100406 | 0.134049 | 17395 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 1.13377 | 6.23825 | 17395 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.0875579 | -0.0562993 | 17395 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | 0.794212 | 6.5767 | 17395 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0535267 | 0.0862778 | 17353 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 1.10833 | 6.25868 | 17353 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0551384 | 0.0875689 | 17395 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 1.73865 | 5.62684 | 17395 |
| 0.4 | zero | entropy | H1 | -0.344991 | 0.555426 | 17395 |
| 0.4 | zero | entropy | H2 | 0.368507 | 5.4335 | 17395 |
| 0.4 | zero | front_position | H1 | 0.111212 | 0.0992239 | 17395 |
| 0.4 | zero | front_position | H2 | 0.261984 | 5.54002 | 17395 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.533218 | 0.743876 | 17353 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 3.89319 | 1.90516 | 17353 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.223551 | 0.433987 | 17395 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 4.62152 | 1.18049 | 17395 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 68.6383 | 17407 |
| dos_and_pe_headers | 486.685 | 17407 |
| executable_sections | 10980.6 | 17407 |
| non_executable_sections | 3251.44 | 17407 |
| overlay | 3198.87 | 17407 |
| resource_like_sections | 3205.76 | 17407 |
| unknown | 821.486 | 17407 |

### seed_43 subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.0378721 | [-0.0467378, -0.0291385] | 15680 |
| mean_pool | H2 | 0.308267 | [0.278343, 0.337608] | 15680 |
| nearest_repetition | H1 | -0.000345332 | [-0.0490876, 0.0448888] | 1683 |
| nearest_repetition | H2 | 0.0683731 | [-0.00532098, 0.140356] | 1683 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | -0.00549691 | 0.0238353 | 17405 |
| 0.05 | local_median | entropy | H2 | -0.0281625 | 3.5335 | 17405 |
| 0.05 | local_median | front_position | H1 | 0.00240442 | 0.015934 | 17405 |
| 0.05 | local_median | front_position | H2 | 0.0398369 | 3.4655 | 17405 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.0130054 | 0.00538061 | 17363 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | 0.0750292 | 3.42607 | 17363 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.0155654 | 0.00277294 | 17405 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | 0.102319 | 3.40301 | 17405 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.0261889 | 0.0450866 | 17405 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | 0.265341 | 6.62372 | 17405 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | 0.0381038 | -0.0195665 | 17405 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.268788 | 6.61261 | 17405 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0128114 | 0.0316261 | 17363 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.129696 | 6.75614 | 17363 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.00417745 | 0.0230421 | 17405 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.0730149 | 6.81679 | 17405 |
| 0.05 | zero | entropy | H1 | -0.116549 | 0.132006 | 17405 |
| 0.05 | zero | entropy | H2 | 2.17464 | 1.42588 | 17405 |
| 0.05 | zero | front_position | H1 | 0.00513288 | 0.0103243 | 17405 |
| 0.05 | zero | front_position | H2 | -0.972057 | 4.57257 | 17405 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | -0.00925896 | 0.0247567 | 17363 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 2.36376 | 1.23653 | 17363 |
| 0.05 | zero | uniform_random_20_repeats | H1 | 0.0128273 | 0.00262983 | 17405 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 2.61438 | 0.986133 | 17405 |
| 0.1 | local_median | entropy | H1 | -0.0104712 | 0.0527088 | 17405 |
| 0.1 | local_median | entropy | H2 | 0.0111545 | 3.71945 | 17405 |
| 0.1 | local_median | front_position | H1 | -0.0167692 | 0.0590069 | 17405 |
| 0.1 | local_median | front_position | H2 | 0.0682675 | 3.66234 | 17405 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.0261192 | 0.0162252 | 17363 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | 0.147134 | 3.57925 | 17363 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.0357389 | 0.00649877 | 17405 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.208419 | 3.52218 | 17405 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0209802 | 0.0573866 | 17405 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | 0.3722 | 6.53228 | 17405 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0505189 | -0.0144171 | 17405 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.246407 | 6.65854 | 17405 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0268598 | 0.063126 | 17363 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.307951 | 6.59516 | 17363 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.00208433 | 0.0383202 | 17405 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.215338 | 6.68868 | 17405 |
| 0.1 | zero | entropy | H1 | -0.122706 | 0.14638 | 17405 |
| 0.1 | zero | entropy | H2 | 2.02625 | 1.76394 | 17405 |
| 0.1 | zero | front_position | H1 | 0.0375767 | -0.0139026 | 17405 |
| 0.1 | zero | front_position | H2 | -1.13886 | 4.92904 | 17405 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.0430946 | 0.0668309 | 17363 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 2.95557 | 0.834145 | 17363 |
| 0.1 | zero | uniform_random_20_repeats | H1 | 0.013462 | 0.0102121 | 17405 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 3.13023 | 0.659955 | 17405 |
| 0.2 | local_median | entropy | H1 | -0.0108272 | 0.107728 | 17405 |
| 0.2 | local_median | entropy | H2 | 0.198755 | 4.08807 | 17405 |
| 0.2 | local_median | front_position | H1 | -0.023687 | 0.120588 | 17405 |
| 0.2 | local_median | front_position | H2 | 0.430181 | 3.85665 | 17405 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.0518439 | 0.0452957 | 17363 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.359623 | 3.92281 | 17363 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.080079 | 0.0168218 | 17405 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.520782 | 3.76605 | 17405 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.00818024 | 0.0574091 | 17405 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | 0.506793 | 6.36696 | 17405 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0235543 | 0.0264367 | 17405 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.132584 | 6.73835 | 17405 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0755244 | 0.124685 | 17363 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.596974 | 6.27291 | 17363 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.022355 | 0.0712192 | 17405 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.609255 | 6.26251 | 17405 |
| 0.2 | zero | entropy | H1 | -0.0113679 | 0.0375749 | 17405 |
| 0.2 | zero | entropy | H2 | 1.85807 | 2.81542 | 17405 |
| 0.2 | zero | front_position | H1 | 0.0822164 | -0.0560094 | 17405 |
| 0.2 | zero | front_position | H2 | -1.01409 | 5.68758 | 17405 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.119046 | 0.145322 | 17363 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.14608 | 0.52592 | 17363 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.0239396 | 0.0501466 | 17405 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 4.55302 | 0.120467 | 17405 |
| 0.4 | local_median | entropy | H1 | -0.145632 | 0.364809 | 17405 |
| 0.4 | local_median | entropy | H2 | 0.147586 | 4.75863 | 17405 |
| 0.4 | local_median | front_position | H1 | 0.0257693 | 0.193407 | 17405 |
| 0.4 | local_median | front_position | H2 | 0.754937 | 4.15128 | 17405 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.0915114 | 0.128187 | 17363 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.419446 | 4.48142 | 17363 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.153965 | 0.065212 | 17405 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 0.656585 | 4.24963 | 17405 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.0110809 | 0.0542695 | 17405 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 0.744325 | 6.05606 | 17405 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.0822095 | -0.0408169 | 17405 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | -0.0839603 | 6.88571 | 17405 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.125929 | 0.168386 | 17363 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 1.05728 | 5.7406 | 17363 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0662939 | 0.10866 | 17405 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 1.47228 | 5.3263 | 17405 |
| 0.4 | zero | entropy | H1 | -0.0866259 | 0.0841052 | 17405 |
| 0.4 | zero | entropy | H2 | 1.70399 | 4.56869 | 17405 |
| 0.4 | zero | front_position | H1 | 0.0211027 | -0.0236234 | 17405 |
| 0.4 | zero | front_position | H2 | 0.156883 | 6.1158 | 17405 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.312766 | 0.310237 | 17363 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 4.27203 | 1.99708 | 17363 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.108172 | 0.105651 | 17405 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 5.35745 | 0.915235 | 17405 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 69.2242 | 17407 |
| dos_and_pe_headers | 447.916 | 17407 |
| executable_sections | 11198.2 | 17407 |
| non_executable_sections | 3491.86 | 17407 |
| overlay | 3422.34 | 17407 |
| resource_like_sections | 3477.3 | 17407 |
| unknown | 784.029 | 17407 |

### seed_44 subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.0306556 | [-0.0456429, -0.0175601] | 15670 |
| mean_pool | H2 | 0.28123 | [0.261693, 0.301159] | 15670 |
| nearest_repetition | H1 | -0.0393311 | [-0.116559, 0.0292769] | 1683 |
| nearest_repetition | H2 | 0.238399 | [0.173624, 0.30165] | 1683 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | -0.0186112 | 0.064205 | 17395 |
| 0.05 | local_median | entropy | H2 | 0.207111 | 2.87361 | 17395 |
| 0.05 | local_median | front_position | H1 | 0.0873472 | -0.0417533 | 17395 |
| 0.05 | local_median | front_position | H2 | 0.15727 | 2.92345 | 17395 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.0518795 | -0.00617536 | 17353 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | 0.0643303 | 3.01293 | 17353 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.0453579 | 0.000235903 | 17395 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | 0.19236 | 2.88836 | 17395 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.0794154 | 0.109156 | 17395 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | 0.0963261 | 5.3306 | 17395 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | 0.0605459 | -0.0318367 | 17395 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.407899 | 5.0185 | 17395 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0256998 | 0.0543482 | 17353 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.149487 | 5.27803 | 17353 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0197526 | 0.0484788 | 17395 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.124959 | 5.30317 | 17395 |
| 0.05 | zero | entropy | H1 | -0.136676 | 0.20124 | 17395 |
| 0.05 | zero | entropy | H2 | 1.4527 | 0.601518 | 17395 |
| 0.05 | zero | front_position | H1 | 0.0644837 | 8.1011e-05 | 17395 |
| 0.05 | zero | front_position | H2 | -1.211 | 3.26522 | 17395 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | -0.0377052 | 0.102426 | 17353 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 2.47639 | -0.422784 | 17353 |
| 0.05 | zero | uniform_random_20_repeats | H1 | 0.0364829 | 0.0280818 | 17395 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 2.87878 | -0.824563 | 17395 |
| 0.1 | local_median | entropy | H1 | -0.0304798 | 0.107884 | 17395 |
| 0.1 | local_median | entropy | H2 | 0.284826 | 3.07651 | 17395 |
| 0.1 | local_median | front_position | H1 | 0.00832846 | 0.0690757 | 17395 |
| 0.1 | local_median | front_position | H2 | 0.0883396 | 3.273 | 17395 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.0799124 | -0.0023211 | 17353 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | 0.183254 | 3.17456 | 17353 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.0742031 | 0.00320105 | 17395 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.387719 | 2.97362 | 17395 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0995833 | 0.138299 | 17395 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | 0.212504 | 5.29507 | 17395 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0538463 | -0.0156712 | 17395 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.657144 | 4.85149 | 17395 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0538053 | 0.0920588 | 17353 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.338196 | 5.16857 | 17353 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0354407 | 0.0735844 | 17395 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.302933 | 5.20373 | 17395 |
| 0.1 | zero | entropy | H1 | -0.201035 | 0.272525 | 17395 |
| 0.1 | zero | entropy | H2 | 1.91588 | 0.809789 | 17395 |
| 0.1 | zero | front_position | H1 | 0.0709136 | 0.00057566 | 17395 |
| 0.1 | zero | front_position | H2 | -1.4865 | 4.21216 | 17395 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.216009 | 0.287671 | 17353 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 3.45114 | -0.726216 | 17353 |
| 0.1 | zero | uniform_random_20_repeats | H1 | -0.00911457 | 0.0806039 | 17395 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 3.97536 | -1.24969 | 17395 |
| 0.2 | local_median | entropy | H1 | -0.0946783 | 0.243093 | 17395 |
| 0.2 | local_median | entropy | H2 | 0.361698 | 3.48689 | 17395 |
| 0.2 | local_median | front_position | H1 | 0.0368878 | 0.111526 | 17395 |
| 0.2 | local_median | front_position | H2 | 0.501478 | 3.34711 | 17395 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.125585 | 0.0231877 | 17353 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.352926 | 3.49221 | 17353 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.133432 | 0.0149827 | 17395 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.679662 | 3.16893 | 17395 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.132104 | 0.185012 | 17395 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | 0.459753 | 5.18568 | 17395 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0797501 | -0.0279749 | 17395 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.7039 | 4.94105 | 17395 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0695161 | 0.121568 | 17353 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.710707 | 4.93705 | 17353 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0410664 | 0.0925044 | 17395 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.740405 | 4.90671 | 17395 |
| 0.2 | zero | entropy | H1 | -0.328139 | 0.395824 | 17395 |
| 0.2 | zero | entropy | H2 | 1.85941 | 2.04499 | 17395 |
| 0.2 | zero | front_position | H1 | 0.0953418 | -0.027657 | 17395 |
| 0.2 | zero | front_position | H2 | -2.56486 | 6.46926 | 17395 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.556341 | 0.624182 | 17353 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.6882 | -0.785496 | 17353 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.195987 | 0.263672 | 17395 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 5.70961 | -1.80521 | 17395 |
| 0.4 | local_median | entropy | H1 | -0.3929 | 0.662437 | 17395 |
| 0.4 | local_median | entropy | H2 | 0.247362 | 4.22506 | 17395 |
| 0.4 | local_median | front_position | H1 | 0.133183 | 0.136354 | 17395 |
| 0.4 | local_median | front_position | H2 | 0.85347 | 3.61896 | 17395 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.133878 | 0.136309 | 17353 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.424483 | 4.04463 | 17353 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.197706 | 0.0718317 | 17395 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 0.793251 | 3.67917 | 17395 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.140418 | 0.163305 | 17395 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 0.765416 | 5.05557 | 17395 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.106133 | -0.0837431 | 17395 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | 0.694669 | 5.13082 | 17395 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.122691 | 0.14553 | 17353 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 1.15741 | 4.66491 | 17353 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.111988 | 0.13495 | 17395 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 1.56052 | 4.26461 | 17395 |
| 0.4 | zero | entropy | H1 | -0.526324 | 0.561667 | 17395 |
| 0.4 | zero | entropy | H2 | 1.41138 | 4.07397 | 17395 |
| 0.4 | zero | front_position | H1 | 0.044467 | -0.00912449 | 17395 |
| 0.4 | zero | front_position | H2 | -1.07062 | 6.55597 | 17395 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.83176 | 0.867114 | 17353 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 4.54111 | 0.939498 | 17353 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.522534 | 0.557876 | 17395 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 5.73251 | -0.247163 | 17395 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 77.1348 | 17407 |
| dos_and_pe_headers | 442.162 | 17407 |
| executable_sections | 9987.45 | 17407 |
| non_executable_sections | 3015.41 | 17407 |
| overlay | 3201.92 | 17407 |
| resource_like_sections | 3250.95 | 17407 |
| unknown | 731.156 | 17407 |

### seed_average subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.0253098 | [-0.0348598, -0.016736] | 15666 |
| mean_pool | H2 | 0.3348 | [0.317312, 0.353296] | 15666 |
| nearest_repetition | H1 | -0.0172625 | [-0.0580735, 0.0196665] | 1680 |
| nearest_repetition | H2 | 0.222758 | [0.170508, 0.27569] | 1680 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | -0.009733 | 0.0382511 | 17395 |
| 0.05 | local_median | entropy | H2 | 0.0257894 | 3.16765 | 17395 |
| 0.05 | local_median | front_position | H1 | 0.0382872 | -0.00976913 | 17395 |
| 0.05 | local_median | front_position | H2 | 0.101366 | 3.09207 | 17395 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.0277573 | 0.000831324 | 17353 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | 0.0974835 | 3.0926 | 17353 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.0253165 | 0.00320163 | 17395 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | 0.179793 | 3.01364 | 17395 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.041492 | 0.0667568 | 17395 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | 0.222655 | 6.20926 | 17395 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | 0.0503826 | -0.0253589 | 17395 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.423196 | 6.00653 | 17395 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.00993159 | 0.0350942 | 17353 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.169384 | 6.26426 | 17353 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.00260294 | 0.0277534 | 17395 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.148915 | 6.28565 | 17395 |
| 0.05 | zero | entropy | H1 | -0.0993453 | 0.144638 | 17395 |
| 0.05 | zero | entropy | H2 | 1.49255 | 1.08502 | 17395 |
| 0.05 | zero | front_position | H1 | 0.0512396 | -0.00594663 | 17395 |
| 0.05 | zero | front_position | H2 | -1.08031 | 3.65789 | 17395 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | -0.0139672 | 0.0593618 | 17353 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 2.24582 | 0.331312 | 17353 |
| 0.05 | zero | uniform_random_20_repeats | H1 | 0.0250734 | 0.0202196 | 17395 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 2.34038 | 0.237197 | 17395 |
| 0.1 | local_median | entropy | H1 | -0.0229894 | 0.0764263 | 17395 |
| 0.1 | local_median | entropy | H2 | 0.0826391 | 3.40699 | 17395 |
| 0.1 | local_median | front_position | H1 | 0.00136984 | 0.0520671 | 17395 |
| 0.1 | local_median | front_position | H2 | 0.0801979 | 3.40943 | 17395 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.0437436 | 0.00982417 | 17353 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | 0.221008 | 3.26537 | 17353 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.0453702 | 0.00806669 | 17395 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.368134 | 3.1215 | 17395 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0526209 | 0.0910992 | 17395 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | 0.348179 | 6.15521 | 17395 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0518031 | -0.0134491 | 17395 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.538989 | 5.96511 | 17395 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0271879 | 0.0655468 | 17353 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.344823 | 6.15835 | 17353 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.00767984 | 0.0459554 | 17395 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.315847 | 6.18779 | 17395 |
| 0.1 | zero | entropy | H1 | -0.102776 | 0.167282 | 17395 |
| 0.1 | zero | entropy | H2 | 1.63031 | 1.50603 | 17395 |
| 0.1 | zero | front_position | H1 | 0.0577145 | 0.00679176 | 17395 |
| 0.1 | zero | front_position | H2 | -1.15725 | 4.29359 | 17395 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.0949964 | 0.159641 | 17353 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 3.11807 | 0.0173707 | 17353 |
| 0.1 | zero | uniform_random_20_repeats | H1 | 0.00835345 | 0.0561528 | 17395 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 3.19324 | -0.0568988 | 17395 |
| 0.2 | local_median | entropy | H1 | -0.0548358 | 0.165331 | 17395 |
| 0.2 | local_median | entropy | H2 | 0.212898 | 3.82745 | 17395 |
| 0.2 | local_median | front_position | H1 | 0.01291 | 0.0975856 | 17395 |
| 0.2 | local_median | front_position | H2 | 0.428458 | 3.61189 | 17395 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.0687094 | 0.0420553 | 17353 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.404451 | 3.6326 | 17353 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.0879066 | 0.0225891 | 17395 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.674438 | 3.36591 | 17395 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.071258 | 0.124065 | 17395 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | 0.543495 | 6.0396 | 17395 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0643346 | -0.0124072 | 17395 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.514231 | 6.06855 | 17395 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0584633 | 0.110449 | 17353 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.644513 | 5.93874 | 17353 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0217081 | 0.0734521 | 17395 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.719486 | 5.86365 | 17395 |
| 0.2 | zero | entropy | H1 | -0.113218 | 0.203367 | 17395 |
| 0.2 | zero | entropy | H2 | 1.54782 | 2.67923 | 17395 |
| 0.2 | zero | front_position | H1 | 0.0957239 | -0.00557534 | 17395 |
| 0.2 | zero | front_position | H2 | -1.40482 | 5.63187 | 17395 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.282948 | 0.373294 | 17353 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.351 | -0.125706 | 17353 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.101556 | 0.191705 | 17395 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 4.91976 | -0.692706 | 17395 |
| 0.4 | local_median | entropy | H1 | -0.226339 | 0.461867 | 17395 |
| 0.4 | local_median | entropy | H2 | 0.186207 | 4.56739 | 17395 |
| 0.4 | local_median | front_position | H1 | 0.0813237 | 0.154205 | 17395 |
| 0.4 | local_median | front_position | H2 | 0.835653 | 3.91794 | 17395 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.0922659 | 0.143829 | 17353 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.463377 | 4.28644 | 17353 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.154793 | 0.0807357 | 17395 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 0.805431 | 3.94816 | 17395 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.0839683 | 0.117208 | 17395 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 0.881172 | 5.78329 | 17395 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.0919667 | -0.0602864 | 17395 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | 0.468307 | 6.19774 | 17395 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.100716 | 0.133398 | 17353 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 1.10767 | 5.55473 | 17353 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0778069 | 0.110393 | 17395 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 1.59048 | 5.07258 | 17395 |
| 0.4 | zero | entropy | H1 | -0.319314 | 0.400399 | 17395 |
| 0.4 | zero | entropy | H2 | 1.16129 | 4.69206 | 17395 |
| 0.4 | zero | front_position | H1 | 0.0589271 | 0.0221587 | 17395 |
| 0.4 | zero | front_position | H2 | -0.217251 | 6.0706 | 17395 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.559248 | 0.640409 | 17353 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 4.23545 | 1.61391 | 17353 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.284752 | 0.365838 | 17395 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 5.23716 | 0.616186 | 17395 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 71.6658 | 17407 |
| dos_and_pe_headers | 458.921 | 17407 |
| executable_sections | 10722.1 | 17407 |
| non_executable_sections | 3252.9 | 17407 |
| overlay | 3274.38 | 17407 |
| resource_like_sections | 3311.33 | 17407 |
| unknown | 778.89 | 17407 |

## era

| Scope | H | Effect | 95% CI | Holm p | Eligible files | Groups | Empty CAM excluded |
|---|---|---:|---:|---:|---:|---:|---:|
| seed_42 | H1 | -0.0222827 | [-0.0500321, 0.00646583] | 0.93903 | 5311 | 1419 | 20 |
| seed_42 | H2 | 0.452407 | [0.410184, 0.495437] | 0.0009995 | 5311 | 1419 | 20 |
| seed_43 | H1 | -0.0230512 | [-0.0415289, -0.00589357] | 0.996002 | 5323 | 1424 | 8 |
| seed_43 | H2 | 0.0729813 | [0.0470388, 0.100195] | 0.0009995 | 5323 | 1424 | 8 |
| seed_44 | H1 | -0.0355312 | [-0.0546405, -0.0164336] | 1 | 5329 | 1428 | 2 |
| seed_44 | H2 | 0.263019 | [0.227018, 0.29892] | 0.0009995 | 5329 | 1428 | 2 |
| seed_average | H1 | -0.0246606 | [-0.0406498, -0.00892695] | 0.9995 | 5302 | 1412 | {'seed_42': 20, 'seed_43': 8, 'seed_44': 2} |
| seed_average | H2 | 0.26493 | [0.23892, 0.292362] | 0.0009995 | 5302 | 1412 | {'seed_42': 20, 'seed_43': 8, 'seed_44': 2} |

### File bootstrap sensitivity

| Scope | H | Effect | 95% CI | p |
|---|---|---:|---:|---:|
| seed_42 | H1 | -0.0190306 | [-0.0301824, -0.00831223] | 0.9995 |
| seed_42 | H2 | 0.367292 | [0.345235, 0.388144] | 0.00049975 |
| seed_43 | H1 | -0.0160145 | [-0.0230313, -0.00861273] | 1 |
| seed_43 | H2 | -0.0175825 | [-0.0291933, -0.00541682] | 0.999 |
| seed_44 | H1 | -0.0177391 | [-0.0260075, -0.00931283] | 1 |
| seed_44 | H2 | 0.155212 | [0.137704, 0.171697] | 0.00049975 |
| seed_average | H1 | -0.0159896 | [-0.0218093, -0.0100408] | 1 |
| seed_average | H2 | 0.168938 | [0.15568, 0.182104] | 0.00049975 |

### Correctly detected malicious subset

| Scope | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| seed_42 | H1 | -0.0325995 | [-0.0573104, -0.0106567] | 5043 |
| seed_42 | H2 | 0.502653 | [0.457842, 0.550949] | 5043 |
| seed_43 | H1 | -0.0212267 | [-0.0362676, -0.0076191] | 4958 |
| seed_43 | H2 | 0.0920689 | [0.0634443, 0.121886] | 4958 |
| seed_44 | H1 | -0.0419475 | [-0.0570987, -0.0278103] | 5090 |
| seed_44 | H2 | 0.296111 | [0.259628, 0.33336] | 5090 |
| seed_average | H1 | -0.0235547 | [-0.0351028, -0.0124559] | 4833 |
| seed_average | H2 | 0.300009 | [0.271171, 0.329775] | 4833 |

### seed_42 subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.0240243 | [-0.0557276, 0.00707165] | 5040 |
| mean_pool | H2 | 0.511981 | [0.465303, 0.557216] | 5040 |
| nearest_repetition | H1 | -0.0329626 | [-0.119443, 0.0385324] | 271 |
| nearest_repetition | H2 | -0.00537158 | [-0.0843179, 0.0834004] | 271 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | 0.00557401 | 0.0295329 | 5312 |
| 0.05 | local_median | entropy | H2 | 0.0654602 | 1.97728 | 5312 |
| 0.05 | local_median | front_position | H1 | 0.00939267 | 0.0257142 | 5312 |
| 0.05 | local_median | front_position | H2 | -0.30813 | 2.35087 | 5312 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.027598 | 0.00751546 | 5311 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | -0.094713 | 2.13735 | 5311 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.0279178 | 0.00718904 | 5312 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | -0.0527715 | 2.09551 | 5312 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.0502238 | 0.0667612 | 5312 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | 0.256269 | 5.98381 | 5312 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | 0.0278558 | -0.0114875 | 5312 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.224859 | 6.01394 | 5312 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.00359367 | 0.020187 | 5311 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.186344 | 6.05449 | 5311 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | 0.00337889 | 0.0130098 | 5312 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.19475 | 6.04501 | 5312 |
| 0.05 | zero | entropy | H1 | -0.162394 | 0.222614 | 5312 |
| 0.05 | zero | entropy | H2 | 0.744459 | 0.678799 | 5312 |
| 0.05 | zero | front_position | H1 | -0.0249918 | 0.0852115 | 5312 |
| 0.05 | zero | front_position | H2 | -0.0727594 | 1.49602 | 5312 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | -0.0275654 | 0.0877944 | 5311 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 0.761989 | 0.661292 | 5311 |
| 0.05 | zero | uniform_random_20_repeats | H1 | -0.00244614 | 0.0626658 | 5312 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 0.618287 | 0.804972 | 5312 |
| 0.1 | local_median | entropy | H1 | 0.000936296 | 0.0673289 | 5312 |
| 0.1 | local_median | entropy | H2 | 0.187078 | 2.12977 | 5312 |
| 0.1 | local_median | front_position | H1 | -0.0345683 | 0.102834 | 5312 |
| 0.1 | local_median | front_position | H2 | -0.300003 | 2.61685 | 5312 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.0500781 | 0.0181999 | 5311 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | -0.0886825 | 2.40555 | 5311 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.0533687 | 0.0148965 | 5312 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.00437522 | 2.31247 | 5312 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0595276 | 0.0829704 | 5312 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | 0.451876 | 5.96428 | 5312 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0513558 | -0.0272509 | 5312 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.586808 | 5.82498 | 5312 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0190306 | 0.0424498 | 5311 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.367292 | 6.05151 | 5311 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | 0.00100096 | 0.0217861 | 5312 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.398225 | 6.018 | 5312 |
| 0.1 | zero | entropy | H1 | -0.136332 | 0.236533 | 5312 |
| 0.1 | zero | entropy | H2 | 1.21507 | 0.57958 | 5312 |
| 0.1 | zero | front_position | H1 | 0.0661181 | 0.0340825 | 5312 |
| 0.1 | zero | front_position | H2 | -1.45648 | 3.25113 | 5312 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.13902 | 0.239236 | 5311 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 1.84582 | -0.0510757 | 5311 |
| 0.1 | zero | uniform_random_20_repeats | H1 | -0.0907343 | 0.190935 | 5312 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 1.45213 | 0.342524 | 5312 |
| 0.2 | local_median | entropy | H1 | 0.00409815 | 0.140778 | 5312 |
| 0.2 | local_median | entropy | H2 | 0.603905 | 2.44855 | 5312 |
| 0.2 | local_median | front_position | H1 | -0.0114333 | 0.15631 | 5312 |
| 0.2 | local_median | front_position | H2 | 0.223071 | 2.82938 | 5312 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.0920136 | 0.0528901 | 5311 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.109117 | 2.94353 | 5311 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.112386 | 0.0324908 | 5312 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.289484 | 2.76297 | 5312 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.0811885 | 0.106272 | 5312 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | 0.749825 | 5.93974 | 5312 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0837924 | -0.0599358 | 5312 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.543878 | 6.14573 | 5312 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0343626 | 0.0588716 | 5311 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.585206 | 6.10316 | 5311 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0158179 | 0.0403365 | 5312 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.788213 | 5.90016 | 5312 |
| 0.2 | zero | entropy | H1 | -0.0758223 | 0.217924 | 5312 |
| 0.2 | zero | entropy | H2 | 1.74317 | 1.22333 | 5312 |
| 0.2 | zero | front_position | H1 | 0.118334 | 0.0237674 | 5312 |
| 0.2 | zero | front_position | H2 | -1.11857 | 4.08507 | 5312 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.330872 | 0.472993 | 5311 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.19398 | -1.22722 | 5311 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.35111 | 0.493211 | 5312 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 4.44606 | -1.47956 | 5312 |
| 0.4 | local_median | entropy | H1 | -0.0580381 | 0.34946 | 5312 |
| 0.4 | local_median | entropy | H2 | 0.719892 | 3.3692 | 5312 |
| 0.4 | local_median | front_position | H1 | 0.0600221 | 0.231399 | 5312 |
| 0.4 | local_median | front_position | H2 | 0.607167 | 3.48192 | 5312 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.14581 | 0.145668 | 5311 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.290057 | 3.79941 | 5311 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.210974 | 0.0804476 | 5312 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 0.474217 | 3.61487 | 5312 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.105731 | 0.11118 | 5312 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 1.00999 | 5.84118 | 5312 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.0830506 | -0.0766804 | 5312 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | 0.704159 | 6.14549 | 5312 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.052429 | 0.0579026 | 5311 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.753164 | 6.09978 | 5311 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0468964 | 0.0524545 | 5312 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 1.38501 | 5.46713 | 5312 |
| 0.4 | zero | entropy | H1 | -0.312342 | 0.404221 | 5312 |
| 0.4 | zero | entropy | H2 | 1.85853 | 2.88931 | 5312 |
| 0.4 | zero | front_position | H1 | 0.151048 | -0.0591689 | 5312 |
| 0.4 | zero | front_position | H2 | 0.310241 | 4.4376 | 5312 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.773239 | 0.865128 | 5311 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 4.51771 | 0.230653 | 5311 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.465975 | 0.557855 | 5312 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 5.1007 | -0.352855 | 5312 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 206.74 | 5332 |
| dos_and_pe_headers | 146.679 | 5332 |
| executable_sections | 8960.97 | 5332 |
| non_executable_sections | 8738.38 | 5332 |
| overlay | 1702 | 5332 |
| resource_like_sections | 2124.38 | 5332 |
| unknown | 295.38 | 5332 |

### seed_43 subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.0253959 | [-0.0436387, -0.0066382] | 5052 |
| mean_pool | H2 | 0.0904901 | [0.0605544, 0.118105] | 5052 |
| nearest_repetition | H1 | -0.0177766 | [-0.0831561, 0.0386135] | 271 |
| nearest_repetition | H2 | -0.0810971 | [-0.123372, -0.0365646] | 271 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | 0.0339613 | 0.045801 | 5324 |
| 0.05 | local_median | entropy | H2 | 0.184878 | 1.28982 | 5324 |
| 0.05 | local_median | front_position | H1 | 0.0672907 | 0.0124716 | 5324 |
| 0.05 | local_median | front_position | H2 | -0.057704 | 1.53241 | 5324 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.0866536 | -0.0068638 | 5323 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | 0.0631953 | 1.41136 | 5323 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.0606755 | 0.0190868 | 5324 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | 0.0747003 | 1.4 | 5324 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.05602 | 0.0369615 | 5324 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | -0.0253976 | 4.59334 | 5324 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | -0.0304272 | 0.0120645 | 5324 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.142585 | 4.42475 | 5324 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0016185 | -0.0168071 | 5323 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | -0.0413732 | 4.61122 | 5323 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0280141 | 0.00953888 | 5324 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | -0.0606852 | 4.6313 | 5324 |
| 0.05 | zero | entropy | H1 | -0.0805661 | 0.185619 | 5324 |
| 0.05 | zero | entropy | H2 | 1.74496 | 0.463294 | 5324 |
| 0.05 | zero | front_position | H1 | 0.106452 | -0.00139914 | 5324 |
| 0.05 | zero | front_position | H2 | -0.294426 | 2.50268 | 5324 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | 0.102103 | 0.00298139 | 5323 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 3.17468 | -0.966389 | 5323 |
| 0.05 | zero | uniform_random_20_repeats | H1 | 0.120013 | -0.0149603 | 5324 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 3.49644 | -1.28819 | 5324 |
| 0.1 | local_median | entropy | H1 | 0.0532163 | 0.105902 | 5324 |
| 0.1 | local_median | entropy | H2 | 0.374246 | 1.25792 | 5324 |
| 0.1 | local_median | front_position | H1 | 0.0587389 | 0.10038 | 5324 |
| 0.1 | local_median | front_position | H2 | -0.0954788 | 1.72765 | 5324 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.153 | 0.00616702 | 5323 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | 0.199267 | 1.43281 | 5323 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.117667 | 0.0414516 | 5324 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.209707 | 1.42246 | 5324 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0774968 | 0.041347 | 5324 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | -0.0585358 | 4.54806 | 5324 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0478213 | -0.0840329 | 5324 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.317916 | 4.17181 | 5324 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0160145 | -0.0206458 | 5323 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | -0.0175825 | 4.5097 | 5323 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0448723 | 0.0082273 | 5324 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | -0.0597713 | 4.54972 | 5324 |
| 0.1 | zero | entropy | H1 | -0.229448 | 0.278634 | 5324 |
| 0.1 | zero | entropy | H2 | 2.4417 | 0.0106809 | 5324 |
| 0.1 | zero | front_position | H1 | 0.0409929 | 0.00819362 | 5324 |
| 0.1 | zero | front_position | H2 | -0.524453 | 2.97683 | 5324 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.0352731 | 0.0844872 | 5323 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 3.86469 | -1.41219 | 5323 |
| 0.1 | zero | uniform_random_20_repeats | H1 | 0.0177287 | 0.0314578 | 5324 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 4.24551 | -1.79313 | 5324 |
| 0.2 | local_median | entropy | H1 | 0.0255679 | 0.266553 | 5324 |
| 0.2 | local_median | entropy | H2 | 0.645983 | 1.3213 | 5324 |
| 0.2 | local_median | front_position | H1 | -0.0125792 | 0.304701 | 5324 |
| 0.2 | local_median | front_position | H2 | 0.00145906 | 1.96583 | 5324 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.245377 | 0.0468445 | 5323 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.383141 | 1.58412 | 5323 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.192542 | 0.0995788 | 5324 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.440227 | 1.52706 | 5324 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.111835 | 0.0507295 | 5324 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | -0.0516077 | 4.46766 | 5324 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0570195 | -0.117438 | 5324 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.325268 | 4.09013 | 5324 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0250049 | -0.0351136 | 5323 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.116709 | 4.30068 | 5323 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0531156 | -0.00678962 | 5324 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.0798621 | 4.33673 | 5324 |
| 0.2 | zero | entropy | H1 | -0.398857 | 0.397834 | 5324 |
| 0.2 | zero | entropy | H2 | 2.51449 | 0.636917 | 5324 |
| 0.2 | zero | front_position | H1 | -0.00201454 | 0.000992038 | 5324 |
| 0.2 | zero | front_position | H2 | -1.02775 | 4.17916 | 5324 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.230529 | 0.229553 | 5323 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.66688 | -1.51522 | 5323 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.20108 | 0.200058 | 5324 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 4.99669 | -1.84528 | 5324 |
| 0.4 | local_median | entropy | H1 | -0.27552 | 0.641343 | 5324 |
| 0.4 | local_median | entropy | H2 | 0.545634 | 1.83398 | 5324 |
| 0.4 | local_median | front_position | H1 | 0.192552 | 0.173271 | 5324 |
| 0.4 | local_median | front_position | H2 | 0.312128 | 2.06749 | 5324 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.188654 | 0.177186 | 5323 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.477624 | 1.902 | 5323 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.0967423 | 0.269081 | 5324 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 0.516943 | 1.86267 | 5324 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.120402 | 0.028737 | 5324 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 0.110375 | 4.21501 | 5324 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.0499173 | -0.141778 | 5324 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | 0.436907 | 3.89288 | 5324 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0193778 | -0.0723248 | 5323 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.284215 | 4.04478 | 5323 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0402369 | -0.0505717 | 5324 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.490154 | 3.83699 | 5324 |
| 0.4 | zero | entropy | H1 | -1.00625 | 0.991039 | 5324 |
| 0.4 | zero | entropy | H2 | 2.17837 | 1.8405 | 5324 |
| 0.4 | zero | front_position | H1 | 0.020396 | -0.0356053 | 5324 |
| 0.4 | zero | front_position | H2 | -0.32068 | 4.33955 | 5324 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.54531 | 0.53005 | 5323 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 4.13936 | -0.119975 | 5323 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.62289 | 0.607681 | 5324 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 4.30259 | -0.283713 | 5324 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 232.285 | 5332 |
| dos_and_pe_headers | 114.089 | 5332 |
| executable_sections | 9188.23 | 5332 |
| non_executable_sections | 6022.67 | 5332 |
| overlay | 1870.96 | 5332 |
| resource_like_sections | 1943.91 | 5332 |
| unknown | 264.456 | 5332 |

### seed_44 subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.0338 | [-0.0566391, -0.0130017] | 5058 |
| mean_pool | H2 | 0.295689 | [0.255672, 0.333293] | 5058 |
| nearest_repetition | H1 | -0.0759116 | [-0.161068, -0.0011262] | 271 |
| nearest_repetition | H2 | 0.0108374 | [-0.0635156, 0.0783818] | 271 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | 0.0209327 | 0.0178569 | 5330 |
| 0.05 | local_median | entropy | H2 | 0.0839605 | 1.40008 | 5330 |
| 0.05 | local_median | front_position | H1 | 0.00255913 | 0.0362305 | 5330 |
| 0.05 | local_median | front_position | H2 | 0.11616 | 1.36788 | 5330 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.0321526 | 0.00664666 | 5329 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | 0.06041 | 1.42357 | 5329 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.0309686 | 0.00782098 | 5330 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | 0.0884471 | 1.3956 | 5330 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.0443233 | 0.0562224 | 5330 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | 0.111688 | 3.85711 | 5330 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | 0.0152197 | -0.00418945 | 5330 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.228432 | 3.72972 | 5330 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.00432951 | 0.0157319 | 5329 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.0797126 | 3.88304 | 5329 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.00618844 | 0.0179287 | 5330 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.0848725 | 3.87883 | 5330 |
| 0.05 | zero | entropy | H1 | -0.0152638 | 0.0705813 | 5330 |
| 0.05 | zero | entropy | H2 | 0.949257 | -0.271604 | 5330 |
| 0.05 | zero | front_position | H1 | -0.0185958 | 0.0739132 | 5330 |
| 0.05 | zero | front_position | H2 | -0.446606 | 1.12426 | 5330 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | 0.00926586 | 0.0460521 | 5329 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 1.41675 | -0.739135 | 5329 |
| 0.05 | zero | uniform_random_20_repeats | H1 | 0.0273673 | 0.0279501 | 5330 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 1.44688 | -0.769231 | 5330 |
| 0.1 | local_median | entropy | H1 | 0.033767 | 0.0471114 | 5330 |
| 0.1 | local_median | entropy | H2 | 0.334876 | 1.54862 | 5330 |
| 0.1 | local_median | front_position | H1 | 0.00870769 | 0.0721707 | 5330 |
| 0.1 | local_median | front_position | H2 | 0.410885 | 1.47261 | 5330 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.0643815 | 0.016513 | 5329 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | 0.298894 | 1.58469 | 5329 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.0647912 | 0.0160872 | 5330 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.342017 | 1.54148 | 5330 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0501249 | 0.064032 | 5330 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | 0.171386 | 3.81193 | 5330 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0354802 | -0.0209532 | 5330 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.279495 | 3.70276 | 5330 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0177391 | 0.0317043 | 5329 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.155212 | 3.83124 | 5329 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.00917689 | 0.0231121 | 5330 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.140409 | 3.84761 | 5330 |
| 0.1 | zero | entropy | H1 | -0.026139 | 0.113233 | 5330 |
| 0.1 | zero | entropy | H2 | 1.15211 | -0.0504684 | 5330 |
| 0.1 | zero | front_position | H1 | -0.00104553 | 0.0881396 | 5330 |
| 0.1 | zero | front_position | H2 | -0.633426 | 1.73507 | 5330 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.0515527 | 0.13861 | 5329 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 2.49401 | -1.39227 | 5329 |
| 0.1 | zero | uniform_random_20_repeats | H1 | 0.0206696 | 0.0664245 | 5330 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 2.5329 | -1.43126 | 5330 |
| 0.2 | local_median | entropy | H1 | 0.0596442 | 0.105595 | 5330 |
| 0.2 | local_median | entropy | H2 | 0.747795 | 1.81977 | 5330 |
| 0.2 | local_median | front_position | H1 | 0.0699798 | 0.0952589 | 5330 |
| 0.2 | local_median | front_position | H2 | 1.14569 | 1.42187 | 5330 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.116931 | 0.0483323 | 5329 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.670692 | 1.89717 | 5329 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.128962 | 0.0362764 | 5330 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.777504 | 1.79006 | 5330 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.0683602 | 0.0788801 | 5330 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | 0.167654 | 3.78493 | 5330 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0482925 | -0.0374675 | 5330 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.152018 | 3.80363 | 5330 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0300958 | 0.0400839 | 5329 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.258492 | 3.69696 | 5329 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0291277 | 0.0394918 | 5330 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.258988 | 3.69629 | 5330 |
| 0.2 | zero | entropy | H1 | -0.0497025 | 0.179845 | 5330 |
| 0.2 | zero | entropy | H2 | 1.75283 | 0.396682 | 5330 |
| 0.2 | zero | front_position | H1 | 0.116759 | 0.0133835 | 5330 |
| 0.2 | zero | front_position | H2 | 0.104922 | 2.04459 | 5330 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.151245 | 0.281307 | 5329 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.44975 | -2.29994 | 5329 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.110711 | 0.240853 | 5330 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 5.00321 | -2.85369 | 5330 |
| 0.4 | local_median | entropy | H1 | 0.0940344 | 0.242788 | 5330 |
| 0.4 | local_median | entropy | H2 | 0.922932 | 2.32021 | 5330 |
| 0.4 | local_median | front_position | H1 | 0.21312 | 0.123703 | 5330 |
| 0.4 | local_median | front_position | H2 | 1.19036 | 2.05279 | 5330 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.206623 | 0.130265 | 5329 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.849798 | 2.3938 | 5329 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.229065 | 0.107758 | 5330 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 1.06081 | 2.18234 | 5330 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.0618766 | 0.0707302 | 5330 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 0.368214 | 3.66352 | 5330 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.05498 | -0.0461192 | 5330 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | 0.337751 | 3.68938 | 5330 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | 0.00591539 | 0.00331804 | 5329 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.517254 | 3.51359 | 5329 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0472397 | 0.0559341 | 5330 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.754849 | 3.27418 | 5330 |
| 0.4 | zero | entropy | H1 | -0.42586 | 0.580665 | 5330 |
| 0.4 | zero | entropy | H2 | 1.75903 | 1.60254 | 5330 |
| 0.4 | zero | front_position | H1 | 0.12296 | 0.0318454 | 5330 |
| 0.4 | zero | front_position | H2 | -0.527759 | 3.88933 | 5330 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.490363 | 0.645161 | 5329 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 3.87252 | -0.510461 | 5329 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.371354 | 0.52616 | 5330 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 3.67272 | -0.311151 | 5330 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 221.336 | 5332 |
| dos_and_pe_headers | 123.722 | 5332 |
| executable_sections | 8109.96 | 5332 |
| non_executable_sections | 6650.58 | 5332 |
| overlay | 1599.23 | 5332 |
| resource_like_sections | 2049.49 | 5332 |
| unknown | 268.791 | 5332 |

### seed_average subgroups

| Repr policy | H | Effect | 95% CI | Eligible files |
|---|---|---:|---:|---:|
| mean_pool | H1 | -0.025166 | [-0.0418513, -0.00762595] | 5031 |
| mean_pool | H2 | 0.302081 | [0.274079, 0.333013] | 5031 |
| nearest_repetition | H1 | -0.0422169 | [-0.0982373, 0.00628814] | 271 |
| nearest_repetition | H2 | -0.0252104 | [-0.0725073, 0.0207099] | 271 |

### Descriptive combinations

| Budget | Fill | Control | H | Paired mean | Control mean | Eligible files |
|---:|---|---|---|---:|---:|---:|
| 0.05 | local_median | entropy | H1 | 0.020156 | 0.0310636 | 5312 |
| 0.05 | local_median | entropy | H2 | 0.111433 | 1.55573 | 5312 |
| 0.05 | local_median | front_position | H1 | 0.0264142 | 0.0248054 | 5312 |
| 0.05 | local_median | front_position | H2 | -0.0832248 | 1.75039 | 5312 |
| 0.05 | local_median | structure_matched_random_20_repeats | H1 | 0.0488014 | 0.00243278 | 5311 |
| 0.05 | local_median | structure_matched_random_20_repeats | H2 | 0.00963076 | 1.65743 | 5311 |
| 0.05 | local_median | uniform_random_20_repeats | H1 | 0.039854 | 0.0113656 | 5312 |
| 0.05 | local_median | uniform_random_20_repeats | H2 | 0.036792 | 1.63037 | 5312 |
| 0.05 | structure_conditioned_resampling | entropy | H1 | -0.050189 | 0.053315 | 5312 |
| 0.05 | structure_conditioned_resampling | entropy | H2 | 0.114186 | 4.81142 | 5312 |
| 0.05 | structure_conditioned_resampling | front_position | H1 | 0.00421611 | -0.00120414 | 5312 |
| 0.05 | structure_conditioned_resampling | front_position | H2 | 0.198625 | 4.7228 | 5312 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.00318056 | 0.00637059 | 5311 |
| 0.05 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.0748943 | 4.84958 | 5311 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0102745 | 0.0134925 | 5312 |
| 0.05 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.0729791 | 4.85172 | 5312 |
| 0.05 | zero | entropy | H1 | -0.0860746 | 0.159605 | 5312 |
| 0.05 | zero | entropy | H2 | 1.14622 | 0.290163 | 5312 |
| 0.05 | zero | front_position | H1 | 0.0209547 | 0.0525752 | 5312 |
| 0.05 | zero | front_position | H2 | -0.271264 | 1.70765 | 5312 |
| 0.05 | zero | structure_matched_random_20_repeats | H1 | 0.0279344 | 0.0456093 | 5311 |
| 0.05 | zero | structure_matched_random_20_repeats | H2 | 1.78447 | -0.348077 | 5311 |
| 0.05 | zero | uniform_random_20_repeats | H1 | 0.0483114 | 0.0252186 | 5312 |
| 0.05 | zero | uniform_random_20_repeats | H2 | 1.85387 | -0.417483 | 5312 |
| 0.1 | local_median | entropy | H1 | 0.0293065 | 0.0734475 | 5312 |
| 0.1 | local_median | entropy | H2 | 0.298733 | 1.64544 | 5312 |
| 0.1 | local_median | front_position | H1 | 0.0109594 | 0.0917946 | 5312 |
| 0.1 | local_median | front_position | H2 | 0.00513442 | 1.93903 | 5312 |
| 0.1 | local_median | structure_matched_random_20_repeats | H1 | 0.0891532 | 0.0136266 | 5311 |
| 0.1 | local_median | structure_matched_random_20_repeats | H2 | 0.136493 | 1.80768 | 5311 |
| 0.1 | local_median | uniform_random_20_repeats | H1 | 0.0786089 | 0.0241451 | 5312 |
| 0.1 | local_median | uniform_random_20_repeats | H2 | 0.185366 | 1.7588 | 5312 |
| 0.1 | structure_conditioned_resampling | entropy | H1 | -0.0623831 | 0.0627831 | 5312 |
| 0.1 | structure_conditioned_resampling | entropy | H2 | 0.188242 | 4.77476 | 5312 |
| 0.1 | structure_conditioned_resampling | front_position | H1 | 0.0448858 | -0.044079 | 5312 |
| 0.1 | structure_conditioned_resampling | front_position | H2 | 0.394739 | 4.56651 | 5312 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0175947 | 0.0178361 | 5311 |
| 0.1 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.168307 | 4.79748 | 5311 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.0176828 | 0.0177085 | 5312 |
| 0.1 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.159621 | 4.80511 | 5312 |
| 0.1 | zero | entropy | H1 | -0.13064 | 0.209467 | 5312 |
| 0.1 | zero | entropy | H2 | 1.60296 | 0.179931 | 5312 |
| 0.1 | zero | front_position | H1 | 0.0353552 | 0.0434719 | 5312 |
| 0.1 | zero | front_position | H2 | -0.871454 | 2.65435 | 5312 |
| 0.1 | zero | structure_matched_random_20_repeats | H1 | -0.0752819 | 0.154111 | 5311 |
| 0.1 | zero | structure_matched_random_20_repeats | H2 | 2.73484 | -0.951846 | 5311 |
| 0.1 | zero | uniform_random_20_repeats | H1 | -0.0174453 | 0.0962724 | 5312 |
| 0.1 | zero | uniform_random_20_repeats | H2 | 2.74351 | -0.960622 | 5312 |
| 0.2 | local_median | entropy | H1 | 0.0297701 | 0.170975 | 5312 |
| 0.2 | local_median | entropy | H2 | 0.665894 | 1.86321 | 5312 |
| 0.2 | local_median | front_position | H1 | 0.0153224 | 0.185423 | 5312 |
| 0.2 | local_median | front_position | H2 | 0.456742 | 2.07236 | 5312 |
| 0.2 | local_median | structure_matched_random_20_repeats | H1 | 0.151441 | 0.0493556 | 5311 |
| 0.2 | local_median | structure_matched_random_20_repeats | H2 | 0.38765 | 2.14161 | 5311 |
| 0.2 | local_median | uniform_random_20_repeats | H1 | 0.14463 | 0.0561154 | 5312 |
| 0.2 | local_median | uniform_random_20_repeats | H2 | 0.502405 | 2.02669 | 5312 |
| 0.2 | structure_conditioned_resampling | entropy | H1 | -0.0871279 | 0.0786272 | 5312 |
| 0.2 | structure_conditioned_resampling | entropy | H2 | 0.288624 | 4.73078 | 5312 |
| 0.2 | structure_conditioned_resampling | front_position | H1 | 0.0630348 | -0.0716136 | 5312 |
| 0.2 | structure_conditioned_resampling | front_position | H2 | 0.340388 | 4.67983 | 5312 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0298211 | 0.0212806 | 5311 |
| 0.2 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.320136 | 4.70027 | 5311 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.032687 | 0.0243462 | 5312 |
| 0.2 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.375688 | 4.64439 | 5312 |
| 0.2 | zero | entropy | H1 | -0.174794 | 0.265201 | 5312 |
| 0.2 | zero | entropy | H2 | 2.0035 | 0.75231 | 5312 |
| 0.2 | zero | front_position | H1 | 0.0776928 | 0.0127143 | 5312 |
| 0.2 | zero | front_position | H2 | -0.680465 | 3.43627 | 5312 |
| 0.2 | zero | structure_matched_random_20_repeats | H1 | -0.237549 | 0.327951 | 5311 |
| 0.2 | zero | structure_matched_random_20_repeats | H2 | 4.43687 | -1.68079 | 5311 |
| 0.2 | zero | uniform_random_20_repeats | H1 | -0.220967 | 0.311374 | 5312 |
| 0.2 | zero | uniform_random_20_repeats | H2 | 4.81532 | -2.05951 | 5312 |
| 0.4 | local_median | entropy | H1 | -0.0798412 | 0.411197 | 5312 |
| 0.4 | local_median | entropy | H2 | 0.729486 | 2.5078 | 5312 |
| 0.4 | local_median | front_position | H1 | 0.155231 | 0.176124 | 5312 |
| 0.4 | local_median | front_position | H2 | 0.703218 | 2.53407 | 5312 |
| 0.4 | local_median | structure_matched_random_20_repeats | H1 | 0.180362 | 0.15104 | 5311 |
| 0.4 | local_median | structure_matched_random_20_repeats | H2 | 0.53916 | 2.6984 | 5311 |
| 0.4 | local_median | uniform_random_20_repeats | H1 | 0.178927 | 0.152429 | 5312 |
| 0.4 | local_median | uniform_random_20_repeats | H2 | 0.683988 | 2.5533 | 5312 |
| 0.4 | structure_conditioned_resampling | entropy | H1 | -0.0960031 | 0.0702156 | 5312 |
| 0.4 | structure_conditioned_resampling | entropy | H2 | 0.496193 | 4.57324 | 5312 |
| 0.4 | structure_conditioned_resampling | front_position | H1 | 0.0626493 | -0.0881926 | 5312 |
| 0.4 | structure_conditioned_resampling | front_position | H2 | 0.492939 | 4.57592 | 5312 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H1 | -0.0219638 | -0.00370137 | 5311 |
| 0.4 | structure_conditioned_resampling | structure_matched_random_20_repeats | H2 | 0.518211 | 4.55272 | 5311 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H1 | -0.044791 | 0.0192723 | 5312 |
| 0.4 | structure_conditioned_resampling | uniform_random_20_repeats | H2 | 0.87667 | 4.19277 | 5312 |
| 0.4 | zero | entropy | H1 | -0.581483 | 0.658642 | 5312 |
| 0.4 | zero | entropy | H2 | 1.93198 | 2.11078 | 5312 |
| 0.4 | zero | front_position | H1 | 0.0981348 | -0.0209763 | 5312 |
| 0.4 | zero | front_position | H2 | -0.179399 | 4.22216 | 5312 |
| 0.4 | zero | structure_matched_random_20_repeats | H1 | -0.602971 | 0.680113 | 5311 |
| 0.4 | zero | structure_matched_random_20_repeats | H2 | 4.17653 | -0.133261 | 5311 |
| 0.4 | zero | uniform_random_20_repeats | H1 | -0.48674 | 0.563898 | 5312 |
| 0.4 | zero | uniform_random_20_repeats | H2 | 4.35867 | -0.315906 | 5312 |

### Structure CAM mass

| Region | Mean mass | N |
|---|---:|---:|
| certificate_table | 220.12 | 5332 |
| dos_and_pe_headers | 128.163 | 5332 |
| executable_sections | 8753.05 | 5332 |
| non_executable_sections | 7137.21 | 5332 |
| overlay | 1724.07 | 5332 |
| resource_like_sections | 2039.26 | 5332 |
| unknown | 276.209 | 5332 |

